"""Environment reports keep the existing session/license/origin boundary."""
from pathlib import Path
from unittest.mock import patch
import os,sys,tempfile,json,threading,urllib.request,urllib.error,http.cookiejar
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='gpu-http-',dir=ROOT/'tmp'))
COMPILED='--compiled' in sys.argv
os.environ['MANJU_DATA']=str(BASE/'data');sys.path[:0]=([str(ROOT/'release/v0.8.2/漫剧工坊/_internal')] if COMPILED else [])+[str(ROOT/'vendor')];sys.dont_write_bytecode=True
if COMPILED:sys.frozen=True
import server as s,local_session
if COMPILED:
    import re
    assert s.__file__.endswith('.pyd')
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0);s.licensing.activate(s.DATA,token)
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();thread=threading.Thread(target=host.serve_forever,daemon=True);thread.start()
url='http://127.0.0.1:'+str(host.server_address[1]);client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));checks=[]
def get(path,opener=client,headers=None):
    try:
        with opener.open(urllib.request.Request(url+path,headers=headers or {}),timeout=10) as r:return r.status,r.read()
    except urllib.error.HTTPError as e:return e.code,e.read()
try:
    assert get('/api/environment/report',urllib.request.build_opener())[0]==403;checks.append('report_requires_session')
    client.open(url+'/launch/'+host.session.launch).close()
    with patch.object(s.licensing,'status',return_value={'valid':False,'message':'test unlicensed'}):
        assert get('/api/environment/report')[0]==403;checks.append('report_requires_valid_license')
    assert get('/api/environment/report',headers={'Origin':'https://other.example'})[0]==403;checks.append('cross_origin_report_rejected')
    probe={'available':False,'code':'driver_version','detail':'NVIDIA 驱动与编码接口不兼容','name':'NVIDIA NVENC'}
    with patch.object(s.gpu_encoding,'probe',return_value=probe.copy()) as mocked,patch.object(s.gpu_encoding,'adapters',return_value=[]):
        code,raw=get('/api/environment?refresh=1');assert code==200 and mocked.call_args.kwargs['force'] is True;checks.append('refresh_flag_reaches_actual_probe')
        code,raw=get('/api/environment/report');r=json.loads(raw);assert code==200 and r['gpu']['code']=='driver_version';checks.append('classified_diagnostic_available_to_authorized_client')
        assert not any(k in r for k in ['data','config','secrets','license']) and str(BASE) not in raw.decode('utf-8');checks.append('diagnostic_excludes_private_paths_and_configuration')
    report={'sourceOnly':not COMPILED,'compiled':COMPILED,'passed':len(checks),'checks':checks};(ROOT/('tmp/gpu-http-compiled-report.json' if COMPILED else 'tmp/gpu-http-source-report.json')).write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(report))
finally:host.shutdown();host.server_close();thread.join(3)
