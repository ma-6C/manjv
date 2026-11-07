"""Serve only the isolated acceptance data, with an explicitly simulated LLM."""
from pathlib import Path
import json,os,sys,threading
ROOT=Path(__file__).resolve().parent
seed=json.loads((ROOT/'tmp/promotion-studio-acceptance.json').read_text('utf-8'))
os.environ['MANJU_DATA']=str(Path(seed['base'])/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,local_session
def model(cfg,system,user,max_tokens=1024):
    return {'text':json.dumps({'clips':[{'title':'界面模拟高光','reason':'模拟模型，仅验证界面流程','description':'不发布到真实平台',
        'segments':[{'source':0,'start':0,'end':3,'reason':'铺垫'},{'source':1,'start':2,'end':5,'reason':'悬念'}]}]},ensure_ascii=False),'model':'LOCAL-UI-MOCK'}
s.promotion_studio.ai_providers.text_generate=model
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
(ROOT/'tmp/promotion-studio-ui-host.json').write_text(json.dumps({'url':'http://127.0.0.1:'+str(host.server_address[1])+'/launch/'+host.session.launch,'base':seed['base']}),'utf-8')
print('PROMOTION_STUDIO_UI_READY',flush=True)
timer=threading.Timer(600,host.shutdown);timer.daemon=True;timer.start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close();timer.cancel()
