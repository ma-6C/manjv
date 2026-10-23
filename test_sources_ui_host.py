"""Isolated authenticated local UI host; uses the actual network adapter."""
from pathlib import Path
import os,json,time
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'tmp'/('sources-ui-'+time.strftime('%Y%m%d-%H%M%S'));BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data')
import server,local_session
host=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);host.session=local_session.Session()
url='http://127.0.0.1:'+str(host.server_address[1])
(ROOT/'tmp/sources-ui-host.json').write_text(json.dumps({'url':url,'launch':url+'/launch/'+host.session.launch,'base':str(BASE)}),'utf-8')
print(url,flush=True)
try:host.serve_forever()
finally:server.shutdown_jobs();host.server_close()
