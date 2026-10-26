"""Conservative handoff to a registered draft in the real Jianying editor.

This uses native accessibility identities, never editor index forgery or a
screen-coordinate template. Opening an application is not project validation.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from pathlib import Path

import jianying_projects

_OPEN_LOCK = threading.Lock()
_TITLE_IDS = ('draft_name', 'draftname', 'project_name', 'projectname',
              'project_title', 'projecttitle', 'editor.title', 'titlebar.title')
_TITLE_DESCRIPTIONS = ('MainWindowTitleBarTitle:', 'MainWindowTitleBarDraftName:',
                       'MainWindowTitleBarProjectName:')


def _description(control):
    try:
        return str(control.GetPropertyValue(30159) or '')
    except Exception:
        return ''


def _tree(root):
    stack = [(root, 0)]
    count = 0
    while stack and count < 650:
        control, depth = stack.pop()
        count += 1
        yield control
        if depth < 18:
            try:
                stack.extend((child, depth + 1) for child in reversed(control.GetChildren()))
            except Exception:
                pass


def _editor_title(control, name):
    identity = str(getattr(control, 'AutomationId', '') or '').casefold()
    description = _description(control)
    text = str(getattr(control, 'Name', '') or '').strip()
    return (text == name and any(token in identity for token in _TITLE_IDS)) or any(
        description == prefix + name for prefix in _TITLE_DESCRIPTIONS)


class NativeBackend:
    """Only invokes an exact, unique accessibility node of a signed app."""

    def _roots(self, auto):
        if os.name != 'nt':
            return []
        from ctypes import wintypes as wt
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        kernel.OpenProcess.restype = wt.HANDLE
        kernel.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ctypes.POINTER(wt.DWORD)]
        kernel.CloseHandle.argtypes = [wt.HANDLE]
        found = []
        for control in auto.GetRootControl().GetChildren():
            try:
                if control.IsOffscreen or not control.NativeWindowHandle:
                    continue
                process = kernel.OpenProcess(0x1000, False, control.ProcessId)
                if not process:
                    continue
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    length = wt.DWORD(len(buffer))
                    if not kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
                        continue
                    executable = Path(buffer.value)
                finally:
                    kernel.CloseHandle(process)
                if executable.name.casefold() != 'jianyingpro.exe' or not jianying_projects._verified_editor(executable):
                    continue
                found.append(control)
            except Exception:
                continue
        return found

    def _inspect(self, auto, name):
        homes, editors, matches = [], [], []
        for root in self._roots(auto):
            controls = list(_tree(root))
            identities = [str(getattr(item, 'AutomationId', '') or '') for item in controls]
            editor = any('main_timeline_root' in identity for identity in identities) and 'editor.export' in identities
            root_title = str(root.Name or '').strip()
            title_match = root_title in (name + ' - 剪映专业版', name + ' — 剪映专业版') or any(
                _editor_title(item, name) for item in controls)
            if editor:
                item = {'mode': 'target_editor' if title_match else 'other_editor',
                        'windowId': str(root.NativeWindowHandle), 'pid': root.ProcessId,
                        'title': root_title, 'timelineVerified': True, 'projectTitleVerified': title_match}
                editors.append(item)
                if title_match:
                    matches.append(item)
                continue
            home = str(root.AutomationId or '') == 'HomeWindow' or 'homepage' in str(root.ClassName or '').casefold()
            if not home:
                continue
            targets = [item for item in controls if _description(item) == 'HomePageDraftTitle:' + name]
            homes.append({'mode': 'home', 'windowId': str(root.NativeWindowHandle),
                          'pid': root.ProcessId, 'targetCount': len(targets), '_targets': targets})
        # Never switch away from or close another active editor project.
        if len(matches) == 1 and len(editors) == 1:
            return matches[0]
        if editors:
            return {'mode': 'other_editor' if not matches else 'ambiguous', 'windowId': editors[0]['windowId']}
        if len(homes) == 1:
            return homes[0]
        return {'mode': 'ambiguous' if homes else 'unavailable'}

    def inspect(self, name, editor):
        if os.name != 'nt':
            return {'mode': 'unsupported'}
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            result = self._inspect(auto, name)
            return {key: value for key, value in result.items() if not key.startswith('_')}

    def open_target(self, snapshot, name, editor):
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread():
            fresh = self._inspect(auto, name)
            if fresh.get('mode') != 'home' or fresh.get('windowId') != snapshot.get('windowId') or fresh.get('targetCount') != 1:
                return False
            target = fresh['_targets'][0]
            # The documented older bridge identifies the title child. Some
            # versions expose the action on its direct parent instead.
            candidates = [target]
            try:
                parent = target.GetParentControl()
                titles = [_description(item) for item in _tree(parent)] if parent else []
                titles = [value for value in titles if value.startswith('HomePageDraftTitle:')]
                if titles == ['HomePageDraftTitle:' + name]:
                    candidates.append(parent)
            except Exception:
                pass
            for control in candidates:
                try:
                    pattern = control.GetInvokePattern()
                except Exception:
                    pattern = None
                if pattern:
                    pattern.Invoke()
                    return True
                try:
                    legacy = control.GetLegacyIAccessiblePattern()
                except Exception:
                    legacy = None
                if legacy and str(legacy.DefaultAction or '').strip():
                    # Once invoked, an exception has an unknown outcome. Let
                    # the caller observe again rather than trying a parent.
                    legacy.DoDefaultAction()
                    return True
            return False

    def launch(self, folder, options):
        return jianying_projects.open_in_editor(folder, options)


def open_registered_project(import_result, options=None, cancel_event=None, *, backend=None, wait_timeout=12):
    """Open only a uniquely identified registered draft, or explain the gate.

    ``projectOpened`` requires an observed real timeline, export control and
    exact project title. This does not assert playback, official acceptance,
    or the human confirmation required for screenshot association.
    """
    if not isinstance(import_result, dict) or not isinstance(import_result.get('directory'), str):
        raise ValueError('缺少已登记的剪映工程目录')
    folder = Path(import_result['directory']).expanduser().resolve()
    index, _ = jianying_projects._open_index(folder)
    name = str(index.get('name') or '')
    if not name or import_result.get('name') != name or not index.get('editorImportedAt'):
        raise ValueError('工程名称或导入登记不匹配，请先导入已校验的工程')
    if (folder / '未完成工程.txt').exists() or (folder / '未完成导入.txt').exists():
        raise ValueError('工程尚未完成校验')
    opts = jianying_projects.options(options)
    editor = jianying_projects.status(opts)
    base = {'directory': str(folder), 'name': name, 'appLaunched': False,
            'projectOpened': False, 'editorValidated': False, 'timelineVerified': False,
            'projectConfirmedByUser': False, 'route': 'tracks'}

    def waiting(message, reason='editor_project'):
        return {**base, 'status': 'waiting_action', 'reason': reason, 'message': message}

    if not editor.get('editorInstalled') or not editor.get('editorSignatureVerified'):
        return waiting(editor.get('note') or '请安装并选择官方剪映主程序', 'editor_missing')
    if cancel_event and cancel_event.is_set():
        return {**base, 'status': 'cancelled', 'message': '剪映交接已停止，已导入工程保留'}
    if not _OPEN_LOCK.acquire(blocking=False):
        return waiting('另一个剪映工程正在交接，请稍后继续', 'editor_busy')
    try:
        native = backend or NativeBackend()
        deadline = time.monotonic() + max(0, min(float(wait_timeout), 30))
        launched = False
        invoked = False
        while True:
            if cancel_event and cancel_event.is_set():
                return {**base, 'status': 'cancelled', 'message': '剪映交接已停止，已导入工程保留'}
            try:
                snapshot = native.inspect(name, editor)
            except Exception:
                return waiting('无法读取剪映的原生工程控件。请在剪映打开「' + name + '」后继续')
            mode = snapshot.get('mode')
            if mode == 'target_editor' and snapshot.get('timelineVerified') is True and snapshot.get('projectTitleVerified') is True:
                return {**base, 'status': 'completed', 'projectOpened': True, 'timelineVerified': True,
                        'projectTitleVerified': True, 'windowId': str(snapshot.get('windowId', '')),
                        'pid': snapshot.get('pid'), 'message': '已在官方剪映定位本工程的真实时间线；下一步核对并获取官方窗口截图'}
            if mode == 'other_editor':
                return waiting('剪映当前打开了其他工程。请先自行保存，再打开「' + name + '」后继续')
            if mode in ('ambiguous', 'unsupported'):
                return waiting('无法唯一确认剪映工程窗口，请在官方剪映打开「' + name + '」后继续')
            if mode == 'home' and not invoked:
                if snapshot.get('targetCount') != 1:
                    return waiting('请在剪映草稿列表打开「' + name + '」。当前版本未提供唯一可识别的草稿入口')
                try:
                    invoked = bool(native.open_target(snapshot, name, editor))
                except Exception:
                    # An action exception may have taken effect. Observe once
                    # again; never blindly repeat the native action.
                    invoked = True
                if not invoked:
                    return waiting('已找到草稿，但剪映未提供可调用的原生打开动作。请手动打开「' + name + '」后继续')
            elif mode == 'unavailable' and not launched:
                try:
                    result = native.launch(folder, opts)
                    launched = True
                    base['appLaunched'] = result.get('appLaunched') is True
                except Exception as error:
                    return waiting('启动官方剪映失败：' + str(error)[:300], 'editor_launch')
            if time.monotonic() >= deadline:
                return waiting('工程已交给剪映，尚未读到可核验的工程标题和时间线。请打开「' + name + '」后继续')
            if cancel_event:
                cancel_event.wait(.25)
            else:
                time.sleep(.25)
    finally:
        _OPEN_LOCK.release()
