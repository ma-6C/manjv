"""Local acceptance host for the real integrated source workspace."""
from pathlib import Path
import os,sys,json,time,argparse
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--compiled',action='store_true');args=p.parse_args()
BASE=ROOT/'tmp'/('source-production-ui-'+time.strftime('%Y%m%d-%H%M%S'));BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['PYTHONDONTWRITEBYTECODE']='1';sys.dont_write_bytecode=True
if args.compiled:
    sys.path[:0]=[str(ROOT/'release/v0.8.0/漫剧工坊/_internal'),str(ROOT/'vendor')];sys.frozen=True
import server as s,local_session
if args.compiled:
    assert s.__file__.endswith('.pyd')
    import re
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    s.licensing.activate(s.DATA,token)
    s.PUBLIC=ROOT/'release/v0.8.0/漫剧工坊/_internal/web'
s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,parallel=1,regroup=False,autoRecords=False,autoText=False,subtitleAuto=False)
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/source-production-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'compiled':args.compiled}),'utf-8')
print(url,flush=True)
try:host.serve_forever()
finally:
    if s.SOURCE_MANAGER:s.SOURCE_MANAGER.shutdown()
    s.shutdown_jobs();host.server_close()
