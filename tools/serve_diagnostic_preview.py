"""Preview real failed and successful tasks in a separate local data directory."""
from pathlib import Path
from unittest.mock import patch
import json,os,sys,tempfile,threading
ROOT=Path(__file__).resolve().parents[1]
BASE=Path(tempfile.mkdtemp(prefix='diagnostic-ui-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,local_session
source=BASE/'source';source.mkdir()
s.ff(['-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2',
      '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(source/'第002集.mp4')])
p=s.scan(str(source))['projects'][0]
p['name']='日志验证样片'
s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':640,'height':360,'gpu':False,'regroup':False,'autoRecords':False})
with patch.object(s,'ensure_runner',lambda:None):failed=s.create_job({'kind':'transcode','ids':[p['id']]})['id']
with patch.object(s,'filters',lambda *args:'no_such_diagnostic_filter'):s.worker(failed,[p['id']],'transcode',s.JOBS[failed]['config'])
with patch.object(s,'ensure_runner',lambda:None):passed=s.create_job({'kind':'transcode','ids':[p['id']]})['id']
s.worker(passed,[p['id']],'transcode',s.JOBS[passed]['config'])
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
meta={'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'projectId':p['id'],'failedJobId':failed,'passedJobId':passed,
      'pid':os.getpid(),'sourceOnly':True,'realProcessFailure':True}
(ROOT/'tmp/diagnostic-ui-host.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
print('Diagnostic preview ready',flush=True)
timer=threading.Timer(1800,host.shutdown);timer.daemon=True;timer.start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close();timer.cancel()
