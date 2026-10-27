"""One serialized, cancellable VSR worker with a bounded idle lifetime."""
from pathlib import Path
import json,os,queue,subprocess,threading,time,uuid

STRICT_IO_SOURCE=r'''
import subprocess,tempfile,math,os
APP_FFMPEG=''
class CheckedVideoWriter:
 def __init__(self,path,*args):
  fps,size=args if len(args)==2 else args[1:]
  w,h=map(int,size);fps=float(fps)
  if not math.isfinite(fps) or fps<=0 or w<=0 or h<=0 or w%2 or h%2:raise ValueError(f'Invalid STTN video dimensions/frame rate: {w}x{h}, {fps}fps')
  self.frames=0;self.fps=fps;self.size=(w,h);self.closed=False;self.failure=None;self.error_log=tempfile.TemporaryFile()
  try:
   self.process=subprocess.Popen([APP_FFMPEG,'-hide_banner','-loglevel','error','-nostdin','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{w}x{h}','-r',str(fps),'-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-threads','2','-movflags','+faststart',str(path)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=self.error_log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  except Exception:
   self.error_log.close();raise
 def error_text(self):
  self.error_log.seek(0);return self.error_log.read().decode('utf-8','replace')[-5000:]
 def isOpened(self):return not self.closed and self.process.poll() is None
 def write(self,frame):
  import numpy as np
  if frame.shape!=(self.size[1],self.size[0],3):raise ValueError(f'STTN frame size mismatch: {frame.shape}, expected {self.size}')
  if frame.dtype!=np.uint8:frame=np.clip(frame,0,255).astype(np.uint8)
  try:self.process.stdin.write(frame.tobytes());self.frames+=1
  except (BrokenPipeError,OSError) as error:
   try:self.process.wait(timeout=10)
   except subprocess.TimeoutExpired:self.abort()
   raise RuntimeError(f'STTN video encoder pipe closed; exit code {self.process.poll()}: '+self.error_text()) from error
 def release(self):
  if self.closed:
   if self.failure:raise self.failure
   return
  self.closed=True
  try:
   try:self.process.stdin.close()
   except (BrokenPipeError,OSError):pass
   try:code=self.process.wait(timeout=600)
   except subprocess.TimeoutExpired:
    self.process.kill();self.process.wait(timeout=5);raise RuntimeError('STTN video encoder timed out: '+self.error_text())
   if code:raise RuntimeError(f'STTN video encoder failed; exit code {code}: '+self.error_text())
   if self.frames<=0:raise RuntimeError('STTN video encoder received no frames')
  except Exception as error:self.failure=error;raise
 def abort(self):
  if self.process.poll() is None:
   self.process.kill()
   try:self.process.wait(timeout=5)
   except subprocess.TimeoutExpired:pass
  try:self.process.stdin.close()
  except (BrokenPipeError,OSError,ValueError):pass
 def dispose(self):
  self.abort();self.error_log.close()

def checked_merge_audio(sr):
 writer=sr.video_writer
 if not isinstance(writer,CheckedVideoWriter):raise RuntimeError('STTN checked writer was not installed')
 writer.release()
 if writer.frames+1<sr.frame_count:raise RuntimeError(f'STTN stopped before whole video: {writer.frames}/{sr.frame_count} frames')
 duration=writer.frames/writer.fps
 command=[APP_FFMPEG,'-hide_banner','-loglevel','error','-nostdin','-y','-i',str(sr.video_temp_file.name),'-i',str(sr.video_path),'-map','0:v:0','-map','1:a:0?','-c:v','copy','-c:a','aac','-b:a','192k','-af','aresample=async=1000:first_pts=0,apad','-t',str(duration),'-movflags','+faststart',str(sr.video_out_path)]
 try:
  result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  if result.returncode:raise RuntimeError(f'STTN audio/video mux failed; exit code {result.returncode}: '+result.stderr.decode('utf-8','replace')[-5000:])
  sr.is_successful_merged=True
 finally:sr.video_temp_file.close()
'''

WORKER_SOURCE=STRICT_IO_SOURCE+r'''
import sys,json,os,gc,traceback
from pathlib import Path
sys.dont_write_bytecode=True
out=sys.stdout
sys.stdout=sys.stderr
sys.__stdout__=sys.stderr
def emit(value):out.write(json.dumps(value,ensure_ascii=True)+'\n');out.flush()
root=Path(sys.argv[1]);sys.path.insert(0,str(root));os.chdir(root)
try:
 import backend.main as backend_main
 from backend.main import SubtitleRemover
 from backend.config import config
 from backend.tools.constant import InpaintMode
 import backend.inpaint.sttn_auto_inpaint as sttn
 import torch
 # Apply only inside this child process; the signed engine files stay intact.
 class CVProxy:
  def __getattr__(self,name):return CheckedVideoWriter if name=='VideoWriter' else getattr(original_cv,name)
 original_cv=backend_main.cv2;backend_main.cv2=CVProxy()
 backend_main.FFmpegVideoWriter=CheckedVideoWriter
 SubtitleRemover.merge_audio_to_video=checked_merge_audio
 factory=sttn.STTNInpaint;models={};loads=0;hits=0;completed=0
 def model(device,path):
  global loads,hits
  stat=Path(path).stat();key=(str(device),str(path),stat.st_size,stat.st_mtime_ns)
  if key in models:hits+=1;return models[key]
  models.clear();value=factory(device,path);models[key]=value;loads+=1;return value
 sttn.STTNInpaint=model
 emit({'event':'ready','pid':os.getpid()})
except Exception as error:
 emit({'event':'startup_error','error':str(error),'detail':traceback.format_exc()});sys.exit(1)
for line in sys.stdin:
 request=json.loads(line)
 if request.get('cmd')=='quit':break
 sr=None
 try:
  if request.get('mode')!='sttn-auto':raise ValueError('Persistent worker supports STTN-auto only')
  APP_FFMPEG=request.get('ffmpeg','')
  if not APP_FFMPEG or not Path(APP_FFMPEG).is_file():raise ValueError('STTN requires the application FFmpeg executable')
  config.inpaintMode.value=InpaintMode.STTN_AUTO
  sr=SubtitleRemover(request['input'])
  if not sr.video_cap.isOpened() or sr.frame_count<=0:raise ValueError('VSR cannot open input video')
  sr.sub_areas=request['regions'];sr.video_out_path=request['output'];sr.run()
  if not sr.isFinished:raise RuntimeError('VSR did not finish the whole video')
  completed+=1
  emit({'event':'result','id':request['id'],'ok':True,'pid':os.getpid(),'modelLoads':loads,'modelCacheHits':hits,'completedVideos':completed})
 except Exception as error:
  print(traceback.format_exc(),file=sys.stderr)
  models.clear();gc.collect()
  if torch.cuda.is_available():torch.cuda.empty_cache()
  emit({'event':'result','id':request.get('id'),'ok':False,'error':str(error),'detail':traceback.format_exc()})
 finally:
  if sr is not None:
   try:sr.video_cap.release();sr.video_writer.dispose();sr.video_temp_file.close()
   except Exception:pass
  sr=None;gc.collect()
'''

class WorkerError(RuntimeError):
    def __init__(self,message,details='',exit_code=None):
        self.details=details or message;self.tool='本地 AI 工作进程';self.exit_code=exit_code
        super().__init__(message)

class Client:
    def __init__(self,runtime,root,worker_source=None):
        self.messages=queue.Queue();self.observe=None;self.tail='';self.closed=False
        self.process=subprocess.Popen([str(runtime),'-u','-c',worker_source if worker_source is not None else WORKER_SOURCE,str(root)],cwd=root,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=os.environ|{'PYTHONIOENCODING':'utf-8','PYTHONUNBUFFERED':'1'},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def protocol():
            try:
                for line in self.process.stdout:
                    try:self.messages.put(json.loads(line.decode('utf-8')))
                    except (ValueError,UnicodeError):pass
            finally:self.messages.put({'event':'closed'})
        def logs():
            import codecs,re
            decoder=codecs.getincrementaldecoder('utf-8')('replace');pending=''
            while block:=self.process.stderr.read1(8192):
                text=decoder.decode(block);self.tail=(self.tail+text)[-6000:];pending+=text
                lines=re.split(r'[\r\n]',pending);pending=lines.pop()[-65536:]
                for line in lines:
                    callback=self.observe
                    if line and callback:
                        try:callback(line)
                        except Exception:pass
        for target in (protocol,logs):threading.Thread(target=target,daemon=True).start()
    def receive(self,cancel,deadline,heartbeat):
        while True:
            if cancel.is_set():self.close();raise InterruptedError('已暂停本地AI，当前未完成视频恢复时重新处理')
            if time.monotonic()>deadline:self.close();raise WorkerError('AI工作进程等待超时，请重试或关闭模型复用')
            heartbeat()
            try:message=self.messages.get(timeout=.25)
            except queue.Empty:
                if self.process.poll() is not None:raise WorkerError('AI工作进程已退出：'+self.tail[-1600:])
                continue
            if message.get('event') in ('closed','startup_error'):raise WorkerError(message.get('error') or 'AI工作进程意外退出：'+self.tail[-1600:],message.get('detail','')+'\n'+self.tail[-6000:],self.process.poll())
            return message
    def close(self):
        if self.closed:return
        self.closed=True
        if self.process.poll() is None:
            self.process.kill()
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
        for pipe in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:pipe.close()
            except (OSError,ValueError):pass

class Pool:
    def __init__(self,idle_seconds=120,worker_source=None,model_file='backend/models/sttn-auto/infer_model.pth'):self.lock=threading.RLock();self.client=None;self.signature=None;self.timer=None;self.idle_seconds=idle_seconds;self.worker_source=worker_source;self.model_file=model_file
    def fingerprint(self,runtime,root):
        # Watch only this worker's model. The upstream VSR initializer can merge
        # other model shards; those writes must not restart an unrelated worker.
        paths=[Path(runtime),Path(root)/'backend/main.py',Path(root)/'config/config.json',Path(root)/self.model_file]
        return tuple((str(p.resolve()),p.stat().st_size,p.stat().st_mtime_ns) for p in paths if p.is_file())
    def close(self):
        with self.lock:
            if self.timer:self.timer.cancel();self.timer=None
            if self.client:self.client.close();self.client=None
            self.signature=None
    def run(self,runtime,root,request,cancel,observe=lambda line:None,heartbeat=lambda:None,attach=lambda p:None,detach=lambda p:None):
        with self.lock:
            if self.timer:self.timer.cancel();self.timer=None
            signature=self.fingerprint(runtime,root);cold=not self.client or self.signature!=signature or self.client.process.poll() is not None
            if cold:self.close();self.client=Client(runtime,root,self.worker_source);self.signature=signature
            client=self.client;client.observe=observe;attach(client.process)
            try:
                if cold:
                    message=client.receive(cancel,time.monotonic()+180,heartbeat)
                    if message.get('event')!='ready':raise WorkerError('AI工作进程未就绪')
                task=request|{'id':uuid.uuid4().hex}
                client.tail=''
                client.process.stdin.write((json.dumps(task,ensure_ascii=True)+'\n').encode());client.process.stdin.flush()
                result=client.receive(cancel,time.monotonic()+max(600,min(28800,float(request.get('duration',60))*120)),heartbeat)
                if result.get('id')!=task['id'] or not result.get('ok'):raise WorkerError('AI工作进程处理失败：'+str(result.get('error','响应不匹配')),result.get('detail','')+'\n'+str(result.get('error',''))+'\n'+client.tail[-6000:],client.process.poll())
                result['reusedProcess']=not cold
                result['engineLog']=client.tail[-6000:]
                return result
            except BaseException:
                self.close();raise
            finally:
                detach(client.process);client.observe=None
                if self.client:
                    self.timer=threading.Timer(self.idle_seconds,self.close);self.timer.daemon=True;self.timer.start()

POOL=Pool()
