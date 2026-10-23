"""Production server + real media, simulated cloud: restart and deduplication acceptance."""
from pathlib import Path
import json,os,hashlib,sys,subprocess,time,socket,urllib.request,urllib.error
ROOT=Path(__file__).resolve().parent;META=ROOT/'tmp/current-connections-test.json';meta=json.loads(META.read_text('utf-8'));BASE=Path(meta['base']);report={'simulation':True,'realCloudGeneration':False,'checks':[]};child=None;stream=None
def api(name,body=None):
 req=urllib.request.Request(meta['url']+'/api/'+name,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Local-Client':'1'})
 with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)
def wait(jid,terminal=False,remote=False):
 for _ in range(600):
  s=api('state');j=next(j for j in s['jobs'] if j['id']==jid)
  if (terminal and j['status'] not in ['running','queued','pausing']) or (remote and j.get('remoteVideo',{}).get('taskId')):return s,j
  time.sleep(.05)
 raise TimeoutError(jid)
def check(name):report['checks'].append(name);(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(name,flush=True)
def stop():
 try:urllib.request.urlopen(urllib.request.Request(meta['url']+'/__test/crash',data=b'{}',headers={'X-Test-Token':meta['token']}),timeout=3)
 except Exception:pass
 if child:child.wait(timeout=10)
def start():
 global child,stream
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 stream=(BASE/'restart-server.log').open('ab');env=os.environ|{'MANJU_DATA':str(BASE/'data'),'MANJU_TEST_TOKEN':meta['token'],'PYTHONIOENCODING':'utf-8'}
 child=subprocess.Popen([sys.executable,str(ROOT/'test_connections_host.py'),str(port)],cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));meta.update(url=f'http://127.0.0.1:{port}',pid=child.pid);META.write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
 for _ in range(100):
  try:api('state');return
  except Exception:time.sleep(.1)
 raise TimeoutError('restarted service')
def cloud():return json.loads((BASE/'mock-cloud.json').read_text('utf-8'))
try:
 ui=json.loads((BASE/'ui/report.json').read_text('utf-8'));assert ui['ok'],ui
 ids=ui['connectionIds'];state=api('state');selection=state['config']['aiSelection']|{'video':'auto'};api('config',{'aiSelection':selection})
 original=BASE/'fixtures/原始样片/01.mp4';before=hashlib.sha256(original.read_bytes()).hexdigest()
 n=len(cloud()['created']);jid=api('jobs',{'kind':'video_generate','ids':[],'video':{'name':'文生视频恢复验收','prompt':'小猫在月光下走过草地。','mode':'text'}})['id'];s,j=wait(jid,remote=True);task_id=j['remoteVideo']['taskId'];api('jobs/control',{'id':jid,'action':'pause'});s,j=wait(jid,terminal=True);assert j['status']=='paused',j
 assert len(cloud()['created'])==n+1;check('video_cloud_id_persisted_and_local_poll_pause')
 stop();start();s=api('state');assert s['config']['aiRouting']['video']['autoFallback'];assert not any(s['connectionKeyStatus'].values());assert next(j for j in s['jobs'] if j['id']==jid)['remoteVideo']['taskId']==task_id
 api('ai/connection-key',{'id':ids['videoA'],'value':'fixture-secret-video-a'});api('jobs/control',{'id':jid,'action':'resume'});s,j=wait(jid,terminal=True);assert j['status']=='completed',j;assert len(cloud()['created'])==n+1;check('fresh_process_resume_polls_original_cloud_task_without_resubmit')
 generated=j['result'];assert Path(generated['path']).is_file();ff=ROOT/'vendor/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe';subprocess.run([str(ff),'-loglevel','error','-i',generated['path'],'-f','null','-'],check=True,capture_output=True)
 check('downloaded_video_decodes_and_is_registered_in_library')
 # A request can be accepted while the client loses the reply. No automatic re-create is allowed.
 api('ai/connection-key',{'id':ids['videoB'],'value':'fixture-secret-timeout'});selection=s['config']['aiSelection']|{'video':ids['videoB']};api('config',{'aiSelection':selection})
 n=len(cloud()['created']);unknown=api('jobs',{'kind':'video_generate','ids':[],'video':{'name':'提交超时恢复验收','prompt':'小猫看向镜头。'}})['id'];s,j=wait(unknown,terminal=True);assert j['status']=='failed' and j['remoteVideo']['status']=='submission_unknown',j;assert len(cloud()['created'])==n+1
 api('jobs/control',{'id':unknown,'action':'resume'});s,j=wait(unknown,terminal=True);assert j['status']=='failed' and len(cloud()['created'])==n+1;check('uncertain_submission_never_falls_back_or_reposts_on_retry')
 actual=cloud()['created'][-1]['id'];api('jobs/attach-remote',{'id':unknown,'taskId':actual});api('jobs/control',{'id':unknown,'action':'resume'});s,j=wait(unknown,terminal=True);assert j['status']=='completed' and len(cloud()['created'])==n+1;check('attach_existing_cloud_id_and_continue_successfully')
 # Generated media is a normal input for existing local processing.
 local=api('jobs',{'kind':'transcode','ids':[generated['projectId']]})['id'];s,j=wait(local,terminal=True);assert j['status']=='completed',j;check('generated_video_can_enter_existing_local_processing_pipeline')
 subtitle=api('ai/connections',{'connection':{'id':'subtitle_fixture','name':'字幕服务验收','channel':'subtitle','provider':'custom','protocol':'subtitle_json','base':'https://mock.invalid/v1','model':''}})['id']
 api('ai/connection-key',{'id':subtitle,'value':'fixture-secret-subtitle'});api('config',{'subtitleMode':'cloud'})
 p=next(p for p in api('state')['projects'] if Path(p['source'])==original.parent)
 sjid=api('jobs',{'kind':'subtitle','ids':[p['id']]})['id'];s,j=wait(sjid,terminal=True);assert j['status']=='completed',j
 assert any(e['connectionId']==subtitle and e['event']=='succeeded' for e in j['aiAttempts']);check('cloud_subtitle_uses_selected_connection_and_async_polling')
 raw=(BASE/'data/state.json').read_text('utf-8')+(BASE/'data/jobs.json').read_text('utf-8')
 for secret in ['fixture-secret-primary','fixture-secret-backup','fixture-secret-image','fixture-secret-video-a','fixture-secret-video-b','fixture-secret-timeout','fixture-secret-subtitle']:assert secret not in raw
 assert hashlib.sha256(original.read_bytes()).hexdigest()==before;check('credentials_not_persisted_and_original_video_unchanged')
 bad=s['config']['aiConnections'][0]|{'apiKey':'should-not-save'}
 try:api('ai/connections',{'connection':bad});raise AssertionError('Secret field accepted')
 except urllib.error.HTTPError as e:assert e.code==400
 assert 'should-not-save' not in (BASE/'data/state.json').read_text('utf-8');check('credential_fields_rejected_in_saved_connection_configuration')
 report.update(ok=True,jobs={'resumedVideo':jid,'unknownSubmission':unknown,'localProcessing':local},generated=generated)
except Exception as e:report.update(ok=False,error=str(e));raise
finally:
 (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');stop()
 if stream:stream.close()
