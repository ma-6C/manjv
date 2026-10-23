"""Isolated HTTP/UI acceptance host; all fixtures and state stay under tmp/."""
from pathlib import Path
import argparse,json,os,re,shutil,sys,tempfile

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--paced',action='store_true');p.add_argument('--compiled',action='store_true');p.add_argument('--version',default='v0.8.3');args=p.parse_args()
BASE=Path(tempfile.mkdtemp(prefix='tracks-ui-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
DIST=ROOT/'release'/args.version/'漫剧工坊'
sys.path[:0]=([str(DIST/'_internal')] if args.compiled else [])+[str(ROOT/'vendor')];sys.dont_write_bytecode=True
import server as s,local_session
if args.compiled:
    assert s.__file__.endswith('.pyd');sys.frozen=True;s.licensing.verify_distribution(DIST)
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    assert s.licensing.activate(s.DATA,token)['valid'];s.PUBLIC=DIST/'_internal/web'

source=BASE/'验收样片';source.mkdir()
files=[]
for i,length in [(1,3),(2,18),(3,2)]:
    target=source/f'第{i}集.mp4'
    s.ff(['-f','lavfi','-i',f'testsrc2=s={"270x480" if i==3 else "480x270"}:r=25:d={length}',
          '-f','lavfi','-i',f'sine=frequency={300+i*100}:duration={length}',
          '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',target])
    files.append(str(target))
bulk=BASE/'30集样片';bulk.mkdir()
bulk_files=[]
for i in range(30):
    path=bulk/f'第{i+1:02d}集.mp4';shutil.copy2(files[0],path);bulk_files.append(str(path))
real=Path('D:/weixin_wenjian/xwechat_files/wxid_qet5grsgoecp22_d214/msg/video/2026-10/7ecdbee6fa3a89ad314f90ed019be92c.mp4')
# A controlled real-time input makes active FFmpeg cancellation observable.
# This injection is confined to this test host and never enters the product.
original_run=s.run_process
def paced_run(command,*a,**kw):
    if args.paced and any('frame_%04d.jpg' in str(x) for x in command) and str(files[1]) in list(map(str,command)):
        command=list(command);command.insert(command.index('-i'),'-re')
    return original_run(command,*a,**kw)
s.run_process=paced_run
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
meta={'url':url,'launch':url+'/launch/'+host.session.launch,'sourceOnly':not args.compiled,'compiled':args.compiled,'version':args.version,'signedDistributionVerified':args.compiled,'pid':os.getpid(),'base':str(BASE),
      'files':files,'bulkFiles':bulk_files,'realFile':str(real) if real.is_file() else None,'paced':args.paced}
(ROOT/'tmp/tracks-ui-host.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'url':url,'base':str(BASE),'paced':args.paced}),flush=True)
try:host.serve_forever()
finally:s.shutdown_jobs();host.server_close()
