"""Build a clean relocatable Windows planner payload from installed CPython.

This is a staging tool, not an installer. It never reads app state, customer
credentials, model caches or DramaClip databases, and refuses an existing target.
ASR models/runtime and FFmpeg remain supplied by Manju's established workers.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '3562664e0d7f00dc4a5ff5784337751c510925a2'
DEPENDENCIES = ('pydantic', 'pydantic-core', 'annotated-types', 'typing-extensions', 'typing-inspection')
EXCLUDE_STDLIB = {'site-packages', '__pycache__', 'test', 'tests', 'idlelib', 'tkinter', 'turtledemo', 'ensurepip', 'venv'}


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _copy_dependencies(site):
    records = []
    for name in DEPENDENCIES:
        dist = importlib.metadata.distribution(name)
        for item in dist.files or ():
            relative = Path(str(item))
            if (relative.is_absolute() or '..' in relative.parts or '__pycache__' in relative.parts or
                    relative.suffix in ('.pyc', '.pth') or relative.name in ('direct_url.json', 'INSTALLER', 'REQUESTED')):
                continue
            src = Path(dist.locate_file(item))
            target = site / relative
            if src.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
        records.append({'name': name, 'version': dist.version, 'source': 'installed local distribution; no network'})
    return records


def build(destination, source_engine, verify_rpc=True):
    if os.name != 'nt' or sys.version_info[:2] != (3, 12) or sys.maxsize <= 2 ** 32:
        raise ValueError('Use a Windows x64 CPython 3.12 runtime to stage this payload')
    destination = Path(destination).resolve()
    if not destination.is_relative_to((ROOT / 'tmp').resolve()):
        raise ValueError('Staging output must stay under the workspace tmp directory')
    if destination.exists():
        raise ValueError('Refusing to overwrite an existing staging directory')
    source_engine = Path(source_engine).resolve()
    source_manifest = json.loads((source_engine / 'source-manifest.json').read_text('utf-8'))
    if source_manifest.get('commit') != COMMIT:
        raise ValueError('Unexpected DramaClip source commit')
    # Read only the pinned source entries declared by preparation. This excludes
    # runtime caches, jobs, SQLite files, traces and locally generated media.
    destination.mkdir(parents=True)
    for name, expected in source_manifest['sourceSha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or '__pycache__' in relative.parts:
            raise ValueError('Invalid source manifest path')
        source = source_engine / 'source' / relative
        if sha(source) != expected:
            raise ValueError('Pinned DramaClip source changed: ' + name)
        target = destination / 'source' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(source_engine / 'source-manifest.json', destination / 'source-manifest.json')
    runtime = destination / 'runtime'
    scripts, native, lib, site = runtime/'Scripts', runtime/'DLLs', runtime/'Lib', runtime/'Lib/site-packages'
    for path in (scripts, native, lib, site): path.mkdir(parents=True, exist_ok=True)
    python_base = Path(sys.base_prefix).resolve()
    for name in ('python.exe', 'python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
        source = python_base / name
        if not source.is_file(): raise FileNotFoundError('CPython base runtime file missing: ' + name)
        shutil.copy2(source, scripts/name)
    for source in (python_base/'DLLs').iterdir():
        if (source.is_file() and source.suffix.lower() in ('.pyd', '.dll') and
                not source.name.startswith(('_test', '_ctypes_test', '_tkinter', 'tcl', 'tk'))):
            shutil.copy2(source, native/source.name)
    stdlib = python_base/'Lib'
    with zipfile.ZipFile(runtime/'python312.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for directory, folders, names in os.walk(stdlib):
            folders[:] = sorted(folder for folder in folders if folder not in EXCLUDE_STDLIB)
            for name in sorted(names):
                source = Path(directory)/name
                relative = source.relative_to(stdlib)
                if source.suffix in ('.pyc', '.pyd', '.dll') or name in ('ssl.py', 'codex-rejected-cas.pem'):
                    continue
                archive.write(source, relative.as_posix())
    # This host's ssl.py has an auxiliary certificate-rejection policy. Preserve
    # the original implementation and its real-file policy, not a zip-only path.
    shutil.copy2(stdlib/'ssl.py', lib/'ssl.py')
    policy = stdlib/'codex-rejected-cas.pem'
    if 'codex-rejected-cas.pem' in (stdlib/'ssl.py').read_text('utf-8'):
        if not policy.is_file(): raise FileNotFoundError('CPython SSL policy file missing')
        shutil.copy2(policy, lib/policy.name)
    (scripts/'python312._pth').write_text('../Lib\n../python312.zip\n../DLLs\n../Lib/site-packages\n', 'utf-8')
    notices = runtime/'licenses'; notices.mkdir()
    shutil.copy2(python_base/'LICENSE.txt', notices/'CPython-LICENSE.txt')
    dependencies = _copy_dependencies(site)
    (destination/'local-dependencies.json').write_text(json.dumps(dependencies, ensure_ascii=False, indent=2), 'utf-8')
    python = scripts/'python.exe'
    env = {k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON', 'VIRTUAL_ENV'))}
    env['PYTHONUTF8'] = '1'
    code = ("import sys,json,ssl,sqlite3,ctypes,pydantic; ssl.create_default_context(); "
            "print(json.dumps({'prefix':sys.prefix,'basePrefix':sys.base_prefix,'path':sys.path,'pydantic':pydantic.__version__}))")
    probe = json.loads(subprocess.check_output([str(python), '-I', '-B', '-c', code], cwd=ROOT/'tmp', env=env, text=True))
    if any(not Path(path).resolve().is_relative_to(runtime) for path in probe['path']):
        raise RuntimeError('Portable Python unexpectedly referenced an external library path')
    import_code = ('import sys;sys.path.insert(0,' + repr(str(destination/'source/service')) + ');import dramaclip.service_app')
    subprocess.run([str(python), '-I', '-B', '-c', import_code], cwd=ROOT/'tmp', env=env, check=True, capture_output=True)
    rpc = False
    if verify_rpc:
        sys.path.insert(0, str(ROOT))
        from promotion_dramaclip import Sidecar
        with tempfile.TemporaryDirectory(prefix='dramaclip-portable-rpc-', dir=ROOT/'tmp') as data:
            with Sidecar({'root': str(destination), 'python': str(python)}, data, threading.Event()) as sidecar:
                reply = sidecar.call('system.ping', timeout=20)
                if not isinstance(reply, dict): raise RuntimeError('Unexpected sidecar ping reply')
                rpc = True
    marker = {'format': 2, 'commit': COMMIT, 'serviceImportVerified': True, 'rpcVerified': rpc,
              'pythonRelative': 'runtime/Scripts/python.exe', 'pythonSha256': sha(python),
              'sidecarSha256': sha(ROOT/'tools/dramaclip_sidecar.py'),
              'serviceEntrySha256': sha(destination/'source/service/dramaclip/service_app.py'),
              'dependencyProbe': 'pydantic + Manju narrow DramaClip router', 'portableRuntime': True}
    (destination/'runtime-ready.json').write_text(json.dumps(marker, indent=2), 'utf-8')
    for cache in sorted(destination.rglob('__pycache__'), key=lambda path:len(path.parts), reverse=True):
        if cache.is_dir() and cache.resolve().is_relative_to(destination): shutil.rmtree(cache)
    files = {p.relative_to(destination).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p)}
             for p in sorted(destination.rglob('*')) if p.is_file() and '__pycache__' not in p.parts}
    record = {'format': 1, 'kind': 'manju-dramaclip-clean-staging', 'commit': COMMIT,
              'pythonVersion': sys.version.split()[0], 'modelWeightsIncluded': False, 'appStateIncluded': False,
              'runtimeProbe': probe, 'rpcVerified': rpc, 'files': files}
    (destination/'payload-manifest.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'root':str(destination),'files':len(files),'bytes':sum(v['bytes'] for v in files.values()),
                      'rpcVerified':rpc,'python':str(python)},ensure_ascii=False),flush=True)
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, default=ROOT/'tmp'/('dramaclip-portable-'+time.strftime('%Y%m%d-%H%M%S')))
    parser.add_argument('--source-engine', type=Path, default=ROOT/'engines/dramaclip')
    parser.add_argument('--skip-rpc', action='store_true', help='Prepare only; readiness remains false until RPC verified')
    args = parser.parse_args()
    build(args.destination, args.source_engine, not args.skip_rpc)
