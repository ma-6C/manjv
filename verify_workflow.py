"""Real HTTP/media acceptance, including process restart and checkpoint reuse."""
from pathlib import Path
import os,json,subprocess,sys,time,socket,urllib.request,zipfile,shutil,secrets
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'tmp'/'workflow-acceptance'/time.strftime('%Y%m%d-%H%M%S');BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'helper-data')
import server as media
report={'base':str(BASE),'checks':[]};proc=None;logs=[];token=secrets.token_hex(24)
def check(name,**details):report['checks'].append({'name':name,**details});(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(name,flush=True)
def start():
 global proc,url
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 env=os.environ|{'MANJU_DATA':str(BASE/'data'),'PYTHONIOENCODING':'utf-8','MANJU_TEST_TOKEN':token}
 log=(BASE/f'server-{len(logs)}.log').open('wb');logs.append(log)
 proc=subprocess.Popen([sys.executable,str(ROOT/'test_workflow_host.py'),str(port)],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));url=f'http://127.0.0.1:{port}/api/'
 for _ in range(100):
  try:api('state');return
  except Exception:
   if proc.poll() is not None:raise RuntimeError('Test service failed to start')
   time.sleep(.1)
 raise TimeoutError('Test service startup')
def stop():
 global proc
 if proc and proc.poll() is None:
  try:
   req=urllib.request.Request(url.replace('/api/','/__test/crash'),data=b'{}',headers={'X-Test-Token':token})
   urllib.request.urlopen(req,timeout=5)
  except Exception:pass
  proc.wait(timeout=15)
 proc=None
def api(name,body=None):
 req=urllib.request.Request(url+name,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Local-Client':'1'})
 with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
def wait(jid,timeout=120):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  state=api('state');job=next(j for j in state['jobs'] if j['id']==jid)
  if job['status'] not in ['queued','running','pausing']:
   assert job['status']=='completed',job
   return job,next(p for p in state['projects'] if p['id']==job['ids'][0])
  time.sleep(.1)
 raise TimeoutError(jid)
def pixels(path):
 p=subprocess.run([media.FFMPEG,'-loglevel','error','-ss','0.3','-i',str(path),'-frames:v','1','-vf','crop=120:20:100:132','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
 import numpy as np
 return np.frombuffer(p.stdout,dtype=np.uint8).astype(float)
try:
 source=BASE/'source';flow=source/'flow';recovery=source/'recovery';flow.mkdir(parents=True);recovery.mkdir()
 for i,d in enumerate([2.2,1.8]):
  media.ff(['-f','lavfi','-i',f'testsrc2=s=320x180:r=30:d={d}','-vf','drawbox=x=75:y=130:w=170:h=25:color=red:t=fill','-c:v','libx264','-pix_fmt','yuv420p',str(flow/f'{i+1}.mp4')])
 media.ff(['-f','lavfi','-i','color=c=blue:s=1254x720:r=30:d=0.6','-c:v','libx264','-pix_fmt','yuv420p',str(recovery/'1.mp4')])
 clip=json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source'];shutil.copy2(clip,recovery/'2.mp4')
 original={str(p):media.sha256(p) for p in source.rglob('*.mp4')}
 start();api('config',{'source':str(source),'output':str(BASE/'output'),'width':320,'height':180,'segmentSeconds':1.5,'parallel':1,'regroup':True,
  'subtitleAuto':True,'subtitleFirst':1,'subtitleMode':'local','subtitleRegions':[{'x':.18,'y':.7,'w':.64,'h':.2}],
  'pipelineHighlight':True,'highlightMin':.5,'highlightMax':.5,'highlightCount':1,'highlightRandom':False,'autoCover':True,'autoRecords':True})
 projects=api('scan',{'source':str(source)})['projects'];p=next(p for p in projects if p['name']=='flow');rp=next(p for p in projects if p['name']=='recovery')
 api('project',{'id':p['id'],'intro':'Real local workflow test.','rights':True})
 jid=api('jobs',{'kind':'pipeline','ids':[p['id']]})['id'];job,p=wait(jid)
 finals=[a for a in p['artifacts'] if a['path'] in p['finalVideoPaths']];clean=[a for a in p['artifacts'] if a['kind']=='字幕处理'];segments=[a for a in p['artifacts'] if a['kind']=='视频']
 assert len(finals)==3 and len(clean)==2 and len(segments)==3,(len(finals),len(clean),len(segments))
 assert all(a['kind']=='高光视频' for a in finals)
 import numpy as np
 err_clean=float(np.mean(np.abs(pixels(segments[0]['path'])-pixels(clean[0]['path']))));err_source=float(np.mean(np.abs(pixels(segments[0]['path'])-pixels(flow/'1.mp4'))))
 assert err_clean<12 and err_source>15,(err_clean,err_source)
 for a in finals:media.ff(['-i',a['path'],'-f','null','-'])
 assert abs(media.probe(finals[0]['path'])['duration']-2.25)<.15
 check('pipeline_uses_repaired_video_then_split_then_highlight',finalCount=len(finals),cleanedDifference=err_clean,sourceDifference=err_source)
 record=next(a for a in p['artifacts'] if a['name']=='工程记录.json');manifest=json.loads(Path(record['path']).read_text('utf-8'));assert {x['file'] for x in manifest['outputs']}==set(p['finalVideoPaths'])
 package_job=api('jobs',{'kind':'package','ids':[p['id']]})['id'];_,p=wait(package_job)
 package=next(a for a in p['artifacts'] if a['job']==package_job and a['kind']=='发布包')
 with zipfile.ZipFile(package['path']) as z:
  assert z.testzip() is None
  video_names=[n for n in z.namelist() if n.endswith('.mp4')];assert len(video_names)==3 and all(n.startswith('高光视频/') for n in video_names)
 check('package_and_records_reference_only_final_outputs')
 rescanned=api('scan',{'source':str(flow)})['projects'][0]
 assert rescanned['finalVideoPaths']==p['finalVideoPaths']
 check('rescan_preserves_final_video_selection')
 api('config',{'width':1254,'height':720,'subtitleAuto':False,'pipelineHighlight':False,'autoCover':False,'autoRecords':False,'regroup':False})
 first=api('jobs',{'kind':'transcode','ids':[rp['id']]})['id']
 queued=api('jobs',{'kind':'preview','ids':[rp['id']],'videoIndex':0,'start':0,'seconds':5})['id']
 pending=next(j for j in api('state')['jobs'] if j['id']==queued);assert pending['status']=='queued',pending
 api('jobs/control',{'id':queued,'action':'pause'})
 end=time.monotonic()+90;key=f'{rp["id"]}:encode:0'
 while time.monotonic()<end:
  journal=json.loads((BASE/'data/jobs.json').read_text('utf-8'));item=next(j for j in journal if j['id']==first)
  if key in item['checkpoints']:
   saved=item['checkpoints'][key]['files'][0];break
  time.sleep(.03)
 else:raise TimeoutError('First video checkpoint')
 api('jobs/control',{'id':first,'action':'pause'})
 for _ in range(200):
  item=next(j for j in api('state')['jobs'] if j['id']==first)
  if item['status']=='paused':break
  time.sleep(.03)
 assert item['status']=='paused',item
 checkpoint_file=Path(saved['path']);mtime=checkpoint_file.stat().st_mtime_ns
 check('queue_and_pause_preserve_completed_source_video')
 api('jobs/control',{'id':first,'action':'resume'})
 for _ in range(100):
  if next(j for j in api('state')['jobs'] if j['id']==first)['status']=='running':break
  time.sleep(.01)
 stop();start();restored=next(j for j in api('state')['jobs'] if j['id']==first);assert restored['status']=='interrupted',restored
 assert checkpoint_file.stat().st_mtime_ns==mtime
 api('jobs/control',{'id':first,'action':'resume'});completed,rp=wait(first)
 # Finished encode temporaries are removed; the checkpoint journal keeps the original mtime as proof of reuse.
 history=next(j for j in json.loads((BASE/'data/jobs.json').read_text('utf-8')) if j['id']==first)
 assert history['checkpoints'][key]['files'][0]['mtime']==mtime
 check('forced_process_restart_and_resume_reuse_checkpoint',attempts=completed['attempts'])
 api('jobs/control',{'id':queued,'action':'resume'});preview,rp=wait(queued)
 assert media.probe(preview['result']['before'])['duration']<.8
 assert Path(preview['result']['after']).is_file()
 check('preview_handles_short_tail_and_survives_restart')
 # A second source edit invalidates the old task instead of silently reusing stale files.
 cancel_id=api('jobs',{'kind':'preview','ids':[rp['id']],'videoIndex':0,'start':0,'seconds':5})['id']
 api('jobs/control',{'id':cancel_id,'action':'pause'});time.sleep(.3)
 source_file=recovery/'1.mp4';old=source_file.stat().st_mtime;os.utime(source_file,(old+2,old+2))
 try:api('jobs/control',{'id':cancel_id,'action':'resume'});raise AssertionError('Changed source accepted')
 except urllib.error.HTTPError as e:assert e.code==400
 assert all(media.sha256(path)==sha for path,sha in original.items())
 check('changed_sources_block_resume_and_original_bytes_unchanged')
 report['ok']=True;report['flowProjectId']=p['id'];report['recoveryProjectId']=rp['id'];report['finalVideos']=[a['path'] for a in finals]
 (ROOT/'tmp/current-workflow-acceptance.json').write_text(json.dumps({'base':str(BASE),'report':str(BASE/'report.json')},ensure_ascii=False,indent=2),'utf-8')
except Exception as e:report['ok']=False;report['error']=str(e);raise
finally:
 stop()
 for log in logs:log.close()
 (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
