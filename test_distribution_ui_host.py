from pathlib import Path
import os,sys,json
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp/distribution-ui';BASE.mkdir(exist_ok=True)
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT/'release/v0.5.0/漫剧工坊/_internal'),str(ROOT/'vendor')]
sys.frozen=True
import server,local_session
server.PUBLIC=ROOT/'release/v0.5.0/漫剧工坊/_internal/web'
s=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);s.session=local_session.Session()
(BASE/'host.json').write_text(json.dumps({'url':'http://127.0.0.1:'+str(s.server_address[1])+'/launch/'+s.session.launch}),'utf-8')
try:s.serve_forever()
finally:server.shutdown_jobs();s.server_close()
