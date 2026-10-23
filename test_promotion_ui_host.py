from pathlib import Path
import os,json
ROOT=Path(__file__).resolve().parent
report=json.loads((ROOT/'tmp/latest-promotion-acceptance.json').read_text('utf-8'))
os.environ['MANJU_DATA']=str(Path(report['base'])/'data')
import server,local_session
s=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);s.session=local_session.Session()
(ROOT/'tmp/promotion-ui-host.json').write_text(json.dumps({'url':'http://127.0.0.1:'+str(s.server_address[1])+'/launch/'+s.session.launch}),'utf-8')
try:s.serve_forever()
finally:server.shutdown_jobs();s.server_close()
