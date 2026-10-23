"""Serve the isolated real-media handoff acceptance state with source modules."""
from pathlib import Path
import argparse,json,os,sys,threading
ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--compiled',action='store_true');parser.add_argument('--version',default='v0.8.6');args=parser.parse_args()
name='production-handoff-core-compiled-'+args.version+'.json' if args.compiled else 'production-handoff-core.json'
seed=json.loads((ROOT/'tmp'/name).read_text('utf-8'));BASE=Path(seed['base']);DIST=ROOT/'release'/args.version/'漫剧工坊'
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next(((DIST/'_internal' if args.compiled else ROOT/'vendor')/'imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=([str(DIST/'_internal')] if args.compiled else [str(ROOT)])+[str(ROOT/'vendor')]
if args.compiled:sys.frozen=True
import server as s,local_session
if args.compiled:
    assert s.__file__.endswith('.pyd');s.licensing.verify_distribution(DIST);s.PUBLIC=DIST/'_internal/web'
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();url='http://127.0.0.1:'+str(host.server_address[1])
meta={'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'projectId':seed['projectId'],'parentId':seed['uiParentId'],'pid':os.getpid(),'sourceOnly':not args.compiled,'compiled':args.compiled,'version':args.version,'realMedia':True}
(ROOT/'tmp/production-handoff-ui-host.json').write_text(json.dumps(meta,ensure_ascii=False),'utf-8');print('HANDOFF_UI_READY',flush=True)
threading.Timer(180,host.shutdown).start()
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
