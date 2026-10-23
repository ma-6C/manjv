from pathlib import Path
import os,sys,json,time,subprocess,shutil,re
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp/installed-ai-pipeline';BASE.mkdir(exist_ok=True)
os.environ['MANJU_DATA']=str(ROOT/'tmp/engine-installed-data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT/'release/v0.5.0/漫剧工坊/_internal'),str(ROOT/'vendor')];sys.frozen=True
import server as s,licensing,engine_manager
licensing.activate(s.DATA,(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8'));engine=engine_manager.active(s.DATA);assert engine and 'vsr-env' not in engine['python']
original=Path(r'D:\weixin_wenjian\xwechat_files\wxid_qet5grsgoecp22_d214\msg\video\2026-10\7ecdbee6fa3a89ad314f90ed019be92c.mp4');before=s.sha256(original)
source=BASE/'source';source.mkdir(exist_ok=True);shutil.copy2(original,source/'01.mp4')
s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':1254,'height':720,'parallel':1,'subtitleMode':'vsr','subtitleFirst':1,'subtitleRegions':[{'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}],'vsrRoot':engine['root'],'vsrPython':engine['python'],'vsrMode':'sttn-auto'})
p=s.scan(str(source))['projects'][0];jid=s.create_job({'kind':'preview','ids':[p['id']],'options':{'videoIndex':0,'start':0,'duration':5}})['id'];t=time.time()
while time.time()-t<180:
    j=s.JOBS[jid]
    if j.get('finished'):break
    time.sleep(.5)
assert j['status']=='completed',j.get('error');assert s.sha256(original)==before
outputs=[a for a in p['artifacts'] if a['job']==jid];assert any(a['path'].endswith('.mp4') for a in outputs),outputs
report={'ok':True,'engine':engine,'jobSeconds':round(time.time()-t,2),'originalUnchanged':True,'sourceSha256':before,'artifacts':outputs,'core':s.__file__}
(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print('INSTALLED_AI_PREVIEW_OK',flush=True);s.shutdown_jobs()
