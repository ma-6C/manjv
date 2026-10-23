"""Isolated source UI over actual GPU/fallback test results, never user state."""
from pathlib import Path
import os,sys,tempfile,json,shutil
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='gpu-ui-',dir=ROOT/'tmp'))
COMPILED='--compiled' in sys.argv
evidence=json.loads((ROOT/('tmp/gpu-fallback-compiled-report.json' if COMPILED else 'tmp/gpu-fallback-source-report.json')).read_text('utf-8'))
data=BASE/'data';data.mkdir()
for name in ['state.json','jobs.json']:shutil.copy2(Path(evidence['base'])/'data'/name,data/name)
os.environ['MANJU_DATA']=str(data);os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=([str(ROOT/'release/v0.8.2/漫剧工坊/_internal')] if COMPILED else [])+[str(ROOT/'vendor')];sys.dont_write_bytecode=True
if COMPILED:sys.frozen=True
import server as s,local_session
if COMPILED:
    import re
    assert s.__file__.endswith('.pyd')
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0);s.licensing.activate(s.DATA,token)
    s.PUBLIC=ROOT/'release/v0.8.2/漫剧工坊/_internal/web'
s.STATE['config']['gpu']=True
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
fallback=next(j['id'] for j in reversed(list(s.JOBS.values())) if j.get('gpuFallback'))
(ROOT/'tmp/gpu-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'sourceOnly':not COMPILED,'compiled':COMPILED,'base':str(BASE),'fallbackJobId':fallback}),'utf-8')
print(url,flush=True)
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
