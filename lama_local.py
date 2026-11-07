"""Local LaMa video repair for boxed regions and outlined white subtitles."""
from pathlib import Path
import vsr_pool

MODEL='backend/models/big-lama/big-lama.pt'
MODES=('lama-box','lama-text')

def ready(root,runtime):
    return Path(runtime).is_file() and (Path(root)/MODEL).is_file()

# Keep the worker source as data so frozen builds can invoke an existing signed
# optional AI runtime without modifying that runtime's files.
WORKER_SOURCE=r'''
import sys,os,json,time,gc,traceback,subprocess,tempfile,math
from pathlib import Path
out=sys.stdout;sys.stdout=sys.stderr;sys.__stdout__=sys.stderr
def emit(value):out.write(json.dumps(value,ensure_ascii=True)+'\n');out.flush()

def outlined_text_mask(frame, region, glyph_limit, outline_kernel):
 minimum=frame.min(axis=2)
 gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
 stroke=cv2.morphologyEx(gray,cv2.MORPH_TOPHAT,outline_kernel)>=22
 white=((minimum>=180)&(frame.max(axis=2)-minimum<=40)&stroke&(region>0)).astype(np.uint8)
 nearby_dark=cv2.erode(gray,outline_kernel)<=96
 count,labels,stats,_=cv2.connectedComponentsWithStats(white,connectivity=8)
 dark_counts=np.bincount(labels[nearby_dark],minlength=count)
 _,_,widths,heights,areas=stats.T
 keep=(areas>=3)&(widths<=glyph_limit)&(heights<=glyph_limit)&(dark_counts>=areas*.4)
 keep[0]=False
 return cv2.dilate(keep[labels].astype(np.uint8),outline_kernel)

root=Path(sys.argv[1]);model=None;signature=None;loads=0;hits=0;completed=0
emit({'event':'ready','pid':os.getpid()})
for line in sys.stdin:
 req=json.loads(line);cap=None;writer=None;encoder_log=None
 try:
  import torch,numpy as np,cv2
  torch.set_num_threads(min(4,os.cpu_count() or 2))
  path=root/'backend/models/big-lama/big-lama.pt';st=path.stat()
  requested=req.get('device','auto');device='cpu';fallback=''
  if requested=='auto' and torch.cuda.is_available():
   try:torch.ones(1,device='cuda').mul_(2);device='cuda'
   except RuntimeError as error:fallback=str(error)[:300]
  key=(str(path),st.st_size,st.st_mtime_ns,device)
  if model is None or key!=signature:
   model=None;gc.collect()
   if torch.cuda.is_available():torch.cuda.empty_cache()
   def load(target):
    # Python file handles support Chinese paths that some LibTorch builds cannot open.
    with path.open('rb') as stream:return torch.jit.load(stream,map_location=target).eval()
   try:model=load(device)
   except RuntimeError as error:
    if device!='cuda':raise
    fallback=str(error)[:300];device='cpu';model=load(device);key=key[:-1]+('cpu',)
   signature=key;loads+=1
  else:hits+=1
  cap=cv2.VideoCapture(req['input'])
  if not cap.isOpened():raise ValueError('Cannot read input video')
  width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH));height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT));fps=float(cap.get(cv2.CAP_PROP_FPS));total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
  if not 0<fps<=240 or width%2 or height%2:raise ValueError('LaMa requires a valid frame rate and even source dimensions')
  keep=float(req.get('preserveTailSeconds',0))
  if not math.isfinite(keep) or keep<0:raise ValueError('Invalid subtitle tail preservation duration')
  if keep and total<=0:raise ValueError('Cannot determine frame count for tail preservation')
  process_until=max(0,min(total,math.ceil(total-keep*fps))) if keep else total
  mask=np.zeros((height,width),np.uint8)
  for y0,y1,x0,x1 in req['regions']:
   if not 0<=x0<x1<=width or not 0<=y0<y1<=height:raise ValueError('Subtitle rectangle is outside input frame')
   mask[y0:y1,x0:x1]=255
  ys,xs=np.nonzero(mask)
  if not len(xs):raise ValueError('No boxed subtitle area selected')
  # Include surrounding image context but composite only the user's exact mask.
  x0=max(0,int(xs.min())-64);x1=min(width,int(xs.max())+65);y0=max(0,int(ys.min())-64);y1=min(height,int(ys.max())+65)
  local_mask=mask[y0:y1,x0:x1];h,w=local_mask.shape;ph=(-h)%8;pw=(-w)%8
  def to_mask_tensor(binary):
   padded=np.pad(binary[None,None].astype(np.float32),((0,0),(0,0),(0,ph),(0,pw)),mode='symmetric')
   return torch.from_numpy(padded).to(device)
  text_mode=req.get('mode')=='lama-text'
  if text_mode:
   radius=max(2,min(10,round(min(width,height)*.007)))
   outline_kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1))
   glyph_limit=max(16,round(min(width,height)*.11))
  else:mask_tensor=to_mask_tensor(local_mask>0)
  encoder_log=tempfile.TemporaryFile()
  encode_args=req.get('encodeArgs') or ['-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-threads','2']
  video_encoder=encode_args[1]
  writer=subprocess.Popen([req['ffmpeg'],'-hide_banner','-loglevel','error','-nostdin','-y','-f','rawvideo','-pix_fmt','bgr24','-s',f'{width}x{height}','-r',str(fps),'-i','pipe:0','-an',*encode_args,'-movflags','+faststart',req['output']],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=encoder_log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  done=0;last=0;inferred=0
  with torch.inference_mode():
   while True:
    ok,frame=cap.read()
    if not ok:break
    if not keep or done<process_until:
     dst=frame[y0:y1,x0:x1]
     chosen=local_mask>0
     if text_mode:
      text_mask=outlined_text_mask(dst,local_mask,glyph_limit,outline_kernel)
      alpha=np.maximum(text_mask,cv2.GaussianBlur(text_mask.astype(np.float32),(5,5),0))
      chosen=alpha>0
     if not text_mode or chosen.any():
      if text_mode:mask_tensor=to_mask_tensor(chosen)
      crop=cv2.cvtColor(dst,cv2.COLOR_BGR2RGB)
      array=np.pad(crop.transpose(2,0,1)[None].astype(np.float32)/255,((0,0),(0,0),(0,ph),(0,pw)),mode='symmetric')
      tensor=torch.from_numpy(array).to(device)
      try:result=model(tensor,mask_tensor)
      except RuntimeError as error:
       if device!='cuda':raise
       fallback=str(error)[:300];device='cpu';tensor=tensor.cpu();mask_tensor=mask_tensor.cpu();model=model.cpu();signature=None
       torch.cuda.empty_cache();result=model(tensor,mask_tensor)
      pixels=np.clip(result[0,:,:h,:w].permute(1,2,0).cpu().numpy()*255,0,255).astype(np.uint8)
      pixels=cv2.cvtColor(pixels,cv2.COLOR_RGB2BGR)
      if text_mode:
       weights=alpha[chosen,None]
       dst[chosen]=np.rint(weights*pixels[chosen]+(1-weights)*dst[chosen]).astype(np.uint8)
      else:dst[chosen]=pixels[chosen]
      inferred+=1
    writer.stdin.write(frame.tobytes());done+=1
    now=time.monotonic()
    if now-last>.25 or done==total:
     print(f'Subtitle Removing | {done}/{total}',file=sys.stderr,flush=True);last=now
  if done<=0 or total>0 and done<total:raise RuntimeError('Decoder stopped before the whole video was processed')
  writer.stdin.close();code=writer.wait(timeout=120)
  if code:
   encoder_log.seek(0);raise RuntimeError('LaMa video encoding failed: '+encoder_log.read().decode('utf-8','replace')[-2000:])
  writer=None;cap.release();cap=None;completed+=1
  emit({'event':'result','id':req['id'],'ok':True,'pid':os.getpid(),'engine':req.get('mode','lama-box'),'device':device,'fallback':fallback,'videoEncoder':video_encoder,'frames':done,'fps':fps,'modelLoads':loads,'modelCacheHits':hits,'completedVideos':completed,'maskPixels':int((mask>0).sum()),'inferredFrames':inferred,'preserveTailSeconds':keep,'processedFrames':min(done,process_until) if keep else done,'preservedTailFrames':max(0,done-process_until) if keep else 0})
 except Exception as error:
  print(traceback.format_exc(),file=sys.stderr,flush=True);model=None;signature=None;gc.collect()
  detail=str(error)
  if writer is not None and isinstance(error,OSError):
   try:
    if writer.wait(timeout=5):
     encoder_log.seek(0);detail='LaMa video encoding failed: '+encoder_log.read().decode('utf-8','replace')[-2000:]
   except subprocess.TimeoutExpired:pass
  emit({'event':'result','id':req.get('id'),'ok':False,'error':detail})
 finally:
  if writer is not None:
   try:
    if writer.poll() is None:writer.kill()
    writer.wait(timeout=10)
   except Exception:pass
  if encoder_log is not None:encoder_log.close()
  if cap is not None:cap.release()
'''

POOL=vsr_pool.Pool(worker_source=WORKER_SOURCE,model_file=MODEL)
