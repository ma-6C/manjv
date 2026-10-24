"""One serialized, cancellable VSR worker with a bounded idle lifetime."""
from pathlib import Path
import json,os,queue,subprocess,threading,time,uuid

WORKER_SOURCE=r'''
import sys,json,os,gc,traceback
from pathlib import Path
out=sys.stdout
sys.stdout=sys.stderr
sys.__stdout__=sys.stderr
def emit(value):out.write(json.dumps(value,ensure_ascii=True)+'\n');out.flush()
root=Path(sys.argv[1]);sys.path.insert(0,str(root));os.chdir(root)
try:
 from backend.main import SubtitleRemover
 from backend.config import config
 from backend.tools.constant import InpaintMode
 import backend.inpaint.sttn_auto_inpaint as sttn
 import torch
 factory=sttn.STTNInpaint;models={};loads=0;hits=0;completed=0
 def model(device,path):
  global loads,hits
  stat=Path(path).stat();key=(str(device),str(path),stat.st_size,stat.st_mtime_ns)
  if key in models:hits+=1;return models[key]
  models.clear();value=factory(device,path);models[key]=value;loads+=1;return value
 sttn.STTNInpaint=model
 emit({'event':'ready','pid':os.getpid()})
except Exception as error:
 emit({'event':'startup_error','error':str(error)});sys.exit(1)
for line in sys.stdin:
 request=json.loads(line)
 if request.get('cmd')=='quit':break
 sr=None
 try:
  if request.get('mode')!='sttn-auto':raise ValueError('Persistent worker supports STTN-auto only')
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
  emit({'event':'result','id':request.get('id'),'ok':False,'error':str(error)})
 finally:
  if sr is not None:
   try:sr.video_cap.release();sr.video_writer.release()
   except Exception:pass
  sr=None;gc.collect()
'''

class WorkerError(RuntimeError):pass

class Client:
    def __init__(self,runtime,root):
        self.messages=queue.Queue();self.observe=None;self.tail='';self.closed=False
        self.process=subprocess.Popen([str(runtime),'-u','-c',WORKER_SOURCE,str(root)],cwd=root,
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
            if message.get('event') in ('closed','startup_error'):raise WorkerError(message.get('error') or 'AI工作进程意外退出：'+self.tail[-1600:])
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
    def __init__(self,idle_seconds=120):self.lock=threading.RLock();self.client=None;self.signature=None;self.timer=None;self.idle_seconds=idle_seconds
    @staticmethod
    def fingerprint(runtime,root):
        paths=[Path(runtime),Path(root)/'backend/main.py',Path(root)/'config/config.json',Path(root)/'backend/models/sttn-auto/infer_model.pth']
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
            if cold:self.close();self.client=Client(runtime,root);self.signature=signature
            client=self.client;client.observe=observe;attach(client.process)
            try:
                if cold:
                    message=client.receive(cancel,time.monotonic()+180,heartbeat)
                    if message.get('event')!='ready':raise WorkerError('AI工作进程未就绪')
                task=request|{'id':uuid.uuid4().hex}
                client.process.stdin.write((json.dumps(task,ensure_ascii=True)+'\n').encode());client.process.stdin.flush()
                result=client.receive(cancel,time.monotonic()+max(600,min(28800,float(request.get('duration',60))*120)),heartbeat)
                if result.get('id')!=task['id'] or not result.get('ok'):raise WorkerError('AI工作进程处理失败：'+str(result.get('error','响应不匹配'))+'；可关闭模型复用后重试')
                result['reusedProcess']=not cold
                return result
            except BaseException:
                self.close();raise
            finally:
                detach(client.process);client.observe=None
                if self.client:
                    self.timer=threading.Timer(self.idle_seconds,self.close);self.timer.daemon=True;self.timer.start()

POOL=Pool()
