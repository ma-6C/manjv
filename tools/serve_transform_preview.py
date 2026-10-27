"""Isolated source UI host; never loads or overwrites customer projects."""
from pathlib import Path
import json, os, sys, tempfile, threading
ROOT=Path(__file__).resolve().parents[1]
BASE=Path(tempfile.mkdtemp(prefix='transform-ui-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s, local_session
folder=BASE/'source';folder.mkdir()
for n in (1,2):
    s.ff(['-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=12',
          '-f','lavfi','-i',f'sine=frequency={n*330}:sample_rate=48000:duration=12',
          '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(folder/f'第{n:03d}集.mp4')])
p=s.scan(str(folder))['projects'][0];p['rights']=True
s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':640,'height':360,
    'gpu':False,'autoRecords':False,'regroup':False})
s.save()
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
meta={'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'projectId':p['id'],
      'pid':os.getpid(),'sourceOnly':True,'compiled':False}
(ROOT/'tmp/transform-ui-host.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(meta,ensure_ascii=False),flush=True)
timer=threading.Timer(2400,host.shutdown);timer.daemon=True;timer.start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close();timer.cancel()
