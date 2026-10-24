"""Serve isolated whole-video acceptance artifacts with the actual source UI."""
from pathlib import Path
import argparse,json,os,sys,threading
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--seed',type=Path,default=ROOT/'tmp/subtitle-full-latest.json');options=parser.parse_args()
seed=json.loads(options.seed.read_text('utf-8'))
BASE=Path(seed['base'])
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,local_session
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/subtitle-full-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'realProjectId':seed.get('projectId'),'pid':os.getpid(),'sourceOnly':True},ensure_ascii=False),'utf-8')
print('SUBTITLE_FULL_UI_READY',flush=True)
threading.Timer(1800,host.shutdown).start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
