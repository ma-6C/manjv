"""Real-media local publishing workflow and HTTP session contract checks.

Browser results in this file use an explicit controlled double. Official-page
read-only and real Edge form checks live in verify_publish_browser.py.
"""
from pathlib import Path
import copy, http.cookiejar, json, os, shutil, sys, tempfile, threading, time
import urllib.error, urllib.request
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='publish-workflow-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s
import publish_workflow as w
import local_session
from PIL import Image,ImageDraw

report={'base':str(BASE),'checks':[],'realMedia':True,'officialSubmissionTested':False,'ok':False}
def check(name,condition=True):
    assert condition,name
    report['checks'].append(name);print('PASS '+name,flush=True)
def rejects(fn):
    try:fn()
    except (ValueError,PermissionError):return True
    return False
def wait(task_id):
    end=time.monotonic()+30
    while time.monotonic()<end:
        task=next(t for t in svc.public()['tasks'] if t['id']==task_id)
        if task['status'] not in ('queued','running'):return task
        time.sleep(.03)
    raise AssertionError('Publishing task timed out')
class BrowserDouble:
    def __init__(self,data):self.calls=[];self.release=threading.Event();self.release.set()
    def command(self,account,action,payload):
        self.calls.append((account['id'],action,payload));self.release.wait(10)
        return {'loginState':'login_required','state':'needs_login','filled':[],'pending':[],
                'submitted':False,'uploadCompleted':False,'browserOpen':action!='close'}
    def shutdown(self):self.release.set()

host=None
try:
    source=BASE/'原素材';source.mkdir()
    video=source/'原始视频.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=12:duration=1.25',
          '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-shortest',
          '-c:v','libx264','-preset','ultrafast','-c:a','aac',str(video)])
    pid=s.scan(str(source))['projects'][0]['id'];project=s.get_project(pid)
    project.update(name='提审链路验收样片',intro='本地自动化验收样片，不用于平台提交。')
    s.STATE['config']['output']=str(BASE/'output')
    s.STATE['accounts']=[{'id':'test_account','name':'验收专用账号备注','type':'剧集提审','channelId':''}]
    svc=s.publish_workspace();svc.browser_factory=BrowserDouble
    missing=svc.inspect(pid)
    check('原始素材不冒充成片，缺项先列出',not missing['ready'] and not missing['files']['videos'])
    check('缺资料不会创建导出或浏览器任务',rejects(lambda:svc.export(pid)) and rejects(lambda:svc.browser('test_account','assist',pid)) and not svc.public()['tasks'])
    check('设置只接受允许的字段',rejects(lambda:svc.settings(pid,{'apiKey':'fixture'})))
    check('配置集数拒绝布尔和非整数',rejects(lambda:svc.settings(pid,{'episodeCount':True})))
    check('配置金额拒绝无限值',rejects(lambda:svc.settings(pid,{'totalCostYuan':float('inf')})))
    final=BASE/'完成视频';final.mkdir();finished=final/'第01集.mp4';shutil.copy2(video,finished)
    project['artifacts']=[{'path':str(finished),'name':finished.name,'kind':'视频','job':'fixture','bytes':finished.stat().st_size}]
    project['finalVideoPaths']=[str(finished)]
    attachments=BASE/'验收附件';attachments.mkdir()
    images=[]
    for index in range(6):
        image=Image.new('RGB',(480,270),'#f5f2fa');ImageDraw.Draw(image).text((20,20),'LOCAL TEST FIXTURE '+str(index),fill='#29233b')
        path=attachments/f'验收图片_{index}.png';image.save(path);images.append(str(path))
    csv=attachments/'实际成本测试表.csv';csv.write_text('name,yuan\nfixture,100\n','utf-8')
    overrides={'producer':'本地验收制作方','trialEpisodes':1,'episodeCount':1,'totalCostYuan':100,
        'rightsConfirmed':True,'coverPath':images[0],'proofImages':[images[1]],'storyboardImages':images[2:6],
        'costImages':[images[0]],'costReportPaths':[str(csv)],'copyrightImages':[]}
    svc.settings(pid,overrides);ready=svc.inspect(pid)
    check('真实成片与全部本地资料齐全可继续',ready['ready'] and ready['fields']['episodeCount']==1)
    check('检查结果与附件元信息持久化',json.loads((s.DATA/'state.json').read_text('utf-8'))['publishWorkspace']['plans'][pid]['fingerprint']==ready['fingerprint'])
    before=s.sha256(finished);task=wait(svc.export(pid)['taskId'])
    check('资料导出在独立后台任务完成',task['status']=='completed' and Path(task['result']['manifest']).is_file())
    manifest=json.loads(Path(task['result']['manifest']).read_text('utf-8'))
    copied=next(x for x in manifest['files'] if x.get('kind')=='videos' or x.get('category')=='videos' or Path(x['name']).suffix=='.mp4')
    exported=Path(task['result']['directory'])/copied['name']
    check('导出视频真正可解码并保留音轨',s.probe(exported)['audio'] and s.probe(exported)['duration']>=1.2)
    check('复制与源文件哈希相同且不写成功标记',s.sha256(exported)==before==s.sha256(finished) and not (final/'已经发布成功.txt').exists())
    check('导出任务反馈真实字节数',task.get('completedBytes')==task.get('totalBytes') and task.get('percent')==100)
    svc.browser('test_account','open',pid);time.sleep(.05)
    manager=svc._browser;manager.release.clear()
    browser_task=svc.browser('test_account','check',pid)
    check('同一账号后台操作防止重复并发',rejects(lambda:svc.browser('test_account','open',pid)))
    manager.release.set();checked=wait(browser_task['taskId'])
    check('浏览器结果如实保留未登录而非成功发布',checked['result']['loginState']=='login_required' and not checked['result']['submitted'])
    check('不能访问未登记附件或系统配置',rejects(lambda:svc.file(pid,str(s.DATA/'state.json'))))
    check('附件预览只允许本剧实际清单',svc.file(pid,images[0])==Path(images[0]))
    check('结果记录必须填写核对说明',rejects(lambda:svc.record({'projectId':pid,'accountId':'test_account','status':'approved','note':''})))
    record=svc.record({'projectId':pid,'accountId':'test_account','status':'submitted','note':'隔离验收本人记录，不是实际官方提交',
                       'evidenceUrl':'https://channels.weixin.qq.com/mcn/manage?ticket=fixture'})
    check('本人结果记录与平台验证分开',record['source']=='manual' and record['platformVerified'] is False and '?' not in record['evidenceUrl'])
    check('同账号已记录版本拦截重复上传',rejects(lambda:svc.browser('test_account','assist',pid)))
    check('人工记录保存审核来源',s.get_project(pid)['review']=='已提交' and s.get_project(pid)['reviewSource']=='manual')
    # Use a second project for the visible UI to show the ready-to-assist state.
    s.STATE['publishWorkspace']['records']=[];project['review']='待提交';s.save()
    # HTTP tests use the real local session and handlers, not a stub API.
    host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
    url='http://127.0.0.1:'+str(host.server_address[1])
    thread=threading.Thread(target=host.serve_forever,daemon=True);thread.start()
    cookies=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    def request(path,body=None,headers=None):
        req=urllib.request.Request(url+path,data=None if body is None else json.dumps(body).encode(),
            headers=({'Content-Type':'application/json','X-Local-Client':'1'} if body is not None else {})|(headers or {}))
        with client.open(req,timeout=20) as response:return response.status,response.read()
    try:request('/api/publish/workspace')
    except urllib.error.HTTPError as error:check('无本机会话无法访问发布资料',error.code==403)
    else:raise AssertionError('Session gate missing')
    with client.open(url+'/launch/'+host.session.launch) as response:response.read()
    check('合法会话读取发布工作区',json.loads(request('/api/publish/workspace')[1])['plans'][pid]['ready'])
    check('HTTP检查接口接真实资料模块',json.loads(request('/api/publish/inspect',{'projectId':pid})[1])['ready'])
    try:request('/api/publish/settings',{'projectId':pid,'overrides':{}},{'X-Local-Client':''})
    except urllib.error.HTTPError as error:check('发布写接口保留本机请求头检查',error.code==403)
    else:raise AssertionError('Write gate missing')
    check('HTTP附件读取返回实际PNG',request('/api/publish/file?'+__import__('urllib.parse',fromlist=['urlencode']).urlencode({'projectId':pid,'path':images[0]}))[1].startswith(b'\x89PNG'))
    check('外部总目录仅发现剧目根目录',len(svc.discover(str(Path(task['result']['directory']).parent))['candidates'])==1)
    imported=svc.import_folders([task['result']['directory']]);other=s.get_project(imported['projectIds'][0])
    check('外部成品导入不确认版权且不拆成材料子项目',len(imported['projectIds'])==1 and not other['rights'] and other['publishFolder']==task['result']['directory'])
    check('外部成品导入保留可解码的实际正片',s.probe(other['videos'][0]['path'])['audio'])
    check('重新启动不沿用陈旧已登录状态',w.Workspace(s.STATE,s.DATA,s.LOCK,s.save,svc.snapshot,s.probe).public()['browser']['test_account']['loginState']=='unknown')
    legacy=copy.deepcopy(project);legacy['id']='legacy_output_check';legacy.pop('finalVideoPaths',None)
    legacy['artifacts']=[{'path':str(finished),'kind':'视频','job':'old','name':'old.mp4'},
        {'path':str(BASE/'丢失的最新成片.mp4'),'kind':'视频','job':'latest','name':'latest.mp4'}]
    s.STATE['projects'].append(legacy)
    missing_latest=svc.inspect(legacy['id'])
    check('旧项目最新成片丢失不会回退旧任务',not missing_latest['files']['videos'] and not missing_latest['ready'])
    project['finalVideoPaths']=[str(BASE/'显式清单丢失.mp4')]
    missing_explicit=svc.inspect(pid)
    check('显式成片丢失列入资料错误而非整页异常',not missing_explicit['ready'] and any('不存在' in x for x in missing_explicit['errors']))
    project['finalVideoPaths']=[str(finished)];svc.inspect(pid)
    s.STATE['projects']=[p for p in s.STATE['projects'] if p['id']!=legacy['id']]
    isolated=copy.deepcopy(s.STATE)
    def local_snapshot(id):return copy.deepcopy(project),copy.deepcopy(s.STATE['config'])
    closing=w.Workspace(isolated,BASE/'closing',threading.RLock(),lambda:None,local_snapshot,s.probe,browser_factory=BrowserDouble)
    closing.shutdown()
    check('关闭后不能排队或创建新的浏览器',rejects(lambda:closing.browser('test_account','open',pid)) and closing._browser is None)
    report.update(ok=True,projectId=pid,exportDirectory=task['result']['directory'])
finally:
    if host:host.shutdown();host.server_close()
    s.shutdown_jobs()
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/publish-workflow-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'base':str(BASE)},ensure_ascii=False),flush=True)
