"""Isolated local server for search-input regression; never use customer state."""
from pathlib import Path
import argparse,json,os,re,sys,tempfile,threading
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--compiled',action='store_true');p.add_argument('--version',default='v0.8.3');p.add_argument('--timeout',type=int,default=180);args=p.parse_args()
BASE=Path(tempfile.mkdtemp(prefix='source-search-ui-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True
DIST=ROOT/'release'/args.version/'漫剧工坊'
sys.path[:0]=([str(DIST/'_internal')] if args.compiled else [])+[str(ROOT/'vendor')]
import server,local_session
if args.compiled:
    assert server.__file__.endswith('.pyd');sys.frozen=True
    server.licensing.verify_distribution(DIST)
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    assert server.licensing.activate(server.DATA,token)['valid'];server.PUBLIC=DIST/'_internal/web'
host=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/source-search-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'pid':os.getpid(),'sourceOnly':not args.compiled,'compiled':args.compiled,'version':args.version,'signedDistributionVerified':args.compiled}),'utf-8')
print(url,flush=True)
threading.Timer(args.timeout,host.shutdown).start()
try:host.serve_forever()
finally:server.shutdown_jobs();host.server_close()
