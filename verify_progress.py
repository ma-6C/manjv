"""Real FFmpeg / local VSR acceptance, plus isolated protocol and cancellation checks."""
from pathlib import Path
import argparse,os,sys,json,threading,time,subprocess,copy,io,urllib.request
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--compiled',action='store_true');parser.add_argument('--ai',action='store_true');args=parser.parse_args()
BASE=ROOT/'tmp/progress-acceptance'/time.strftime('%Y%m%d-%H%M%S');BASE.mkdir(parents=True,exist_ok=True)
os.environ['MANJU_DATA']=str(BASE/'data')
sys.path[:0]=[str(ROOT/'vendor')]
if args.compiled:sys.path.insert(0,str(ROOT/'release/v0.7.0/漫剧工坊/_internal'))
import server as s,task_progress as tp,video_api
report={'compiled':args.compiled,'core':s.__file__,'checks':[],'realCloudCalls':False,'base':str(BASE)}
def check(name,**details):
 report['checks'].append({'name':name,**details});(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(name,flush=True)
def bare(name):
 j={'id':name,'kind':'transcode','status':'running','ids':[],'cancel':threading.Event(),'processes':set(),'created':time.time(),'config':{}}
 s.JOBS[name]=j;return j
def running(callback):
 errors=[]
 def work():
  try:callback()
  except Exception as e:errors.append(e)
 th=threading.Thread(target=work);th.start();return th,errors

source=BASE/'source';source.mkdir();video=source/'01.mp4'
s.ff(['-f','lavfi','-i','testsrc2=s=640x360:r=30:d=6','-f','lavfi','-i','sine=frequency=440:duration=6','-c:v','libx264','-preset','ultrafast','-c:a','aac','-pix_fmt','yuv420p',str(video)])
before=s.sha256(video)
j=bare('measured-ffmpeg');out=BASE/'encoded.mp4'
thread,errors=running(lambda:s.ff(['-re','-i',str(video),'-c:v','libx264','-preset','fast','-c:a','aac','-t','6',str(out)],j['id']))
observed=[];deadline=time.time()+25
while thread.is_alive() and time.time()<deadline:
 row=tp.snapshot(j)['current']
 if row and row.get('completed',0)>0:observed.append(copy.deepcopy(row))
 time.sleep(.1)
thread.join(5);assert not thread.is_alive() and not errors,errors
assert len({r['completed'] for r in observed})>=3 and any(0<r['percent']<99.9 for r in observed),observed
assert any(r['speed'] is not None and r['etaSeconds'] is not None for r in observed)
assert s.probe(out)['audio'] and abs(s.probe(out)['duration']-6)<.2
check('real_ffmpeg_progress_changes_before_process_exit',samples=len(observed),first=observed[0]['completed'],last=observed[-1]['completed'])
check('measured_speed_eta_after_sampling_and_output_audio_duration_validated')

j2=bare('parallel-isolation');a=tp.begin(j2,'编码','a.mp4',10);b=tp.begin(j2,'编码','b.mp4',20)
tp.advance(j2,a,3);tp.advance(j2,b,12);rows=tp.snapshot(j2)['rows'];assert rows[0]['percent']==30 and rows[1]['percent']==60
tp.advance(j2,a,11);assert tp.snapshot(j2)['rows'][0]['percent']==99.9
tp.finalizing(j2,a);assert tp.snapshot(j2)['rows'][0]['percent'] is None
tp.settle(j2,'paused');assert all(r['etaSeconds'] is None and r['status']=='paused' for r in tp.snapshot(j2)['rows'])
check('parallel_items_independent_and_100_percent_requires_validation')
model=bare('engine-parser');tid=tp.begin(model,'加载模型',unit='frames');assert tp.snapshot(model)['current']['percent'] is None
tp.vsr_event(model,tid,'Subtitle Removing: 42%|xxxxx    | 1512/3600 [00:42<00:58, 36frame/s]')
assert tp.snapshot(model)['current']['completed']==1512
tp.vsr_event(model,tid,'Subtitle Removing: 100%|xxxxxxxxxx| 3600/3600 [00:42<00:00]')
assert tp.snapshot(model)['current']['status']=='finalizing' and tp.snapshot(model)['current']['percent'] is None
check('vsr_frame_protocol_and_unknown_loading_and_audio_finalization')

j3=bare('pause-encoder');thread,errors=running(lambda:s.ff(['-re','-i',str(video),'-c:v','libx264','-t','6',str(BASE/'cancelled.mp4')],j3['id']))
limit=time.time()+5
while not j3['processes'] and time.time()<limit:time.sleep(.05)
assert j3['processes'];j3['cancel'].set();thread.join(8);assert not thread.is_alive() and errors and isinstance(errors[0],InterruptedError),errors
tp.settle(j3,'paused');assert not j3['processes'];check('cancel_during_active_progress_terminates_owned_encoder_without_deadlock')

class Response(io.BytesIO):
 def __init__(self,payload,length=None):super().__init__(payload);self.headers={} if length is None else {'Content-Length':str(length)}
 def geturl(self):return 'https://test.invalid/result.mp4'
payload=video.read_bytes();events=[]
with patch.object(urllib.request,'urlopen',return_value=Response(payload,len(payload))):video_api.download('https://test.invalid/result.mp4',BASE/'download.mp4',threading.Event(),progress=lambda n,t:events.append((n,t)))
assert events[0]==(0,len(payload)) and events[-1]==(len(payload),len(payload));assert (BASE/'download.mp4').read_bytes()==payload
check('download_measures_bytes_and_known_length')
events=[]
with patch.object(urllib.request,'urlopen',return_value=Response(payload)):video_api.download('https://test.invalid/result.mp4',BASE/'unknown-length.mp4',threading.Event(),progress=lambda n,t:events.append((n,t)))
assert all(t is None for n,t in events);check('unknown_content_length_never_fabricates_percentage')
with patch.object(urllib.request,'urlopen',return_value=Response(payload,len(payload)+10)):
 try:video_api.download('https://test.invalid/result.mp4',BASE/'truncated.mp4',threading.Event())
 except ValueError:pass
 else:raise AssertionError('truncated accepted')
assert not (BASE/'truncated.mp4').exists();check('truncated_download_not_promoted_to_output')
j2.update(config={'apiKey':'TEST-SECRET-NOT-FOR-EXPORT'},error='TEST-SECRET-NOT-FOR-EXPORT C:/Users/private/path',status='failed')
diagnostic=json.dumps(tp.report(j2));assert 'TEST-SECRET' not in diagnostic and 'private/path' not in diagnostic
check('diagnostic_allowlist_excludes_config_raw_errors_and_paths')

if args.ai:
 original=Path(r'D:\weixin_wenjian\xwechat_files\wxid_qet5grsgoecp22_d214\msg\video\2026-10\7ecdbee6fa3a89ad314f90ed019be92c.mp4')
 engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
 # Prefer previously imported portable engine to prove that the client v1 ZIP remains compatible.
 import engine_manager
 portable=engine_manager.active(ROOT/'tmp/engine-installed-data')
 if portable:engine={'root':portable['root'],'python':portable['python']}
 sampledir=BASE/'有字幕样片';sampledir.mkdir();sample=sampledir/'01.mp4'
 originalhash=s.sha256(original)
 s.ff(['-i',str(original),'-t','5','-c:v','libx264','-preset','fast','-c:a','aac',str(sample)])
 s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'ai-output'),'subtitleMode':'vsr','vsrRoot':engine['root'],'vsrPython':engine['python'],'vsrMode':'sttn-auto','subtitleFirst':1,'subtitleRegions':[{'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}]})
 project=s.scan(str(sampledir))['projects'][0];jid=s.create_job({'kind':'subtitle','ids':[project['id']]})['id'];samples=[];deadline=time.time()+180
 while time.time()<deadline:
  j=s.JOBS[jid];t=tp.snapshot(j)
  if t.get('current'):samples.append(t['current'])
  if j.get('finished'):break
  time.sleep(.05)
 assert j['status']=='completed',j.get('error')
 measured=[r for r in samples if r['unit']=='frames' and r['completed']>0]
 assert measured,'AI completed but did not emit any measured frame progress'
 outputs=[a for a in project['artifacts'] if a['job']==jid];assert outputs and s.probe(outputs[0]['path'])['audio'];assert s.sha256(original)==originalhash
 check('real_portable_v1_ai_subtitle_model_reports_frame_progress_and_preserves_audio_source',samples=len(measured),frames=max(r['completed'] for r in measured),portable=bool(portable),output=outputs[0]['path'])
assert s.sha256(video)==before;check('original_video_unchanged')
report['ok']=True;(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/latest-progress-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
s.shutdown_jobs();print('PROGRESS_ACCEPTANCE_OK',len(report['checks']),flush=True)
