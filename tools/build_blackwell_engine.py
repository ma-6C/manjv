"""Build a separate cu128 engine from signed v1 inputs, without running models."""
from pathlib import Path, PurePosixPath
import argparse, base64, csv, hashlib, io, json, os, subprocess, sys, zipfile

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / 'tmp/portable-engine-v2-cu128'
WHEELS = ROOT / 'tmp/engine-v2-cu128-wheels'
OUT = ROOT / 'release/v0.9.2/对外发送'
ENGINE_ID = 'vsr-1.4.0-sttn-cu128'
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
import licensing


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_path(name):
    path = PurePosixPath(name)
    if not name or '\\' in name or ':' in name or path.is_absolute() or any(p in ('', '.', '..') for p in name.split('/')):
        raise ValueError('Invalid engine input path')
    return path


def wheel_paths():
    result = []
    for pattern in ('torch-2.7.0+cu128-cp312-cp312-win_amd64.whl', 'torchvision-0.22.0+cu128-cp312-cp312-win_amd64.whl'):
        path = WHEELS / pattern
        if not path.is_file():
            raise FileNotFoundError('Official pinned wheel is missing: ' + pattern)
        result.append(path)
    return result


def stage():
    wheels = wheel_paths()
    source = ROOT / 'release/v0.6.0/对外发送/漫剧工坊-AI离线引擎-v1.zip'
    if STAGE.exists():
        raise RuntimeError('A staging directory already exists; refusing to overwrite it')
    STAGE.mkdir(parents=True)
    with zipfile.ZipFile(source) as archive:
        manifest = licensing.signed_payload(json.loads(archive.read('component-signature.json')))
        if (manifest.get('product'), manifest.get('kind'), manifest.get('format')) != ('ManjuStudio', 'engine', 1):
            raise ValueError('Unsupported engine input')
        entries = {row['path']: row for row in manifest['files']}
        if len(entries) != len(manifest['files']) or set(archive.namelist()) != set(entries) | {'component-signature.json'}:
            raise ValueError('Signed v1 archive entries differ')
        copied = 0
        for name, row in entries.items():
            parts = safe_path(name).parts
            if parts[:3] == ('python', 'Lib', 'site-packages') and len(parts) > 3:
                package = parts[3]
                if package in ('torch', 'functorch', 'torchgen', 'torchvision', 'torchvision.libs') or package.startswith(('torch-', 'torchvision-')) and package.endswith('.dist-info'):
                    continue
            info = archive.getinfo(name)
            if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000 or info.file_size != row['bytes']:
                raise ValueError('Invalid signed engine entry')
            target = STAGE.joinpath(*parts)
            if not target.resolve().is_relative_to(STAGE.resolve()):
                raise ValueError('Engine entry escapes staging')
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.open(info) as src, target.open('xb') as dst:
                while block := src.read(4 * 1024 * 1024):
                    dst.write(block)
                    digest.update(block)
            if target.stat().st_size != row['bytes'] or digest.hexdigest() != row['sha256']:
                raise ValueError('Signed base file checksum differs: ' + name)
            copied += 1
            if copied % 5000 == 0:
                print('BASE_FILES_COPIED', copied, flush=True)
    site = STAGE / 'python/Lib/site-packages'
    # Install only local binary wheels into the disposable package, never into
    # the owner's Python or a customer's already-imported signed engine.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile', '--target', str(site),
                    *map(str, wheels)], cwd=ROOT, env=os.environ | {'PYTHONDONTWRITEBYTECODE': '1'}, check=True)
    meta_path = STAGE / 'engine.json'
    meta = json.loads(meta_path.read_text('utf-8'))
    meta.update(id=ENGINE_ID, torch='2.7.0+cu128', torchvision='0.22.0+cu128', cuda='12.8',
                target='NVIDIA Blackwell / GeForce RTX 50 series', modelRuntimeTested=False)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    notice = '''漫剧工坊 v2 / CUDA 12.8 离线 AI 引擎

针对 RTX 50 系列 / Blackwell：PyTorch 2.7.0+cu128，torchvision 0.22.0+cu128。
两个 Windows Python 3.12 wheel 来自 https://download.pytorch.org/whl/cu128 。
原始包的 Python、模型、修复算法及其许可保留；PyTorch/torchvision 的原始许可随新 wheel 保留。

先退出旧主程序，覆盖安装 0.9.2，再从“授权与组件”导入本 ZIP，不要手工覆盖旧引擎目录。
导入成功后，在 AI 去字幕设置中选择 STTN 时序修复，并将 STTN 推理设备设为“自动”。
本包包含完整环境和原模型，导入后会使用独立的新目录，原 v1 引擎继续保留。

按用户要求，本轮未运行模型、GPU 或客户硬件验收；本包不是已经在 RTX 5060 上实测通过的声明。
软件主程序的 NVENC 编码检测与 PyTorch/CUDA 修复推理是独立链路。
'''
    (STAGE / 'CUDA12.8引擎说明.txt').write_text(notice, 'utf-8-sig')
    provenance = {'engine': ENGINE_ID, 'sourceArchiveSha256': sha(source), 'officialIndex': 'https://download.pytorch.org/whl/cu128',
                  'wheels': [{'name': p.name, 'sha256': sha(p)} for p in wheels],
                  'baseCopiedFilesVerified': copied, 'modelRuntimeTested': False}
    (ROOT / 'tmp/engine-v2-cu128-inputs.json').write_text(json.dumps(provenance, ensure_ascii=False, indent=2), 'utf-8')
    print('CU128_STAGE_READY', flush=True)


def build():
    if not (STAGE / 'engine.json').is_file():
        raise RuntimeError('Stage the engine first')
    files = [p for p in sorted(STAGE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts
             and p.suffix not in ('.pyc', '.log') and p.name != 'direct_url.json'
             and not p.is_relative_to(STAGE / 'python/Lib/site-packages/bin')]
    # Base files were hashed while staging. Official wheel RECORDs supply the
    # replacement hashes. Verify the final bytes again as they enter the ZIP,
    # avoiding a second full read of thousands of immutable package files.
    with zipfile.ZipFile(ROOT / 'release/v0.6.0/对外发送/漫剧工坊-AI离线引擎-v1.zip') as archive:
        original = licensing.signed_payload(json.loads(archive.read('component-signature.json')))
    known = {row['path']: row for row in original['files']}
    provenance = json.loads((ROOT / 'tmp/engine-v2-cu128-inputs.json').read_text('utf-8'))
    wheel_hashes = {row['name']: row['sha256'] for row in provenance['wheels']}
    for wheel in wheel_paths():
        if sha(wheel) != wheel_hashes[wheel.name]:
            raise ValueError('Wheel changed after staging: ' + wheel.name)
        with zipfile.ZipFile(wheel) as archive:
            record = next(name for name in archive.namelist() if name.endswith('.dist-info/RECORD'))
            for name, digest, size in csv.reader(io.StringIO(archive.read(record).decode('utf-8'))):
                if digest.startswith('sha256=') and size:
                    key = 'python/Lib/site-packages/' + str(safe_path(name.replace('\\', '/')))
                    known[key] = {'path': key, 'bytes': int(size), 'sha256': base64.urlsafe_b64decode(digest[7:] + '===').hex()}
    manifest = {'format': 1, 'product': 'ManjuStudio', 'kind': 'engine', 'version': ENGINE_ID, 'files': []}
    for index, path in enumerate(files):
        name = path.relative_to(STAGE).as_posix()
        expected = known.get(name) if name != 'engine.json' and not name.endswith('.dist-info/RECORD') else None
        size = path.stat().st_size
        if expected and size != expected['bytes']:
            raise ValueError('Staged file size differs from signed base or wheel: ' + name)
        manifest['files'].append({'path': name, 'bytes': size, 'sha256': expected['sha256'] if expected else sha(path)})
        if index % 5000 == 0:
            print('HASH', index, len(files), flush=True)
    plain = ROOT / 'tmp/engine-v2-cu128-manifest.json'
    signed = ROOT / 'tmp/engine-v2-cu128-signature.json'
    plain.write_text(json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), 'utf-8')
    subprocess.run([str(ROOT / '授权管理/当前签发工具-v2/授权签发工具.exe'), '--sign-file', str(plain), str(signed)], check=True, timeout=60)
    if licensing.signed_payload(json.loads(signed.read_text('utf-8-sig'))) != manifest:
        raise RuntimeError('Signed engine manifest differs from prepared payload')
    OUT.mkdir(exist_ok=True)
    target = OUT / '漫剧工坊-AI离线引擎-v2-cu128.zip'
    if target.exists():
        raise RuntimeError('Refusing to overwrite an existing v2 archive')
    partial = target.with_suffix('.zip.partial')
    with zipfile.ZipFile(partial, 'x', zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        archive.write(signed, 'component-signature.json')
        for index, (path, row) in enumerate(zip(files, manifest['files'])):
            digest = hashlib.sha256(); written = 0
            with path.open('rb') as src, archive.open(row['path'], 'w', force_zip64=True) as dst:
                while block := src.read(4 * 1024 * 1024):
                    dst.write(block); digest.update(block); written += len(block)
            if written != row['bytes'] or digest.hexdigest() != row['sha256']:
                raise ValueError('Final staged bytes differ from signed manifest: ' + row['path'])
            if index % 5000 == 0:
                print('ZIP', index, len(files), flush=True)
    partial.rename(target)
    report = {'engine': ENGINE_ID, 'file': target.name, 'bytes': target.stat().st_size, 'sha256': sha(target),
              'unpackedBytes': sum(row['bytes'] for row in manifest['files']), 'signedFiles': len(files),
              'modelRuntimeTested': False, 'customerHardwareTested': False}
    (ROOT / 'tmp/engine-v2-cu128-build.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('stage', 'build'))
    args = parser.parse_args()
    stage() if args.action == 'stage' else build()
