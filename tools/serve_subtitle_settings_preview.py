"""Isolated real subtitle output and source UI for page-scoped settings review."""
from pathlib import Path
from unittest.mock import patch
import json,os,sys,tempfile,threading
ROOT=Path(__file__).resolve().parents[1]
BASE=Path(tempfile.mkdtemp(prefix='subtitle-settings-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,local_session
folder=BASE/'source';folder.mkdir()
s.ff(['-f','lavfi','-i','testsrc2=size=640x360:rate=30:duration=3','-f','lavfi','-i','sine=frequency=440:duration=3',
      '-c:v','libx264','-preset','fast','-c:a','aac','-shortest',str(folder/'第001集.mp4')])
p=s.scan(str(folder))['projects'][0];p['name']='设置交互验证样片'
s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='local',gpu=False,regroup=False)
with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':'subtitle','ids':[p['id']]})['id']
s.worker(jid,[p['id']],'subtitle',s.JOBS[jid]['config']);assert s.JOBS[jid]['status']=='completed'
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/subtitle-settings-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),
    'pid':os.getpid(),'projectId':p['id'],'jobId':jid,'sourceOnly':True},ensure_ascii=False,indent=2),'utf-8')
print('SUBTITLE_SETTINGS_PREVIEW_READY',flush=True)
timer=threading.Timer(3600,host.shutdown);timer.daemon=True;timer.start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close();timer.cancel()
