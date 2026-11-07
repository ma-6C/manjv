from pathlib import Path
import base64,copy,json,os,shutil,sys,tempfile,threading,time
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='content-settings-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,local_session
s.STATE['projects']=[{'id':'fixture','name':'设置核验剧集','originalName':'设置核验剧集','intro':'这里是尚未编辑的简介。','videos':[],'artifacts':[],'cover':'','notes':'','review':'待准备','rights':True,'source':str(BASE),'status':'待处理'}]
def entry(cid,channel):return dict(id=cid,name=cid,channel=channel,provider='custom',protocol={'text':'chat','image':'openai_images','subtitle':'subtitle_json'}[channel],base='https://fixture.invalid/v1',model='old-'+channel,enabled=True)
s.STATE['config'].update(aiConnections=[entry('saved-text','text'),entry('saved-image','image'),entry('saved-subtitle','subtitle')],aiRouting={channel:{'primary':'saved-'+channel,'backups':[],'autoFallback':False} for channel in ['text','image','subtitle']},aiSelection={'text':'auto','image':'auto','subtitle':'saved-subtitle'},subtitleEndpoint='https://subtitle.invalid/clear',subtitlePoll='https://subtitle.invalid/status')
s.STATE['config']=s.validate_config(s.STATE['config']);s.save()
subtitle_fixture=os.environ.get('MANJU_SUBTITLE_FIXTURE')=='1'
storage_fixture=os.environ.get('MANJU_STORAGE_FIXTURE')=='1'
if subtitle_fixture or storage_fixture:
    source=BASE/'source';source.mkdir();video=source/'fixture.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=15:duration=6','-f','lavfi','-i','sine=frequency=440:duration=6','-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(video)])
    s.STATE['projects'][0].update(videos=s.video_entries([video]),source=str(source));s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='local',gpu=False);s.save()
if storage_fixture:
    import jianying_projects as j
    entry=s.STATE['projects'][0]['videos'][0]
    def run(command,**kwargs):return s.subprocess.check_output(command,stderr=s.subprocess.STDOUT,**kwargs)
    generated=j.generate(entry,{'sourceSHA256':j.sha(video),'segments':[{'start':0,'end':3},{'start':3,'end':6}]},BASE/'原工程',s.FFMPEG,run,threading.Event())
    generated.update(projectId='fixture',sourcePath=str(video))
    folder=Path(generated['directory']);moved=BASE/'移动后的工程'/folder.name;moved.parent.mkdir()
    assert folder.is_relative_to(BASE) and moved.is_relative_to(BASE)
    folder.rename(moved)
    s.JOBS['moved-draft']={'id':'moved-draft','kind':'jianying_project','ids':['fixture'],'status':'completed','created':time.time(),'config':copy.deepcopy(s.STATE['config']),'cancel':threading.Event(),'processes':set(),
        'options':{'jianyingVideos':[{'projectId':'fixture','path':str(video),'name':video.name}]},'jianyingResults':[generated],'checkpoints':{},'stage':'草稿已生成，待出图','progress':100}
    s.save()
fixture_tasks={}
def request(url,payload=None,key='',protocol='chat',**kwargs):
    row={'url':url,'model':payload.get('model') if payload else None,'keyPresent':bool(key)}
    with (BASE/'calls.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
    if key=='fixture-invalid':raise s.ai.ProviderError('HTTP 401 · new_api_error：密钥无效或已失效，请重新复制有效的 API 密钥。','new_api_error',401)
    if '/models' in url:
        if 'slow.fixture.invalid' in url:time.sleep(1.5)
        if 'empty.fixture.invalid' in url:return {'data':[]}
        if 'unsupported.fixture.invalid' in url:raise s.ai.ProviderError('平台不支持模型查询，请手动填写模型 ID。','HTTPError',404)
        if 'catalog.fixture.invalid' in url:return {'data':[{'id':'fixture-text-alpha'},{'id':'fixture-text-beta'},{'id':'fixture-image-one'}]+[{'id':'extra-model-'+str(i)} for i in range(600)]}
        if 'subtitle.fixture.invalid' in url:return {'data':[{'id':'erase-alpha'},{'id':'erase-beta'},{'id':'language-only'}]}
        return {'data':[{'id':'fixture-image'}]}
    if subtitle_fixture and url.endswith(('/tasks/erase','/video/clear')):
        task='subtitle-'+str(len(fixture_tasks)+1);target=BASE/(task+'.mp4');target.write_bytes(base64.b64decode(payload['video_base64']));fixture_tasks[task]=target
        return {'task_id':task,'status':'running'}
    if subtitle_fixture and url.endswith(('/tasks/status','/video/status')):
        return {'status':'completed','video_url':'https://cdn.fixture.invalid/'+payload['task_id']+'.mp4'}
    return {'model':payload['model'],'choices':[{'message':{'content':'OK'}}],'usage':{'total_tokens':2}}
s.ai.request_json=request
if subtitle_fixture:
    def download(url,target,cancel,**kwargs):
        task=url.rsplit('/',1)[-1].removesuffix('.mp4')
        if not url.startswith('https://cdn.fixture.invalid/') or task not in fixture_tasks:raise AssertionError('unexpected fixture URL')
        shutil.copy2(fixture_tasks[task],target)
    s.media_download.download=download
s.environment=lambda *args,**kwargs:{'gpu':{'ready':False,'detail':'isolated settings fixture'},'ffmpeg':bool(s.FFMPEG),'fonts':True,'cpu':4,'python':sys.version.split()[0]}
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1]);meta={'base':str(BASE),'url':url,'launch':url+'/launch/'+host.session.launch}
if storage_fixture:meta['movedDraft']=str(moved)
(ROOT/'tmp/content-settings-host.json').write_text(json.dumps(meta),'utf-8');print(json.dumps(meta),flush=True)
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
