"""HTTP checks of the new source routes, with isolated data and simulated license states."""
from pathlib import Path
import http.cookiejar,json,os,re,sys,threading,time,urllib.request,urllib.error
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
COMPILED='--compiled' in sys.argv;VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.4'
sys.dont_write_bytecode=True;DIST=ROOT/'release'/VERSION/'漫剧工坊'
BASE=ROOT/'tmp'/('source-security-'+time.strftime('%Y%m%d-%H%M%S'));BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data')
sys.path[:0]=([str(DIST/'_internal')] if COMPILED else [])+[str(ROOT/'vendor')]
import server as s,local_session
if COMPILED:
    assert s.__file__.endswith('.pyd');sys.frozen=True;s.licensing.verify_distribution(DIST)
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    assert s.licensing.activate(s.DATA,token)['valid'];s.PUBLIC=DIST/'_internal/web'
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
thread=threading.Thread(target=host.serve_forever,daemon=True);thread.start()
base='http://127.0.0.1:'+str(host.server_address[1]);checks=[]
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def request(path,body=None,headers=None,opener=client):
    req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json','X-Local-Client':'1',**(headers or {})})
    for attempt in range(3):
        try:
            with opener.open(req,timeout=4) as r:return r.status,r.read()
        except urllib.error.HTTPError as e:return e.code,e.read()
        except (ConnectionAbortedError,ConnectionResetError):
            if attempt==2:raise
            time.sleep(.05)
try:
    assert request('/api/source/report?id=missing',opener=urllib.request.build_opener())[0]==403;checks.append('source_diagnostic_requires_session')
    assert request('/api/source/tasks',opener=urllib.request.build_opener())[0]==403;checks.append('source_history_requires_session')
    assert request('/api/source/cover?id=123456',opener=urllib.request.build_opener())[0]==403;checks.append('cover_requires_session')
    client.open(base+'/launch/'+host.session.launch).close()
    with patch.object(s.licensing,'status',return_value={'valid':False,'message':'test unlicensed'}):
        assert request('/api/source/report?id=missing')[0]==403;checks.append('source_diagnostic_requires_license')
        assert request('/api/source/tasks')[0]==403
        assert request('/api/source/cover?id=123456')[0]==403
        assert request('/api/source/start',{'url':'https://hongguoduanju.com/detail?series_id=123456','directory':str(BASE)})[0]==403
        assert request('/api/source/resolve',{'text':'https://hongguoduanju.com/category/comic-drama'})[0]==403
        checks.append('source_routes_all_require_valid_license')
        for path in ['/api/source/control','/api/source/access-resume','/api/jobs/preflight','/api/promotion/inputs']:
            assert request(path,{'action':'resume'})[0]==403
        checks.append('source_control_and_access_resume_require_license')
    for path in ['/api/source/control','/api/source/access-resume','/api/jobs/preflight','/api/promotion/inputs']:
        assert request(path,{'action':'resume'},opener=urllib.request.build_opener())[0]==403
    checks.append('source_control_and_access_resume_require_session')
    assert request('/api/source/tasks',headers={'Origin':'https://other.example'})[0]==403;checks.append('cross_origin_read_rejected')
    assert request('/api/source/start',{},headers={'X-Local-Client':''})[0]==403;checks.append('missing_client_header_rejected')
    assert request('/api/source/resolve',{'text':'https://127.0.0.1/private'})[0]==400;checks.append('unapproved_url_rejected_over_http')
    assert request('/api/source/cover?id=99999999')[0]==400;checks.append('cover_only_from_previously_resolved_source')
    assert request('/api/source/start',{'url':'https://hongguoduanju.com/detail?series_id=123456','directory':'relative/path','video':True})[0]==400;checks.append('relative_save_directory_rejected')
    assert request('/api/source/tasks')[0]==200;checks.append('authenticated_source_state_available')
    (ROOT/'tmp/source-security-082-report.json').write_text(json.dumps({'version':VERSION,'compiled':COMPILED,'passed':len(checks),'checks':checks},indent=2),'utf-8')
    print(json.dumps({'passed':len(checks)}),flush=True)
finally:host.shutdown();host.server_close();thread.join(3)
