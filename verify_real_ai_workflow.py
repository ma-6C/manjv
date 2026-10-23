"""Real supplied subtitle clip through the full AI-to-final-segments pipeline."""
from pathlib import Path
import os,json,sys,shutil,time,threading,urllib.request,re,subprocess
ROOT=Path(__file__).resolve().parent
reuse='--reuse' in sys.argv
BASE=Path(json.loads((ROOT/'tmp/current-real-ai-workflow.json').read_text('utf-8'))['base']) if reuse else ROOT/'实际视频测试'/('全流程AI验收_'+time.strftime('%Y%m%d-%H%M%S'))
BASE.mkdir(parents=True,exist_ok=True)
os.environ['MANJU_DATA']=str(BASE/'隔离应用数据')
import server as app
report={'base':str(BASE),'checks':[]};http=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
threading.Thread(target=http.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{http.server_address[1]}/api/'
def api(name,body=None):
 req=urllib.request.Request(url+name,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Local-Client':'1'})
 with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def save():
 (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
 (ROOT/'tmp/current-real-ai-workflow.json').write_text(json.dumps({'base':str(BASE),'report':str(BASE/'report.json')},ensure_ascii=False,indent=2),'utf-8')
def count(path):
 r=subprocess.run([app.FFMPEG,'-hide_banner','-loglevel','error','-i',str(path),'-map','0:v:0','-an','-progress','pipe:1','-f','null','-'],capture_output=True,check=True)
 return int(re.findall(r'^frame=(\d+)$',r.stdout.decode(),re.M)[-1])
try:
 original=Path(json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source']);before=app.sha256(original)
 source=BASE/'素材'/'带字幕样片';source.mkdir(parents=True,exist_ok=True);clip=source/'01.mp4'
 if not reuse:shutil.copy2(original,clip)
 engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
 cfg={'source':str(source),'output':str(BASE/'导出'),'width':1254,'height':720,'segmentSeconds':5,'regroup':True,'parallel':1,'gpu':False,
      'speed':1,'cropPercent':0,'brightness':0,'contrast':1,'saturation':1,'markAI':False,'subtitleAuto':True,'subtitleFirst':1,
      'subtitleMode':'vsr','vsrRoot':engine['root'],'vsrPython':engine['python'],'vsrMode':'sttn-auto',
      'subtitleRegions':[{'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}],
      'pipelineHighlight':False,'autoText':False,'autoCover':True,'autoRecords':True,'autoCost':False}
 api('config',cfg)
 if reuse:
  state=api('state');p=state['projects'][0];jid=next(j['id'] for j in state['jobs'] if j['kind']=='pipeline' and j['status']=='completed')
 else:
  p=api('scan',{'source':str(source)})['projects'][0];jid=api('jobs',{'kind':'pipeline','ids':[p['id']]})['id']
 t=time.monotonic();last=''
 while time.monotonic()-t<600:
  state=api('state');j=next(x for x in state['jobs'] if x['id']==jid)
  if j['stage']!=last:print(j['stage'].encode('ascii','backslashreplace').decode(),flush=True);last=j['stage']
  if j['status'] not in ['queued','running','pausing']:break
  time.sleep(.5)
 assert j['status']=='completed',j
 p=next(x for x in api('state')['projects'] if x['id']==p['id']);files=p['finalVideoPaths'];assert len(files)==3,files
 frames=[count(x) for x in files];assert sum(frames)==count(original)==362,frames
 metadata=[app.probe(x) for x in files];assert all(x['audio'] for x in metadata)
 assert abs(sum(x['duration'] for x in metadata)-12.07)<.15,metadata
 clean=next(a['path'] for a in p['artifacts'] if a['kind']=='AI字幕处理')
 # Final segment at the same timestamp must match the neural repaired intermediate.
 import numpy as np
 def pixels(path):
  r=subprocess.run([app.FFMPEG,'-loglevel','error','-ss','1.5','-i',str(path),'-frames:v','1','-vf','crop=534:46:360:600','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
  return np.frombuffer(r.stdout,dtype=np.uint8).astype(float)
 mae=float(np.mean(abs(pixels(clean)-pixels(files[0]))));assert mae<8,mae
 for label,path in [('原片',original),('AI修复后分集',files[0])]:
  app.ff(['-ss','1.5','-i',str(path),'-frames:v','1','-update','1',str(BASE/f'{label}.jpg')])
 assert app.sha256(original)==before==app.sha256(clip)
 record=next(a['path'] for a in p['artifacts'] if a['name']=='工程记录.json')
 outputs=json.loads(Path(record).read_text('utf-8'))['outputs'];assert {x['file'] for x in outputs}==set(files)
 report.update(ok=True,job=j,verificationSeconds=round(time.monotonic()-t,2),verifiedExistingCompletedJob=reuse,source=str(original),sourceSHA256=before,sourceUnchanged=True,
    finalVideos=files,frameCounts=frames,metadata=metadata,repairedIntermediate=clean,finalVsRepairedPixelMAE=mae,engine='STTN-auto / RTX 4060')
 report['checks']=['real_neural_subtitle_repair_then_transcode_split','362_frames_preserved','three_final_segments_with_audio','decoded_all_frames','records_match_final_segments','original_sha256_unchanged'];save();print('REAL_AI_WORKFLOW_OK',flush=True)
except Exception as e:
 report.update(ok=False,error=str(e));save();raise
finally:
 app.shutdown_jobs();http.shutdown()
