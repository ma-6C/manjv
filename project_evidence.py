"""Unmodified captures of verified official application windows.

App origin, user-confirmed project association and platform acceptance are
separate facts. This module never draws an editor UI or submits screenshots.
"""
from __future__ import annotations
import copy,ctypes,hashlib,os,re,shutil,subprocess,threading,time,uuid
from pathlib import Path

PLATFORMS={'jianying':'剪映'}


def require_platform(platform):
    if not isinstance(platform,str) or platform not in PLATFORMS:
        raise ValueError('当前仅支持剪映工程窗口，请使用剪映重新采集')
    return platform

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(2*1024**2),b''):h.update(b)
    return h.hexdigest()


class WindowsCapture:
    def __init__(self):
        self.cache={}
        if os.name=='nt':
            from ctypes import wintypes as wt
            self.wt=wt;self.user=ctypes.WinDLL('user32',use_last_error=True);self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            self.user.GetForegroundWindow.restype=wt.HWND
            self.kernel.OpenProcess.argtypes=[wt.DWORD,wt.BOOL,wt.DWORD];self.kernel.OpenProcess.restype=wt.HANDLE
            self.kernel.QueryFullProcessImageNameW.argtypes=[wt.HANDLE,wt.DWORD,wt.LPWSTR,ctypes.POINTER(wt.DWORD)]
            self.kernel.CloseHandle.argtypes=[wt.HANDLE]
            self.user.GetWindowThreadProcessId.argtypes=[wt.HWND,ctypes.POINTER(wt.DWORD)]
            self.user.GetWindowTextLengthW.argtypes=[wt.HWND]
            self.user.GetWindowTextW.argtypes=[wt.HWND,wt.LPWSTR,ctypes.c_int]
            self.user.IsWindowVisible.argtypes=[wt.HWND];self.user.IsIconic.argtypes=[wt.HWND]
            self.user.GetWindowRect.argtypes=[wt.HWND,ctypes.POINTER(wt.RECT)]

    def _signature(self,path):
        if Path(path).name.casefold()!='jianyingpro.exe':raise ValueError('请选择剪映官方应用窗口')
        st=Path(path).stat();key=(path,st.st_size,st.st_mtime_ns)
        if key not in self.cache:
            import jianying_projects
            value=jianying_projects._signature(Path(path))
            self.cache[key]={'status':value.get('status','unavailable'),'subject':value.get('publisher','')}
        return self.cache[key]

    def _editor_surface(self,hwnd):
        # The real timeline and export controls distinguish an open editing
        # project from the home screen, splash screen or floating player.
        try:
            import uiautomation as auto
            with auto.UIAutomationInitializerInThread():
                import jianying_automation
                root=auto.ControlFromHandle(hwnd)
                if jianying_automation.media_missing(root):return False
                for owned in auto.GetRootControl().GetChildren():
                    if owned.ProcessId==root.ProcessId and jianying_automation.media_missing(owned):return False
                stack=[(root,0)];count=0;timeline=False;export=False
                while stack and count<450:
                    control,depth=stack.pop();count+=1;identity=control.AutomationId or ''
                    timeline=timeline or 'main_timeline_root' in identity
                    export=export or identity=='editor.export'
                    if timeline and export:return True
                    if depth<16:stack.extend((c,depth+1) for c in reversed(control.GetChildren()))
        except Exception:pass
        return False

    def describe(self,hwnd,platform):
        require_platform(platform)
        if os.name!='nt':raise ValueError('官方窗口采集需要在 Windows 桌面应用中运行')
        handle=self.wt.HWND(int(hwnd));pid=self.wt.DWORD()
        if not self.user.IsWindowVisible(handle) or self.user.IsIconic(handle):return None
        self.user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        process=self.kernel.OpenProcess(0x1000,False,pid.value)
        if not process:return None
        try:
            buffer=ctypes.create_unicode_buffer(32768);length=self.wt.DWORD(len(buffer))
            if not self.kernel.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(length)):return None
            path=buffer.value
        finally:self.kernel.CloseHandle(process)
        name=Path(path).name.casefold()
        if name!='jianyingpro.exe':return None
        signature=self._signature(path)
        publisher=('深圳市脸萌科技有限公司',)
        names=[value.strip().strip('"') for value in re.findall(r'(?:^|,\s*)(?:CN|O)=([^,]+)',signature['subject'])]
        if signature['status']!='Valid' or not any(p in names for p in publisher):return None
        title=ctypes.create_unicode_buffer(max(1,self.user.GetWindowTextLengthW(handle)+1))
        self.user.GetWindowTextW(handle,title,len(title))
        if not title.value.strip():return None
        if not self._editor_surface(int(hwnd)):return None
        return {'id':str(int(hwnd)),'title':title.value[:300],'pid':pid.value,'platform':platform,
            'processName':Path(path).name,'processPath':path,'appVerified':True,'signatureStatus':signature['status'],
            'signatureSubject':signature['subject'],'pageUrl':''}

    def windows(self,platform):
        require_platform(platform)
        if os.name!='nt':return []
        handles=[];callback=ctypes.WINFUNCTYPE(self.wt.BOOL,self.wt.HWND,self.wt.LPARAM)
        def collect(hwnd,param):handles.append(int(hwnd));return True
        cb=callback(collect);self.user.EnumWindows(cb,0);rows=[]
        for hwnd in handles:
            try:
                item=self.describe(hwnd,platform)
                if item:rows.append(item)
            except (OSError,ValueError,subprocess.TimeoutExpired):continue
        return rows

    def foreground(self,window):
        return int(self.user.GetForegroundWindow() or 0)==int(window)

    def capture(self,window,platform,target):
        require_platform(platform)
        before=self.describe(window,platform)
        if not before or not self.foreground(window):raise ValueError('请选择官方工程窗口并将它置于最前方')
        from PIL import ImageGrab,ImageStat
        previous=None
        try:
            # Keep window coordinates and desktop pixels in the same per-monitor
            # DPI space, including mixed-scaling multi-monitor setups.
            if hasattr(self.user,'SetThreadDpiAwarenessContext'):
                self.user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
                self.user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
                previous=self.user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
            rect=self.wt.RECT();self.user.GetWindowRect(self.wt.HWND(int(window)),ctypes.byref(rect))
            box=(rect.left,rect.top,rect.right,rect.bottom)
            if not 300<=box[2]-box[0]<=16000 or not 200<=box[3]-box[1]<=16000:raise ValueError('工程窗口过小或尺寸无效，请展开后重试')
            image=ImageGrab.grab(bbox=box,all_screens=True)
        finally:
            if previous:self.user.SetThreadDpiAwarenessContext(previous)
        after=self.describe(window,platform)
        if not after or not self.foreground(window) or any(before[k]!=after[k] for k in ('pid','processPath','title','pageUrl')):
            raise ValueError('采集时窗口或网页发生变化，请保持工程界面在前台后重试')
        if max(ImageStat.Stat(image.convert('RGB')).stddev)<2:raise ValueError('截图为空白，请保持编辑器画面正常显示后重试')
        image.save(target,'PNG')
        return {**before,'width':image.width,'height':image.height,'captureMethod':'desktop_visible_window','unmodified':True,'bounds':list(box)}


class Manager:
    def __init__(self,state,data,lock,save,register,backend=None):
        self.state,self.data,self.lock,self.save,self.register=state,Path(data),lock,save,register
        self.backend=backend or WindowsCapture();self.stop=threading.Event()
        with lock:
            state.setdefault('projectEvidence',{'items':[],'tasks':[]})
            for task in state['projectEvidence']['tasks']:
                if task['status'] in ('waiting_window','capturing','automating'):
                    retired=task.get('platform') not in (None,'jianying')
                    task.update(status='failed',message='原截图来源已停用，请使用剪映重新采集' if retired else '上次采集已中断，请重新选择剪映工程窗口')
    @property
    def value(self):return self.state['projectEvidence']
    def list(self,pid):
        with self.lock:return copy.deepcopy({key:[x for x in self.value[key] if x['projectId']==pid] for key in ('items','tasks')})
    def _record(self,pid,path,platform,source,note,metadata,association):
        require_platform(platform)
        evidence={'source':source,'platform':platform,'appVerified':source=='window_capture' and metadata.get('appVerified') is True,
            'sha256':sha(path),'projectConfirmedByUser':association.get('userConfirmed') is True,
            'capturedAt':time.time(),'metadata':metadata,'association':association,'platformAccepted':False}
        item={'id':uuid.uuid4().hex[:16],'projectId':pid,'platform':platform,'source':source,'path':str(path),
              'capturedAt':evidence['capturedAt'],'projectAssociation':association,'note':note,'officialEvidence':evidence}
        with self.lock:
            self.register(pid,path,PLATFORMS[platform]+'工程截图' if evidence['appVerified'] else '待核对工程截图',evidence)
            self.value['items'].append(item);self.value['items']=self.value['items'][-1000:];self.save()
        return copy.deepcopy(item)
    def capture(self,pid,body,association):
        platform=body.get('platform','jianying')
        require_platform(platform)
        candidates=self.backend.windows(platform)
        if not body.get('windowId'):return {'windows':candidates,'note':'请先在官方编辑器打开对应工程，再选择窗口采集'}
        if body.get('userConfirmed') is not True:raise ValueError('请本人确认选中的剪映窗口已打开本剧工程，并且时间线和预览清晰可见')
        window=str(body['windowId']);candidate=next((x for x in candidates if x['id']==window),None)
        if not candidate:raise ValueError('所选窗口已关闭或来源无法核验，请重新选择')
        if self.stop.is_set():raise ValueError('截图服务正在关闭')
        with self.lock:
            if self.stop.is_set():raise ValueError('截图服务正在关闭')
            if any(t['projectId']==pid and t['status'] in ('waiting_window','capturing','automating') for t in self.value['tasks']):raise ValueError('本剧已有截图采集正在等待，请先切换到官方工程窗口')
            task={'id':uuid.uuid4().hex[:16],'projectId':pid,'platform':platform,'status':'waiting_window','message':'请在30秒内切换到选中的剪映工程窗口，保持画面清晰可见','createdAt':time.time()}
            self.value['tasks'].append(task);self.value['tasks']=self.value['tasks'][-100:];self.save()
        def run():
            path=None
            try:
                ready_at=None;end=time.monotonic()+30
                while time.monotonic()<end:
                    if self.stop.wait(.2):raise InterruptedError('采集已停止')
                    if self.backend.foreground(window):
                        ready_at=ready_at or time.monotonic()
                        if time.monotonic()-ready_at>.8:break
                    else:ready_at=None
                else:raise ValueError('未检测到选中窗口在前台，请展开工程界面后重新采集')
                with self.lock:task.update(status='capturing',message='正在采集实际窗口');self.save()
                folder=self.data/'official-project-evidence'/pid;folder.mkdir(parents=True,exist_ok=True)
                path=folder/(task['id']+'.png');metadata=self.backend.capture(window,platform,path)
                if any(metadata.get(k)!=candidate.get(k) for k in ('pid','processPath')):raise ValueError('窗口所属进程已变化，请重新选择')
                if self.stop.is_set():raise InterruptedError('采集已停止')
                association['userConfirmed']=True
                item=self._record(pid,path,platform,'window_capture',str(body.get('note',''))[:1000],metadata,association)
                with self.lock:task.update(status='completed',message='已采集未绘制、未拼接的官方窗口截图；工程内容由本人确认',item=item);self.save()
            except Exception as error:
                if path and path.is_file():path.unlink()
                with self.lock:task.update(status='failed',message=str(error)[:1000]);self.save()
        threading.Thread(target=run,daemon=True,name='project-evidence-'+task['id']).start()
        return {'taskId':task['id'],'status':'waiting_window','message':task['message']}

    def auto_capture(self,pid,body,association,imported,opts):
        """Open, frame and capture a registered project without fabricated UI."""
        import jianying_automation
        if association.get('draftName')!=imported['name']:raise ValueError('自动截图的工程关联不匹配')
        with self.lock:
            if self.stop.is_set():raise ValueError('截图服务正在关闭')
            if any(t['status'] in ('waiting_window','capturing','automating') for t in self.value['tasks']):raise ValueError('已有剪映截图任务，请等待当前任务完成')
            task={'id':uuid.uuid4().hex[:16],'projectId':pid,'platform':'jianying','status':'automating',
                  'message':'正在登记并打开对应剪映工程','createdAt':time.time()}
            self.value['tasks'].append(task);self.value['tasks']=self.value['tasks'][-100:];self.save()
        def run():
            path=None
            try:
                opened=jianying_automation.open_registered_project(imported,opts,self.stop)
                if not opened.get('projectOpened'):
                    with self.lock:task.update(status='waiting_action',message=opened['message']);self.save()
                    return
                with self.lock:task.update(message='已定位本工程，正在调整时间线并等待画面稳定');self.save()
                frame=jianying_automation.prepare_capture(imported,opts,self.stop)
                candidate=self.backend.describe(frame['windowId'],'jianying')
                if not candidate or candidate['pid']!=frame['pid']:raise ValueError('官方工程窗口在采集前已变化')
                native=jianying_automation.NativeBackend()
                exact=native.inspect(imported['name'],{})
                if exact.get('mode')!='target_editor' or exact.get('windowId')!=frame['windowId']:raise ValueError('采集前工程标题核对失败')
                folder=self.data/'official-project-evidence'/pid;folder.mkdir(parents=True,exist_ok=True)
                path=folder/(task['id']+'.png')
                metadata=self.backend.capture(frame['windowId'],'jianying',path)
                exact=native.inspect(imported['name'],{})
                if exact.get('mode')!='target_editor' or exact.get('windowId')!=frame['windowId']:raise ValueError('采集过程中工程已切换')
                if metadata['pid']!=candidate['pid'] or metadata['title']!=candidate['title']:raise ValueError('截图时工程标题或进程发生变化')
                if self.stop.is_set():raise InterruptedError('截图服务已停止')
                metadata.update(projectTitleVerified=True,paintStable=True,automationWarnings=frame['warnings'])
                matched={**association,'userConfirmed':body.get('userConfirmed') is True,'projectMatchedByAutomation':True,
                         'status':'已核对工程标题和真实时间线；画面内容及使用效果仍需本人查看'}
                item=self._record(pid,path,'jianying','window_capture','自动打开本工程后采集的原始剪映窗口',metadata,matched)
                with self.lock:task.update(status='completed',message='实际工程截图已保存'+('；'+'；'.join(frame['warnings']) if frame['warnings'] else ''),item=item);self.save()
            except Exception as exc:
                if path and path.is_file():path.unlink()
                with self.lock:task.update(status='failed',message=str(exc)[:2000]);self.save()
        threading.Thread(target=run,daemon=True,name='jianying-auto-'+task['id']).start()
        return {'taskId':task['id'],'status':'automating','message':task['message']}
    def import_images(self,pid,body,association):
        platform=body.get('platform');paths=body.get('paths');note=body.get('note','')
        require_platform(platform)
        if body.get('userConfirmed') is not True or not isinstance(note,str) or not note.strip():raise ValueError('请注明剪映工程来源说明并本人确认')
        if not isinstance(paths,list) or not 1<=len(paths)<=30:raise ValueError('一次请选择1至30张实际工程截图')
        from PIL import Image
        items=[];folder=self.data/'official-project-evidence'/pid;folder.mkdir(parents=True,exist_ok=True)
        for value in paths:
            if not isinstance(value,str):raise ValueError('截图路径无效')
            source=Path(value).resolve()
            if source.suffix.lower() not in ('.png','.jpg','.jpeg','.webp') or not source.is_file() or not 0<source.stat().st_size<100*1024**2:raise ValueError('请提供可读取的截图图片')
            with Image.open(source) as image:
                if image.width*image.height>100_000_000:raise ValueError('截图尺寸过大')
                image.verify()
            target=folder/(uuid.uuid4().hex+source.suffix.lower());shutil.copy2(source,target)
            items.append(self._record(pid,target,platform,'manual_import',note[:1000],{'appVerified':False,'unmodified':True},association))
        return {'items':items,'note':'已保存原始图片；手动导入来源未自动核验，不会升级为已验证官方窗口截图'}
    def shutdown(self):self.stop.set()
