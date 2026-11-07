"""Run the real launcher with isolated application data for local acceptance."""
from pathlib import Path
import json
import os
import sys

ROOT=Path(__file__).resolve().parents[1]
os.environ['MANJU_DATA']=str(ROOT/'tmp/xiaovmiao-check/data')
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server,local_session

host=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
host.session=local_session.Session()
(ROOT/'tmp/xiaovmiao-check-host.json').write_text(json.dumps({
    'url':f'http://127.0.0.1:{host.server_address[1]}/launch/{host.session.launch}'
}), 'utf-8')
print('XIAOVMIAO_CHECK_READY', flush=True)
try:host.serve_forever()
finally:host.server_close()
