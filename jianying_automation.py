"""Conservative handoff to a registered draft in the real Jianying editor.

The optional mouse fallback uses the current verified control's clickable point.
Opening an application is not project validation.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from pathlib import Path
from contextlib import contextmanager

import jianying_projects
import jianying_registry
import jianying_visual

_OPEN_LOCK = threading.Lock()
_CAPTURE_LOCK = threading.Lock()
_TITLE_IDS = ('draft_name', 'draftname', 'project_name', 'projectname',
              'project_title', 'projecttitle', 'editor.title', 'titlebar.title')
_TITLE_DESCRIPTIONS = ('MainWindowTitleBarTitle:', 'MainWindowTitleBarDraftName:',
                       'MainWindowTitleBarProjectName:')


@contextmanager
def physical_pixels():
    previous=None
    if os.name=='nt':
        user=ctypes.WinDLL('user32',use_last_error=True)
        if hasattr(user,'SetThreadDpiAwarenessContext'):
            user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
            user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
            previous=user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    try:yield
    finally:
        if previous:user.SetThreadDpiAwarenessContext(previous)


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


def media_missing(root):
    for control in _tree(root):
        try:
            if control.IsOffscreen:continue
            text=str(control.Name or '').strip()
            if 'Media Not Found' in text or '检测到以下媒体丢失' in text or text in ('媒体丢失','重新链接媒体'):
                return True
            if text in ('链接媒体','Link Media') and str(control.ControlTypeName)=='WindowControl':return True
        except Exception:continue
    return False


def _editor_title(control, name):
    identity = str(getattr(control, 'AutomationId', '') or '').casefold()
    description = _description(control)
    text = str(getattr(control, 'Name', '') or '').strip()
    return (text == name and any(token in identity for token in _TITLE_IDS)) or any(
        description == prefix + name for prefix in _TITLE_DESCRIPTIONS)


class NativeBackend:
    """Invokes a unique native target, with an optional guarded mouse fallback."""

    def __init__(self, allow_mouse=False):
        self.allow_mouse=allow_mouse
        self.root_diagnostic={}

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
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.IsWindowVisible.argtypes=[wt.HWND]
        user.GetWindowThreadProcessId.argtypes=[wt.HWND,ctypes.POINTER(wt.DWORD)]
        handles=[]
        callback_type=ctypes.WINFUNCTYPE(wt.BOOL,wt.HWND,wt.LPARAM)
        @callback_type
        def collect(hwnd,lparam):
            if user.IsWindowVisible(hwnd):handles.append(hwnd)
            return True
        user.EnumWindows.argtypes=[callback_type,wt.LPARAM]
        user.EnumWindows(collect,0)
        self.root_diagnostic={'visible':len(handles),'readable':0,'jianying':0,'candidates':[],'errors':[]}
        # Enumerate native handles first. A desktop-wide UIA traversal can
        # stall on unrelated applications before Jianying is even launched.
        for hwnd in handles:
            try:
                pid=wt.DWORD()
                user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
                process = kernel.OpenProcess(0x1000, False, pid.value)
                if not process:
                    continue
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    length = wt.DWORD(len(buffer))
                    if not kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
                        continue
                    executable = Path(buffer.value)
                    self.root_diagnostic['readable']+=1
                finally:
                    kernel.CloseHandle(process)
                if 'jianying' in str(executable).casefold():self.root_diagnostic['candidates'].append(str(executable))
                if executable.name.casefold() != 'jianyingpro.exe' or not jianying_projects._verified_editor(executable):
                    continue
                self.root_diagnostic['jianying']+=1
                control=auto.ControlFromHandle(hwnd)
                found.append(control)
            except Exception as error:
                self.root_diagnostic['errors'].append(str(error)[:300])
                continue
        return found

    def _inspect(self, auto, name):
        homes, editors, matches = [], [], []
        diagnostic=[]
        for root in self._roots(auto):
            if media_missing(root):return {'mode':'media_missing','windowId':str(root.NativeWindowHandle)}
            controls = list(_tree(root))
            identities = [str(getattr(item, 'AutomationId', '') or '') for item in controls]
            diagnostic.append({'window':root.NativeWindowHandle,'name':str(root.Name or ''),'class':str(root.ClassName or ''),
                               'id':str(root.AutomationId or ''),'controls':len(controls),'identities':identities[:12]})
            editor = any('main_timeline_root' in identity for identity in identities) and 'editor.export' in identities
            qt_editor=jianying_visual.qt_editor_surface(root,controls)
            root_title = str(root.Name or '').strip()
            title_match = root_title in (name + ' - 剪映专业版', name + ' — 剪映专业版') or any(
                _editor_title(item, name) for item in controls)
            identity={'projectIdentityVerified':title_match,'projectTitleVerified':title_match,
                      'projectMatchMethod':'native_project_title'}
            if qt_editor and not title_match:identity=jianying_visual.visible_identity(root,name)
            if editor or qt_editor:
                matched=identity['projectIdentityVerified']
                item = {'mode': 'target_editor' if matched else 'other_editor',
                        'windowId': str(root.NativeWindowHandle), 'pid': root.ProcessId,
                        'title': root_title, 'timelineVerified': True,**identity}
                editors.append(item)
                if matched:
                    matches.append(item)
                continue
            home = str(root.AutomationId or '') == 'HomeWindow' or 'homepage' in str(root.ClassName or '').casefold()
            if not home:
                continue
            targets = [item for item in controls if _description(item) == 'HomePageDraftTitle:' + name]
            homes.append({'mode': 'home', 'windowId': str(root.NativeWindowHandle),
                          'pid': root.ProcessId, 'targetCount': len(targets), '_targets': targets, '_root':root})
        self.root_diagnostic['roots']=diagnostic
        # Never switch away from or close another active editor project.
        if len(matches) == 1 and len(editors) == 1:
            return matches[0]
        if editors:
            return {**editors[0],'mode': 'other_editor' if not matches else 'ambiguous'}
        if len(homes) == 1:
            return homes[0]
        return {'mode': 'ambiguous' if homes else 'unavailable'}

    def inspect(self, name, editor):
        if os.name != 'nt':
            return {'mode': 'unsupported'}
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread(),physical_pixels():
            result = self._inspect(auto, name)
            return {key: value for key, value in result.items() if not key.startswith('_')}

    def foreground_for_inspection(self):
        """A requested open/capture may focus one verified official editor.

        Identity still has to match afterwards; this does not close or edit
        an unrecognized project and is never called by passive status polling.
        """
        import uiautomation as auto
        from ctypes import wintypes as wt
        with auto.UIAutomationInitializerInThread(),physical_pixels():
            roots=[root for root in self._roots(auto) if str(root.AutomationId or '')=='MainWindow']
            if len(roots)!=1:return
            root=roots[0];user=ctypes.WinDLL('user32')
            user.IsIconic.argtypes=[wt.HWND];user.ShowWindow.argtypes=[wt.HWND,ctypes.c_int]
            if user.IsIconic(wt.HWND(root.NativeWindowHandle)):user.ShowWindow(wt.HWND(root.NativeWindowHandle),9)
            root.SetActive(waitTime=.2)

    def open_target(self, snapshot, name, editor):
        import uiautomation as auto
        with auto.UIAutomationInitializerInThread(),physical_pixels():
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
            if self.allow_mouse:
                root=fresh['_root']
                root.SetActive(waitTime=0.1)
                again=self._inspect(auto,name)
                if again.get('mode')!='home' or again.get('targetCount')!=1 or again.get('windowId')!=snapshot.get('windowId'):return False
                target=again['_targets'][0];click_targets=[target]
                parent=target.GetParentControl()
                titles=[_description(item) for item in _tree(parent)] if parent else []
                if [text for text in titles if text.startswith('HomePageDraftTitle:')]==['HomePageDraftTitle:'+name]:click_targets.append(parent)
                for candidate in click_targets:
                    x,y,clickable=candidate.GetClickablePoint()
                    if not clickable:continue
                    if auto.GetForegroundWindow()!=root.NativeWindowHandle:return False
                    hit=auto.ControlFromPoint(x,y)
                    if hit.ProcessId!=root.ProcessId:return False
                    target_id=tuple(candidate.GetRuntimeId());confirmed=False
                    if not target_id:continue
                    for _ in range(12):
                        if not hit:break
                        if tuple(hit.GetRuntimeId())==target_id:
                            confirmed=True;break
                        hit=hit.GetParentControl()
                    if not confirmed:continue
                    rect=root.BoundingRectangle
                    root.DoubleClick(x-rect.left,y-rect.top,simulateMove=False,waitTime=.1)
                    return True
            return False

    def launch(self, folder, options):
        return jianying_projects.open_in_editor(folder, options)

    def close_home(self,snapshot,event):
        """Normally exit an idle home so the refreshed index is read at launch."""
        import uiautomation as auto
        from ctypes import wintypes as wt
        with auto.UIAutomationInitializerInThread(),physical_pixels():
            roots=self._roots(auto)
            fresh=self._inspect(auto,'')
            if len(roots)!=1 or fresh.get('mode')!='home' or fresh.get('windowId')!=snapshot.get('windowId'):return False
            if event.is_set():raise InterruptedError('工程图已暂停')
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.PostMessageW.argtypes=[wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM]
            user.PostMessageW.restype=wt.BOOL
            if not user.PostMessageW(wt.HWND(int(fresh['windowId'])),0x10,0,0):return False
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if event.wait(.25):raise InterruptedError('工程图已暂停')
            if not jianying_registry.running():return True
        return False

    def open_first(self,snapshot,name,editor,folder):
        """Open the indexed first draft by its rendered cover, without scrolling."""
        if not self.allow_mouse:return False
        if not jianying_registry.first_draft(folder):return False
        from PIL import ImageGrab
        import json
        import uiautomation as auto
        descriptor=Path(folder)/'manju-card.json'
        if not descriptor.is_file():return False
        marker=json.loads(descriptor.read_text('utf-8'))
        code=jianying_registry.token(folder,name)
        if marker.get('token')!=code or marker.get('active') is not True:return False
        with auto.UIAutomationInitializerInThread(),physical_pixels():
            fresh=self._inspect(auto,name)
            if fresh.get('mode')!='home' or fresh.get('windowId')!=snapshot.get('windowId'):return False
            root=fresh['_root'];root.SetActive(waitTime=.15)
            if auto.GetForegroundWindow()!=root.NativeWindowHandle:return False
            rect=root.BoundingRectangle
            box=(rect.left,rect.top,rect.right,rect.bottom)
            point=jianying_registry.find_mark(ImageGrab.grab(bbox=box,all_screens=True),code)
            if point:
                # Re-observe the thumbnail before sending the single click.
                again=jianying_registry.find_mark(ImageGrab.grab(bbox=box,all_screens=True),code)
                if again!=point:return False
                x,y=point[0]+rect.left,point[1]+rect.top
                hit=auto.ControlFromPoint(x,y)
                if not hit or hit.ProcessId!=root.ProcessId or auto.GetForegroundWindow()!=root.NativeWindowHandle:return False
                if not jianying_registry.first_draft(folder):return False
                root.DoubleClick(x-rect.left,y-rect.top,simulateMove=False,waitTime=.1);return True
        return False

    def open_marked(self,snapshot,name,editor,folder):
        return self.open_first(snapshot,name,editor,folder)


def open_registered_project(import_result, options=None, cancel_event=None, *, backend=None, wait_timeout=60):
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
        native = backend or NativeBackend(opts['mouseOpen'])
        focus=getattr(native,'foreground_for_inspection',None)
        if focus:focus()
        registration={}
        if opts['registerIndex'] and backend is None:
            initial=native.inspect(name,editor)
            if initial.get('mode')=='home':
                if not native.close_home(initial,cancel_event or threading.Event()):
                    return waiting('剪映首页尚未正常退出，请处理提示后继续；目标草稿和已完成记录已保留')
            elif initial.get('mode')=='other_editor':
                if initial.get('identityDiagnostic'):return waiting('暂未核对到目标工程：'+initial['identityDiagnostic'])
                return waiting('剪映当前打开了其他工程，请先保存退出后继续生成工程图')
            if initial.get('mode')!='target_editor':registration=jianying_registry.register(folder,opts)
        deadline = time.monotonic() + max(0, min(float(wait_timeout), 90))
        launched = False
        invoked = False
        action_error=''
        while True:
            if cancel_event and cancel_event.is_set():
                return {**base, 'status': 'cancelled', 'message': '剪映交接已停止，已导入工程保留'}
            try:
                snapshot = native.inspect(name, editor)
            except Exception:
                return waiting('无法读取剪映的原生工程控件。请在剪映打开「' + name + '」后继续')
            mode = snapshot.get('mode')
            if mode == 'target_editor' and snapshot.get('timelineVerified') is True and (snapshot.get('projectTitleVerified') is True or snapshot.get('projectIdentityVerified') is True):
                jianying_registry.restore_cover(folder)
                return {**base, 'status': 'completed', 'projectOpened': True, 'timelineVerified': True,
                        'projectTitleVerified': snapshot.get('projectTitleVerified') is True,
                        'projectIdentityVerified':True,'projectMatchMethod':snapshot.get('projectMatchMethod','native_project_title'),
                        'windowId': str(snapshot.get('windowId', '')),
                        'pid': snapshot.get('pid'), 'message': '已在官方剪映定位本工程的真实时间线；下一步核对并获取官方窗口截图'}
            if mode == 'media_missing':
                return waiting('剪映提示媒体丢失或需要链接媒体。请先使用工程目录中的 Resources 重连素材，确认画面可播放后继续；本次未记为打开成功。','editor_media_missing')
            if mode == 'other_editor':
                if snapshot.get('identityDiagnostic'):return waiting('暂未核对到目标工程：'+snapshot['identityDiagnostic'])
                return waiting('剪映当前打开了其他工程。请先自行保存，再打开「' + name + '」后继续')
            if mode in ('ambiguous', 'unsupported'):
                return waiting('无法唯一确认剪映工程窗口，请在官方剪映打开「' + name + '」后继续')
            if mode == 'home' and not invoked:
                # The current native home exposes no per-card UIA titles.
                # Prefer the target we registered first; a unique cover mark
                # identifies its actual position in the rendered home window.
                if opts['mouseOpen'] and hasattr(native,'open_first'):
                    if not jianying_registry.first_draft(folder):
                        return waiting(registration.get('message') or '本次工程尚未置顶到第一个草稿，请退出剪映后继续')
                    try:invoked=bool(native.open_first(snapshot,name,editor,folder))
                    except Exception as error:
                        invoked=True;action_error=str(error)[:500]
                    if invoked:continue
                    if time.monotonic()>=deadline:
                        return waiting('剪映首页尚未显示可定位的第一个目标草稿，请等待首页加载完成后继续')
                    if cancel_event:cancel_event.wait(.25)
                    else:time.sleep(.25)
                    continue
                if snapshot.get('targetCount') != 1:
                    if opts['mouseOpen'] and hasattr(native,'open_marked') and native.open_marked(snapshot,name,editor,folder):
                        invoked=True
                        continue
                    return waiting(registration.get('message') or '请在剪映草稿列表打开「' + name + '」。未找到唯一匹配的标题或封面标记')
                try:
                    invoked = bool(native.open_target(snapshot, name, editor))
                except Exception:
                    # An action exception may have taken effect. Observe once
                    # again; never blindly repeat the native action.
                    invoked = True
                if not invoked:
                    return waiting('已找到草稿，暂时无法安全自动打开。请手动打开「' + name + '」后继续')
            elif mode == 'unavailable' and not launched:
                try:
                    result = native.launch(folder, opts)
                    launched = True
                    base['appLaunched'] = result.get('appLaunched') is True
                except Exception as error:
                    return waiting('启动官方剪映失败：' + str(error)[:300], 'editor_launch')
            if time.monotonic() >= deadline:
                return waiting(('定位草稿时发生错误：'+action_error+'。' if action_error else '')+'工程已交给剪映，尚未读到可核验的工程标题和时间线。请打开「' + name + '」后继续')
            if cancel_event:
                cancel_event.wait(.25)
            else:
                time.sleep(.25)
    finally:
        _OPEN_LOCK.release()


def prepare_capture(imported,opts,cancel_event=None):
    """Frame only the exactly identified native project; never force-close it."""
    from PIL import ImageChops,ImageGrab,ImageStat
    import uiautomation as auto
    name=imported['name'];native=NativeBackend(opts['mouseOpen']);warnings=[]
    event=cancel_event or threading.Event()
    if not _CAPTURE_LOCK.acquire(blocking=False):raise ValueError('另一个剪映窗口正在准备截图，请稍后重试')
    try:
        with auto.UIAutomationInitializerInThread(),physical_pixels():
            snapshot=native.inspect(name,{})
            if snapshot.get('mode')!='target_editor':raise ValueError('当前剪映窗口不是待截图工程，或存在未重连媒体')
            window=int(snapshot['windowId']);root=auto.ControlFromHandle(window)
            root.SetActive(waitTime=.15)
            user=ctypes.WinDLL('user32',use_last_error=True)
            from ctypes import wintypes as wt
            user.ShowWindow.argtypes=[wt.HWND,ctypes.c_int];user.ShowWindow(wt.HWND(window),3)
            if event.wait(.4):raise InterruptedError('截图准备已停止')
            def current():
                state=native.inspect(name,{})
                if state.get('mode')!='target_editor' or int(state.get('windowId',0))!=window or auto.GetForegroundWindow()!=window:
                    raise ValueError('准备截图时未能确认本工程；状态='+str(state.get('mode'))+
                        '，预期窗口='+str(window)+'，当前窗口='+str(state.get('windowId'))+
                        '，前台窗口='+str(auto.GetForegroundWindow())+
                        ('；'+str(state['identityDiagnostic']) if state.get('identityDiagnostic') else '')+'。请将本工程置于前台后继续')
                if event.is_set():raise InterruptedError('截图准备已停止')
            current();controls=list(_tree(root))
            timelines=[c for c in controls if 'main_timeline_root' in str(c.AutomationId or '')]
            if opts['timelineZoom'] and opts['mouseOpen'] and len(timelines)==1:
                rect=timelines[0].BoundingRectangle;x=(rect.left+rect.right)//2;y=(rect.top+rect.bottom)//2
                if rect.right>rect.left and rect.bottom>rect.top:
                    hit=auto.ControlFromPoint(x,y)
                    if hit and hit.ProcessId==root.ProcessId:
                        auto.MoveTo(x,y,waitTime=.1);current()
                        auto.PressKey(auto.Keys.VK_CONTROL,waitTime=.05)
                        try:current();auto.WheelUp(opts['timelineZoom'],interval=.1,waitTime=.2)
                        finally:auto.ReleaseKey(auto.Keys.VK_CONTROL,waitTime=.05)
            elif opts['timelineZoom']:warnings.append('没有可唯一确认的时间线控件或未允许鼠标，保留当前缩放')
            def transport(names):
                matches=[c for c in _tree(root) if str(c.Name or '').strip() in names and
                         ('player' in str(c.AutomationId or '').lower() or 'player' in _description(c).lower()) and not c.IsOffscreen]
                if len(matches)!=1:return False
                current();pattern=matches[0].GetInvokePattern()
                if not pattern:return False
                pattern.Invoke();return True
            if opts['previewBeforeCapture']:
                if transport(('播放','Play')):
                    if event.wait(.8):raise InterruptedError('截图准备已停止')
                    if not transport(('暂停','Pause')):raise ValueError('已开始预览，但无法确认暂停控件；请手动暂停后重新截图')
                else:warnings.append('没有可唯一确认的播放控件，未自动播放')
            # Leave the pointer in the identified window's outer border so
            # hover previews/tooltips cannot cover the bin or start playback.
            if opts['mouseOpen']:
                current();rect=root.BoundingRectangle
                auto.MoveTo(rect.right-4,rect.top+rect.height()//2,waitTime=.1)
            previous=None;stable=0;deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                current();rect=root.BoundingRectangle;box=(rect.left,rect.top,rect.right,rect.bottom)
                image=ImageGrab.grab(bbox=box,all_screens=True).convert('RGB').resize((320,180))
                if previous is not None:
                    delta=ImageStat.Stat(ImageChops.difference(image,previous))
                    stable=stable+1 if max(delta.mean)<1.2 else 0
                    if stable>=3:return {'windowId':str(window),'pid':snapshot['pid'],
                        'projectTitleVerified':snapshot.get('projectTitleVerified') is True,
                        'projectIdentityVerified':True,'paintStable':True,'warnings':warnings}
                previous=image
                if event.wait(.35):raise InterruptedError('截图准备已停止')
            raise ValueError('剪映画面尚未稳定，本次未采集；请暂停播放并等待素材加载后重试')
    finally:_CAPTURE_LOCK.release()


def close_completed_project(imported,cancel_event=None):
    """Request normal exit only for the batch's own captured project.

    Save dialogs and other editor projects require user action. Never send a
    force kill, a discard response or a generic close-all command.
    """
    if os.name!='nt':raise ValueError('自动批量出图需要 Windows 剪映')
    import uiautomation as auto
    from ctypes import wintypes as wt
    native=NativeBackend();event=cancel_event or threading.Event();name=imported['name']
    if not _OPEN_LOCK.acquire(blocking=False):raise ValueError('剪映正在处理另一个打开请求，请稍后继续')
    try:
        if event.is_set():raise InterruptedError('自动出图已暂停')
        if not jianying_registry.running():return
        with auto.UIAutomationInitializerInThread():
            state=native.inspect(name,{})
            if state.get('mode') not in ('target_editor','home'):
                raise ValueError('剪映当前不是本批已出图工程，请先保存并退出，再点继续出图')
            user=ctypes.WinDLL('user32',use_last_error=True)
            user.PostMessageW.argtypes=[wt.HWND,wt.UINT,wt.WPARAM,wt.LPARAM]
            user.PostMessageW.restype=wt.BOOL
            handle=int(state['windowId'])
            if not user.PostMessageW(wt.HWND(handle),0x10,0,0):raise ValueError('剪映暂未接受正常退出请求，请保存退出后继续')
            home_requested=False;deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                if event.wait(.25):raise InterruptedError('自动出图已暂停')
                if not jianying_registry.running():return
                fresh=native.inspect(name,{})
                if fresh.get('mode')=='home' and not home_requested:
                    root=auto.ControlFromHandle(int(fresh['windowId']))
                    dialogs=[c for c in _tree(root) if str(c.Name or '').strip() in ('保存更改','保存草稿','放弃更改','不保存','Save changes')]
                    if dialogs:break
                    user.PostMessageW(wt.HWND(int(fresh['windowId'])),0x10,0,0);home_requested=True
                elif fresh.get('mode') in ('other_editor','ambiguous','media_missing'):break
            raise ValueError('剪映尚未退出，可能有保存或确认提示；请处理后点继续出图，已保存图片不会重做')
    finally:_OPEN_LOCK.release()
