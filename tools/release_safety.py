"""Fail closed before a build can replace deliveries or collect local profiles."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PureWindowsPath
import re
import shutil


def new_release_destination(root, version):
    if not re.fullmatch(r'v\d+\.\d+\.\d+', version):
        raise ValueError('版本号无效')
    root = Path(root).resolve()
    release = root / 'release'
    version_dir = release / version
    if (release.is_symlink() or release.is_junction() or version_dir.is_symlink() or
            version_dir.is_junction() or not version_dir.resolve().is_relative_to(root)):
        raise ValueError('发行目录包含链接或超出工作区')
    if version_dir.exists() and (not version_dir.is_dir() or any(version_dir.iterdir())):
        raise FileExistsError('版本目录已存在且非空，请指定新的 --version，保留原发行文件：' + str(version_dir))
    return version_dir / '漫剧工坊'


def verify_manifest_file_set(destination, manifest):
    """Reject unsigned extra files before NSIS recursively embeds a build."""
    destination = Path(destination)
    expected = [item['path'] for item in manifest['files']]
    if not expected or len(expected) != len(set(name.casefold() for name in expected)):
        raise ValueError('发行清单为空或包含重复路径')
    actual = set()
    for path in destination.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('发行文件不得包含链接：' + str(path))
        if path.is_file() and path != destination / 'integrity.json':
            actual.add(path.relative_to(destination).as_posix())
    if actual != set(expected):
        raise ValueError('发行目录含未签署的额外文件或缺失文件，停止生成安装包')


def companion_files(module):
    """Verify the complete input set before a single program file is bundled."""
    module = Path(module)
    manifest = module / 'module.json'
    if not manifest.is_file():
        if module.exists() and any(module.iterdir()):
            raise ValueError('小v喵模块存在但缺少清单，停止打包')
        return None
    if module.is_symlink() or module.is_junction() or manifest.is_symlink():
        raise ValueError('小v喵模块不得包含链接')
    encoded = manifest.read_bytes()
    data = json.loads(encoded)
    files = data.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('小v喵程序清单为空')
    program = module / '程序'
    if program.is_symlink() or program.is_junction():
        raise ValueError('小v喵程序目录不得为链接')
    expected = {}
    names = set()
    for name, digest in files.items():
        if not isinstance(name, str):
            raise ValueError('小v喵程序清单路径无效')
        relative = PureWindowsPath(name)
        if (not name or relative.is_absolute() or relative.drive or
                '..' in relative.parts or ':' in name or '\\' in name or
                name.casefold() in names or not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest)):
            raise ValueError('小v喵程序清单路径或哈希无效')
        names.add(name.casefold())
        if any(part.casefold() in {'本地数据', 'profile', 'userdata', 'user data', 'logs', 'crashpad'} for part in relative.parts):
            raise ValueError('小v喵清单含本地用户数据：' + name)
        expected[name] = digest
    if data.get('executable') not in expected or '/' in data['executable'] or not data['executable'].lower().endswith('.exe'):
        raise ValueError('小v喵清单缺少有效的主程序')
    actual = set()
    for path in program.rglob('*'):
        if path.is_symlink() or path.is_junction():
            raise ValueError('小v喵程序包含链接：' + str(path))
        if path.is_file():
            actual.add(path.relative_to(program).as_posix())
    if actual != set(expected):
        raise ValueError('小v喵程序文件集合与清单不同；缺失或额外文件不能随包发送')

    def verify(item):
        name, digest = item
        with (program / name).open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('小v喵程序文件校验失败：' + name)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(verify, expected.items()))
    return encoded, expected


def copy_companion(module, destination, verified=None):
    verified = companion_files(module) if verified is None else verified
    if verified is None:
        return
    encoded, files = verified
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError('不覆盖已有小v喵发行目录：' + str(destination))
    for name, digest in files.items():
        source, target = Path(module) / '程序' / name, destination / '程序' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        with target.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('小v喵程序复制校验失败：' + name)
    (destination / 'module.json').write_bytes(encoded)
