"""Serve an isolated real-media flow fixture; never use production user data."""
from pathlib import Path
import json,os,sys,threading
ROOT=Path(__file__).resolve().parent
seed=json.loads((ROOT/'tmp/studio-flow-preview-seed.json').read_text('utf-8'))
BASE=Path(seed['base']).resolve()
assert BASE.is_relative_to(ROOT/'tmp') and BASE.name.startswith('studio-flow-real-')
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,local_session
s.STATE['studioFlows']={'flows':[],'activeFlowId':''};s.save()
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/studio-flow-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,
    'base':str(BASE),'projectId':seed['projectId'],'pid':os.getpid(),'sourceOnly':True,'realFlow':True},ensure_ascii=False),'utf-8')
print('STUDIO_FLOW_SOURCE_READY',flush=True)
threading.Timer(3600,host.shutdown).start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
