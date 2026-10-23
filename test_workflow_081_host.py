"""Compiled UI host replaying recorded real public responses and real media; no network."""
from pathlib import Path
import sys,os,json,time,tempfile,re,io,shutil
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='workflow-ui-081-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True;os.environ['PYTHONDONTWRITEBYTECODE']='1'
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT/'release/v0.8.1/漫剧工坊/_internal'),str(ROOT/'vendor')];sys.frozen=True
import server as s,hongguo_source as h,local_session
assert s.__file__.endswith('.pyd');s.licensing.verify_distribution(ROOT/'release/v0.8.1/漫剧工坊')
token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0);s.licensing.activate(s.DATA,token)
record=json.loads((ROOT/'tmp/source-workspace-acceptance.json').read_text('utf-8'));sources={v['sourceEpisodeId']:Path(v['path']) for v in record['media']}
cover=ROOT/'实际视频测试/红果网页采集-20261020/封面.jpg'
def fetch(url,cancel=None):
    if '/category/' in url:return (ROOT/'tmp/hongguo-category.html').read_text('utf-8')
    if '/detail?' in url:return (ROOT/'tmp/hongguo-detail-current.html').read_text('utf-8')
    n={'7697855365819419673':2,'7697855263528733721':3}.get(url.rsplit('/',1)[-1],1)
    return (ROOT/'tmp'/('hongguo-player.html' if n==1 else f'hongguo-player-{n}.html')).read_text('utf-8')
def download(url,path,cancel,progress,image=False):
    if cancel.is_set():raise h.Cancelled()
    shutil.copy2(cover if image else sources[url.split('/')[-2]],path);progress(path.stat().st_size,path.stat().st_size)
h.fetch_html=fetch;h.download=download;h.response=lambda *a,**k:io.BytesIO(cover.read_bytes())
s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,parallel=1,regroup=False,autoRecords=False,autoCover=False,autoText=False,subtitleAuto=False,subtitleMode='local')
s.PUBLIC=ROOT/'release/v0.8.1/漫剧工坊/_internal/web'
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/workflow-081-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE),'compiled':True,'replay':True}),'utf-8')
print(url,flush=True)
try:host.serve_forever()
finally:
    if s.SOURCE_MANAGER:s.SOURCE_MANAGER.shutdown()
    s.shutdown_jobs();host.server_close()
