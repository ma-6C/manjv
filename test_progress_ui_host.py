"""UI acceptance host: real media, input pacing added only here to observe progress. Never shipped."""
from pathlib import Path
import os,time,json,shutil
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp/progress-ui'/time.strftime('%Y%m%d-%H%M%S');BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data')
import server as s,local_session
source=BASE/'source'/'进度验收样片';source.mkdir(parents=True)
s.ff(['-f','lavfi','-i','testsrc2=s=640x360:r=30:d=8','-f','lavfi','-i','sine=frequency=440:duration=8','-c:v','libx264','-preset','ultrafast','-c:a','aac','-pix_fmt','yuv420p',str(source/'01.mp4')]);shutil.copy2(source/'01.mp4',source/'02.mp4')
s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':640,'height':360,'parallel':2,'regroup':False,'autoRecords':False,'subtitleAuto':False,'subtitleMode':'local'})
project=s.scan(str(source))['projects'][0]
actual_ff=s.ff
def paced(args,job=None):return actual_ff((['-re']+list(args)) if job and '-i' in args else args,job)
s.ff=paced
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();url='http://127.0.0.1:'+str(host.server_address[1]);meta={'url':url,'launch':url+'/launch/'+host.session.launch,'projectId':project['id'],'base':str(BASE),'realMedia':True,'testInputPacing':True}
(ROOT/'tmp/progress-ui-host.json').write_text(json.dumps(meta,ensure_ascii=False),'utf-8');print(url,flush=True)
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
