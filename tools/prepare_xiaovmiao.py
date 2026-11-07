"""Copy the user-selected program only, preserving its bytes and licenses."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]


def prepare(source, destination, executable_name='vcat_local_init.exe', mode='offline-local', profile_layout='legacy'):
    source = Path(source).resolve(); destination = Path(destination).resolve()
    if Path(executable_name).name != executable_name or not executable_name.lower().endswith('.exe'):
        raise ValueError('主程序名必须是程序目录中的 EXE 文件名')
    executable = source / executable_name
    app = source / 'resources/app'
    if not executable.is_file():raise ValueError('未找到主程序：'+executable_name)
    if not (source / 'resources/app.asar').is_file():
        try:
            main = json.loads((app/'package.json').read_text('utf-8'))['main']
            if not isinstance(main,str) or not main or Path(main).is_absolute() or Path(main).drive or '..'in Path(main).parts:
                raise ValueError('invalid relative entry')
            entry = (app/main).resolve()
            if not entry.is_relative_to(app.resolve()) or not entry.is_file():
                raise ValueError('invalid entry')
        except (OSError,ValueError,KeyError,TypeError):
            raise ValueError('程序目录缺少有效的 app.asar 或 resources/app/package.json 入口')from None
    if mode not in {'offline-local','local-reconstructed'} or profile_layout not in {'legacy','workspace'}:
        raise ValueError('不支持的程序模式或数据布局')
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('输入和输出目录不得重叠')
    files = {}
    for item in sorted(source.rglob('*')):
        if item.is_symlink() or item.is_junction():
            raise ValueError('程序目录包含链接，请先检查：' + str(item))
        if not item.is_file():
            continue
        rel = item.relative_to(source)
        # Account/profile folders and diagnostics do not belong in a payload.
        if any(p.casefold() in {'本地数据', 'profile', 'userdata', 'user data', 'logs', 'crashpad'} for p in rel.parts):
            continue
        if item.suffix.lower() in {'.log', '.jsonl', '.dmp'} or item.name.lower() == 'uninst.exe':
            continue
        with item.open('rb') as stream:
            files[rel.as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    payload = destination / '程序'
    manifest = destination / 'module.json'
    if destination.exists():
        existing=json.loads(manifest.read_text('utf-8'))if manifest.is_file()else {}
        if (existing.get('files')!=files or existing.get('executable')!=executable_name or
                existing.get('mode')!=mode or existing.get('profileLayout','legacy')!=profile_layout):
            raise FileExistsError('目标目录已存在且内容不同，不覆盖：' + str(destination))
        for name, sha in files.items():
            with (payload / name).open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                    raise ValueError('已有程序文件校验失败：' + name)
        return {'files': len(files), 'destination': str(destination), 'unchanged': True}
    payload.mkdir(parents=True)
    for name, sha in files.items():
        target = payload / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != sha:
                raise ValueError('复制校验失败：' + name)
    manifest.write_text(json.dumps({'format': 1, 'name': '小v喵', 'executable': executable.name,
        'mode': mode, 'profileLayout':profile_layout, 'files': files}, ensure_ascii=False, indent=2), 'utf-8')
    return {'files': len(files), 'destination': str(destination), 'unchanged': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=Path('D:/小v喵/本地初始化修复_20261103/程序'))
    parser.add_argument('--destination', type=Path, default=ROOT / 'modules/xiaovmiao')
    parser.add_argument('--executable',default='vcat_local_init.exe')
    parser.add_argument('--mode',default='offline-local',choices=['offline-local','local-reconstructed'])
    parser.add_argument('--profile-layout',default='legacy',choices=['legacy','workspace'])
    options = parser.parse_args()
    print(json.dumps(prepare(options.source, options.destination,options.executable,options.mode,options.profile_layout), ensure_ascii=False))
