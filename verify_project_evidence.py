"""Controlled provenance checks plus real-media editable draft preparation.

Native window acceptance is deliberately separate from these backend fixtures.
"""
from pathlib import Path
import copy,json,os,sys,tempfile,threading,time
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='official-project-core-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,project_evidence as pe,publish_materials as pm
from PIL import Image
report={'base':str(BASE),'checks':[],'ok':False,'scope':'Backend controlled provenance and real media; not native editor screenshot proof'}
def check(name,value=True):assert value,name;report['checks'].append(name);print('PASS '+name,flush=True)
def rejects(fn):
    try:fn()
    except (ValueError,PermissionError):return True
    return False
class ControlledCapture:
    def windows(self,platform):return [{'id':'fixture-window','title':'CONTROLLED TEST ONLY','pid':123,'processPath':'fixture','platform':platform}]
    def foreground(self,window):return True
    def capture(self,window,platform,path):
        Image.new('RGB',(480,320),'#e8dcf9').save(path)
        return {'id':window,'pid':123,'processPath':'fixture','appVerified':True,'unmodified':True,'fixture':True}
try:
    class Control:
        def __init__(self,kind='PaneControl',cls='',value='',focused=False,children=()):
            self.ControlTypeName,self.ClassName,self.value,self.HasKeyboardFocus,self.children=kind,cls,value,focused,list(children)
        def GetChildren(self):return self.children
        def GetValuePattern(self):return SimpleNamespace(Value=self.value)
    address=Control('EditControl','Chrome_OmniboxView','https://jimeng.jianying.com/project/example',False)
    document=Control('DocumentControl',value='https://example.org/')
    root_control=Control(children=[address,document])
    auto=SimpleNamespace(UIAutomationInitializerInThread=nullcontext,ControlFromHandle=lambda h:root_control)
    with patch.dict(sys.modules,{'uiautomation':auto}):
        reader=pe.WindowsCapture()
        check('只输入未导航的即梦网址不能当实际来源',reader._browser_url(1)=='')
        document.value=address.value;address.HasKeyboardFocus=True
        check('地址栏正在编辑时拒绝采集',reader._browser_url(1)=='')
        address.HasKeyboardFocus=False
        check('受控浏览器原生地址与文档URL一致才通过',reader._browser_url(1)==address.value)
        address.value=document.value='https://jimeng.jianying.com:8443/project/example'
        check('即梦来源拒绝非官方端口',reader._browser_url(1)=='')
        address.value=document.value='https://name:pass@jimeng.jianying.com/project/example'
        check('即梦来源拒绝嵌入登录凭据的地址',reader._browser_url(1)=='')
    folder=BASE/'素材';folder.mkdir();video=folder/'官方工程接入样片.mp4'
    original=Path('D:/weixin_wenjian/xwechat_files/wxid_qet5grsgoecp22_d214/msg/video/2026-10/7ecdbee6fa3a89ad314f90ed019be92c.mp4')
    if original.is_file():s.ff(['-i',str(original),'-t','6','-vf','scale=960:-2','-c:v','libx264','-preset','fast','-c:a','aac',str(video)])
    else:s.ff(['-f','lavfi','-i','testsrc2=size=640x360:rate=12:duration=6','-c:v','libx264','-preset','fast',str(video)])
    pid=s.scan(str(folder))['projects'][0]['id'];project=s.get_project(pid);project['intro']='官方工程接入实际样片测试';project['rights']=True
    s.STATE['config']['output']=str(BASE/'output')
    before=len(s.JOBS)
    check('自绘工程图任务入口拒绝且不排队',rejects(lambda:s.create_job({'kind':'track_sheet','ids':[pid]})) and len(s.JOBS)==before)
    with patch.object(s,'ensure_runner',lambda:None):job=s.create_job({'kind':'jianying_project','ids':[pid],
        'sourceVideoPaths':{pid:[str(video)]},'trackOrder':[str(video)],'jianying':{'splitScenes':False,'executable':'D:/剪映/JianyingPro/JianyingPro.exe','draftRoot':'D:/剪映/JianyingPro Drafts'}})
    s.worker(job['id'],[pid],'jianying_project',s.JOBS[job['id']]['config']);j=s.JOBS[job['id']]
    check('真实视频与原声生成可编辑工程',j['status']=='completed' and j['jianyingResults'][0]['tracks']>=1)
    row=j['jianyingResults'][0]
    check('草稿完成不冒称官方编辑器已验证',row['editorValidated'] is False)
    s.records(project,s.STATE['config'],j['id'])
    check('制作记录只存实际JSON不再绘制拼接工程页',any(a['kind']=='制作记录' and a['path'].endswith('.json') for a in project['artifacts']) and not any(a['kind']=='工程记录' for a in project['artifacts']))
    check('原有真实分镜帧继续保留并标明用途',len([a for a in project['artifacts'] if a['kind']=='分镜截图' and Path(a['path']).is_file()])==4)
    old=BASE/'旧图.png';Image.new('RGB',(30,30)).save(old);project['artifacts'].append({'kind':'工程记录','path':str(old)})
    check('旧自绘或拼接图不进入真实官方证明',not pm.inspect(project,{},probe=s.probe)['files']['proofImages'])
    registered=[]
    def record(p,path,kind,evidence):
        entry={'path':str(path),'kind':kind,'officialEvidence':copy.deepcopy(evidence)};registered.append(entry)
    m=pe.Manager({},BASE/'evidence-fixture',threading.RLock(),lambda:None,record,backend=ControlledCapture())
    check('枚举窗口不生成图片',m.capture(pid,{'platform':'jianying'},{}).get('windows') and not registered)
    check('必须本人确认窗口工程内容',rejects(lambda:m.capture(pid,{'platform':'jianying','windowId':'fixture-window'},{})))
    started=m.capture(pid,{'platform':'jianying','windowId':'fixture-window','userConfirmed':True},{'projectId':pid})
    for _ in range(100):
        tasks=m.list(pid)['tasks']
        if tasks[-1]['status'] in ('completed','failed'):break
        time.sleep(.03)
    check('受控采集写未修改图片与来源元信息',tasks[-1]['status']=='completed' and registered[-1]['officialEvidence']['sha256']==pe.sha(registered[-1]['path']))
    valid=pm.inspect({'id':pid,'name':'测试','artifacts':registered},{},probe=s.probe)
    check('受控完整来源登记可被检查器核验',len(valid['files']['proofImages'])==1)
    Image.new('RGB',(31,31)).save(registered[-1]['path'])
    check('采集后图片修改不能沿用来源通过',not pm.inspect({'id':pid,'name':'测试','artifacts':registered},{})['files']['proofImages'])
    manual=m.import_images(pid,{'platform':'jianying','paths':[str(old)],'note':'controlled import fixture','userConfirmed':True},{'projectId':pid})
    check('手动导入保持来源未核验',manual['items'][0]['officialEvidence']['appVerified'] is False and registered[-1]['kind']=='待核对工程截图')
    check('手动导入不能提升为官方证明',not pm.inspect({'id':pid,'name':'测试','artifacts':[registered[-1]]},{})['files']['proofImages'])
    m.shutdown()
    check('关闭后停止新采集',rejects(lambda:m.capture(pid,{'platform':'jianying','windowId':'fixture-window','userConfirmed':True},{})))
    s.save();report.update(ok=True,projectId=pid,jobId=j['id'],directory=row['directory'],source=str(video))
finally:
    s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/official-project-core-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(report['checks']),'base':str(BASE),'ok':report['ok']},ensure_ascii=False))
