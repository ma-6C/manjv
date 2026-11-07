"""Independent companion launcher with explicit, persistent user-data selection."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time


def checked_executable(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError('请选择小v喵主程序的完整路径')
    path = Path(value.strip().strip('"')).expanduser()
    if not path.is_absolute() or str(path).startswith(('\\\\', '//')):
        raise ValueError('请选择本机磁盘上的 EXE 文件')
    path = path.resolve()
    if path.suffix.lower() != '.exe' or not path.is_file():
        raise ValueError('未找到程序，请选择小v喵的 EXE 文件')
    if not (path.parent / 'resources/app.asar').is_file():
        app = path.parent / 'resources/app'
        try:
            package = json.loads((app / 'package.json').read_text('utf-8'))
            main = package.get('main') if isinstance(package, dict) else None
            entry = Path(main) if isinstance(main, str) and main.strip() else None
            if entry is None or entry.is_absolute() or entry.drive or '..' in entry.parts:
                raise ValueError('invalid entry')
            target = (app / entry).resolve()
            if not target.is_relative_to(app.resolve()) or not target.is_file():
                raise ValueError('missing entry')
        except (OSError, ValueError, TypeError):
            raise ValueError('程序目录缺少有效的 app.asar 或 resources/app 启动入口，请保留小v喵的完整目录') from None
    return path


def manifest_executable(value):
    """A payload's executable is one filename, never an external path."""
    if not isinstance(value, str) or not value or any(c in value for c in '/\\:'):
        return None
    name = Path(value)
    return value if len(name.parts) == 1 and name.name == value and name.suffix.lower() == '.exe' else None


class Manager:
    def __init__(self, home, app_home):
        self.home = Path(home); self.app_home = Path(app_home)
        self.bundle = self.app_home / 'modules/xiaovmiao'
        self.settings_file = self.home / 'xiaovmiao.json'
        self.lock = threading.RLock()
        self.process = None; self.opened_at = ''; self.runtime = ''; self.profile = ''
        try:
            value = json.loads(self.settings_file.read_text('utf-8'))
            self.path = value.get('executable', '') if isinstance(value, dict) else ''
            self.profile = value.get('profile', '') if isinstance(value, dict) else ''
        except (OSError, ValueError):
            self.path = ''

    def candidates(self):
        paths = [self.path, os.environ.get('MANJU_XIAOVMIAO_EXE', '')]
        try:
            manifest = json.loads((self.bundle / 'module.json').read_text('utf-8'))
            name = manifest_executable(manifest.get('executable')) if isinstance(manifest, dict) else None
            if name:
                paths.append(str(self.bundle / '程序' / name))
        except (OSError, ValueError):
            pass
        for root in (self.bundle / '程序', self.app_home.parent / '小v喵', Path('D:/小v喵')):
            paths.extend(str(root / n) for n in ('vcat_local_init.exe', 'vcat-local.exe', '小V猫.exe',
                '本地初始化修复_20261103/程序/vcat_local_init.exe'))
        result = []
        for item in paths:
            try:
                p = checked_executable(item)
                if str(p) not in result:
                    result.append(str(p))
            except ValueError:
                pass
        return result

    def executable(self):
        # Never silently switch installations after a configured path is moved.
        if self.path:
            return checked_executable(self.path)
        paths = self.candidates()
        if not paths:
            raise ValueError('未找到小v喵，请在本页设置中选择程序')
        return checked_executable(paths[0])

    def status(self):
        with self.lock:
            try:
                path = self.executable(); available = True; error = ''
            except ValueError as exc:
                path = Path(self.path) if self.path else None
                available = False; error = str(exc)
            mode='external'
            if path and path.is_relative_to(self.bundle.resolve()):
                try:mode=json.loads((self.bundle/'module.json').read_text('utf-8')).get('mode','local')
                except (OSError,ValueError,AttributeError):mode='local'
            return {'available': available, 'executable': str(path) if path else '',
                'bundled': bool(path and path.is_relative_to(self.bundle.resolve())),
                'candidates': self.candidates(), 'supported': os.name == 'nt',
                'localMode': bool(path and (mode.startswith('local') or mode=='external' and path.name.lower()=='vcat_local_init.exe')),
                'accountFlow': 'original-online' if mode=='standard-account-flow' else 'local' if mode.startswith('local') else 'external',
                'processRunning': bool(self.process and self.process.poll() is None),
                'openedAt': self.opened_at, 'profile': self.profile, 'error': error}

    def configure(self, value, profile=''):
        with self.lock:
            # Empty selection restores the portable bundled default.
            path = str(checked_executable(value)) if value else ''
            if profile:
                p=Path(profile)
                if not p.is_absolute() or not p.is_dir() or str(p).startswith(('\\\\','//')):
                    raise ValueError('未找到小v喵原有的本地数据目录')
                profile=str(p.resolve())
            self.home.mkdir(parents=True, exist_ok=True)
            temp = self.settings_file.with_suffix('.tmp')
            temp.write_text(json.dumps({'executable': path,'profile':profile}, ensure_ascii=False, indent=2), 'utf-8')
            temp.replace(self.settings_file)
            self.path = path; self.profile = profile
            return self.status()

    def prepare_runtime(self, path):
        if not path.is_relative_to(self.bundle.resolve()):
            return path
        # The supplied local build keeps its database next to its program folder.
        # Run a per-user copy so Program Files and the shipped payload stay clean.
        try:
            manifest = json.loads((self.bundle / 'module.json').read_text('utf-8'))
            files = manifest['files']
            if not isinstance(files, dict) or not files:
                raise ValueError('empty manifest')
            if manifest.get('profileLayout', 'legacy') not in ('legacy', 'workspace'):
                raise ValueError('invalid profile layout')
            for name, digest in files.items():
                rel = Path(name)
                if rel.is_absolute() or '..' in rel.parts or not isinstance(digest, str) or len(digest) != 64:
                    raise ValueError('invalid manifest')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError('小v喵随附程序清单缺失或无效，请重新准备模块') from exc
        key = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
        root = self.home / 'components/xiaovmiao' / key
        destination = root / '程序'
        target = destination / path.name
        marker = root / 'ready.json'
        if marker.is_file() and target.is_file():
            self.runtime = str(target)
            return checked_executable(str(target))
        root.mkdir(parents=True, exist_ok=True)
        # A fixed staging name plus the manager lock allows retry after an
        # interrupted copy, without ever touching a prior version's local data.
        stage = root / 'preparing'
        stage.mkdir(exist_ok=True)
        def copy_verified(item):
            name, digest = item
            source = self.bundle / '程序' / name
            dest = stage / name
            if not source.resolve().is_relative_to((self.bundle / '程序').resolve()):
                raise ValueError('小v喵程序清单路径无效')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            with dest.open('rb') as stream:
                if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                    raise ValueError('小v喵程序文件校验失败：' + name)
        if len(files) >= 512:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for _ in pool.map(copy_verified, files.items()):
                    pass
        else:
            for item in files.items():
                copy_verified(item)
        if destination.exists():
            # Never replace an installation that may contain live app writes.
            raise ValueError('小v喵运行目录不完整，请联系维护人员检查：' + str(destination))
        stage.rename(destination)
        marker.write_text(json.dumps({'payload': key, 'profileLayout': manifest.get('profileLayout', 'legacy')}), 'utf-8')
        self.runtime = str(target)
        return checked_executable(str(target))

    def bundled_profile(self, runtime):
        """Keep the selected database when a changed payload gets a new hash."""
        if self.profile:
            return
        try:
            manifest = json.loads((self.bundle / 'module.json').read_text('utf-8'))
            layout = manifest.get('profileLayout', 'legacy')
            if layout not in ('legacy', 'workspace'):
                raise ValueError('unsupported layout')
        except (OSError, ValueError, AttributeError):
            raise ValueError('小v喵数据布局清单无效，请先检查模块') from None
        database = 'workspace/.vcat/offline-local/vcat.db' if layout == 'workspace' else '.vcat/offline-local/vcat.db'
        home=self.home/'components/xiaovmiao'
        current=runtime.parent.parent/'本地数据'
        candidates=[]
        if home.is_dir():
            for root in home.iterdir():
                if not root.is_dir() or root.is_symlink() or root.is_junction():continue
                if len(root.name)!=16 or any(c not in '0123456789abcdef' for c in root.name):continue
                profile=root/'本地数据'
                if not (profile/database).is_file():continue
                try:
                    marker=json.loads((root/'ready.json').read_text('utf-8'))
                    if not isinstance(marker,dict) or marker.get('payload')!=root.name:raise ValueError('wrong payload')
                except (OSError,ValueError,TypeError):
                    raise ValueError('小v喵历史运行目录清单无效，原有数据已保留，请先检查目录') from None
                if marker.get('profileLayout', 'legacy') != layout:continue
                candidates.append(profile.resolve())
        if current.resolve() in candidates:
            profile=current
        elif len(candidates)==1:
            profile=candidates[0]
        elif len(candidates)>1:
            raise ValueError('检测到多份小v喵历史数据，未新建空库；请先指定要继续使用的本地数据目录')
        else:
            profile=current
            profile.mkdir(parents=True,exist_ok=True)
        self.configure(self.path,str(profile))

    def open(self):
        with self.lock:
            if os.name != 'nt':
                raise ValueError('小v喵桌面程序需要在 Windows 上打开')
            selected=self.executable()
            path = self.prepare_runtime(selected)
            if selected.is_relative_to(self.bundle.resolve()):self.bundled_profile(path)
            env = os.environ.copy()
            for key in ('ELECTRON_RUN_AS_NODE', 'NODE_OPTIONS', 'NODE_PATH',
                        'VCAT_BASELINE', 'VCAT_BOOT_ONLY', 'VCAT_TEST_EXIT_MS',
                        'VCAT_NETWORK_PROBE', 'VCAT_ACCOUNT_PHASE'):
                env.pop(key, None)
            if self.profile:
                profile=Path(self.profile)
                if not profile.is_dir():raise ValueError('小v喵原有的本地数据目录已移动，请先恢复目录')
                env['MANJU_XIAOVMIAO_PROFILE']=str(profile)
            self.process = subprocess.Popen([str(path)], cwd=str(path.parent), env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            # A zero exit may mean Electron handed off to its existing instance.
            try:
                code = self.process.wait(timeout=.4)
            except subprocess.TimeoutExpired:
                code = None
            if code not in (None, 0):
                raise ValueError('小v喵启动失败，退出码：' + str(code))
            self.opened_at = time.strftime('%Y-%m-%d %H:%M:%S')
            return {**self.status(), 'launchRequested': True,
                    'message': '已发送打开请求，请在小v喵窗口中继续操作'}
