"""Isolated HTTP acceptance after retiring AI video generation; no external calls."""
from pathlib import Path
import base64,copy,http.cookiejar,io,json,os,shutil,sys,tempfile,threading,time,urllib.request,urllib.error
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='connections-retired-',dir=ROOT/'tmp'));DATA=BASE/'data';DATA.mkdir()
os.environ['MANJU_DATA']=str(DATA);os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
def entry(cid,channel,protocol):return dict(id=cid,name=cid,channel=channel,provider='custom',protocol=protocol,base='https://mock.invalid/v1',model='fixture-model',enabled=True)
connections=[entry('text_fixture','text','chat'),entry('image_fixture','image','openai_images'),entry('subtitle_fixture','subtitle','subtitle_json'),entry('retired_video','video','ark_video')]
legacy={'aiConnections':connections,'aiRouting':{c['channel']:{'primary':c['id'],'backups':[],'autoFallback':False} for c in connections},'aiSelection':{c['channel']:c['id'] for c in connections}}
(DATA/'state.json').write_text(json.dumps({'config':legacy,'projects':[],'accounts':[],'logs':[]}),'utf-8')
history=BASE/'historical-result.mp4'
(DATA/'jobs.json').write_text(json.dumps([{'id':'old_queued','kind':'video_generate','status':'queued','config':legacy,'ids':[],'created':1}, {'id':'old_done','kind':'video_generate','status':'completed','config':legacy,'ids':[],'created':1,'stage':'旧生成完成','result':{'path':str(history)}}]),'utf-8')
import server as s,local_session,media_download
from PIL import Image
checks=[];report={'base':str(BASE),'checks':checks,'ok':False,'cloudResponses':'simulated; no real API call'}
def check(name,value=True):
 assert value,name
 checks.append(name);print('PASS '+name,flush=True)
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();threading.Thread(target=host.serve_forever,daemon=True).start();url='http://127.0.0.1:'+str(host.server_address[1]);client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));client.open(url+'/launch/'+host.session.launch).close()
def api(name,body=None):
 req=urllib.request.Request(url+'/api/'+name,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Local-Client':'1'})
 with client.open(req,timeout=30) as response:return json.load(response)
def reject(name,body,check_name):
 try:api(name,body)
 except urllib.error.HTTPError as error:check(check_name,error.code in (400,404))
 else:raise AssertionError(check_name)
def wait(jid):
 end=time.monotonic()+90
 while time.monotonic()<end:
  row=next(j for j in api('state')['jobs'] if j['id']==jid)
  if row['status'] not in ('queued','running','pausing'):
   assert row['status']=='completed',row
   return row
  time.sleep(.1)
 raise TimeoutError(jid)
try:
 s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=1.2','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(history)])
 old_hash=s.sha256(history);initial=api('state')
 check('legacy_video_connection_and_routes_removed',len(initial['config']['aiConnections'])==3 and 'video' not in initial['config']['aiRouting'] and 'video' not in initial['config']['aiSelection'])
 check('text_image_subtitle_configuration_preserved',{c['id'] for c in initial['config']['aiConnections']}=={'text_fixture','image_fixture','subtitle_fixture'})
 retired=next(j for j in initial['jobs'] if j['id']=='old_queued');done=next(j for j in initial['jobs'] if j['id']=='old_done')
 check('old_queued_generation_cannot_auto_run',retired['status']=='cancelled' and retired['moduleRetired'] and not retired['resumable'])
 check('completed_generation_history_and_media_preserved',done['status']=='completed' and done['result']['path']==str(history) and history.is_file())
 reject('jobs',{'kind':'video_generate','ids':[],'video':{'prompt':'unused'}},'video_generation_submission_rejected')
 reject('jobs/control',{'id':'old_queued','action':'resume'},'retired_generation_resume_rejected')
 reject('jobs/attach-remote',{'id':'old_queued','taskId':'unused'},'old_task_attachment_endpoint_removed')
 reject('ai/connections',{'connection':entry('blocked_video','video','ark_video')},'video_connection_creation_rejected')
 check('generation_implementation_absent',not hasattr(s,'generate_video') and 'video_generate' not in s.LOCAL_JOB_KINDS and not (ROOT/'video_api.py').exists())
 folder=BASE/'source';folder.mkdir();shutil.copy2(history,folder/'01.mp4');(folder/'简介.txt').write_text('测试角色寻找伙伴，然后一起回家。','utf-8')
 api('config',{'output':str(BASE/'output'),'width':320,'height':180,'regroup':False,'subtitleMode':'cloud','autoText':False,'autoCover':False,'autoRecords':False})
 p=api('scan',{'source':str(folder)})['projects'][0];pid=p['id'];api('project',{'id':pid,'rights':True})
 for cid in ('text_fixture','image_fixture','subtitle_fixture'):api('ai/connection-key',{'id':cid,'value':'fixture-session-'+cid})
 image=io.BytesIO();Image.new('RGB',(64,64),'#9d86c7').save(image,'PNG');calls=[]
 def request(endpoint,payload=None,*a,**k):
  calls.append(endpoint)
  if endpoint.endswith('/chat/completions'):return {'model':'fixture-model','choices':[{'message':{'content':json.dumps({'title':'星河归家之旅','synopsis':'伙伴们寻找彼此并一同回家。'},ensure_ascii=False)}}]}
  if endpoint.endswith('/images/generations'):return {'data':[{'b64_json':base64.b64encode(image.getvalue()).decode()}]}
  if endpoint.endswith('/video/clear'):return {'status':'completed','video_url':'https://cdn.mock.invalid/subtitle-result.mp4'}
  raise AssertionError('Unexpected network call '+endpoint)
 def download(endpoint,target,cancel,**kwargs):
  assert endpoint=='https://cdn.mock.invalid/subtitle-result.mp4';shutil.copy2(history,target)
 with patch.object(s.ai,'request_json',request),patch.object(media_download,'download',download):
  rewritten=wait(api('jobs',{'kind':'rewrite','ids':[pid]})['id']);check('text_generation_still_works',rewritten['status']=='completed')
  cover=wait(api('jobs',{'kind':'coverAI','ids':[pid]})['id']);check('image_cover_still_works',cover['status']=='completed')
  subtitle=wait(api('jobs',{'kind':'subtitle','ids':[pid]})['id']);check('cloud_subtitle_and_result_download_still_work',subtitle['status']=='completed')
 artifacts=api('state')['projects'][0]['artifacts'];result=next(a for a in artifacts if a['job']==subtitle['id']);check('cloud_subtitle_result_is_playable_with_audio',s.probe(result['path'])['audio'])
 check('no_generation_submission_or_polling_calls',len(calls)==3 and all(not x.endswith('/videos') and '/contents/generations/tasks' not in x for x in calls))
 check('session_keys_not_written_to_disk','fixture-session-' not in (DATA/'state.json').read_text('utf-8'))
 check('historical_video_file_unchanged',s.sha256(history)==old_hash)
 # Exercise the remaining real downloader against a controlled HTTPS response.
 class Response(io.BytesIO):
  headers={'Content-Length':'4'}
  def geturl(self):return 'https://cdn.mock.invalid/result.mp4'
 with patch.object(media_download.urllib.request,'urlopen',lambda *a,**k:Response(b'mp4!')):
  target=BASE/'download-test.mp4';media_download.download('https://cdn.mock.invalid/result.mp4',target,threading.Event());check('shared_https_download_helper_preserved',target.read_bytes()==b'mp4!')
 api('config',{'subtitleMode':'local'})
 report.update(ok=True,projectId=pid)
finally:
 s.shutdown_jobs();host.shutdown();host.server_close();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/connections-retirement-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(checks),'base':str(BASE)},ensure_ascii=False))
