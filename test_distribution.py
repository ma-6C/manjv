"""Acceptance for compiled release core, session, activation and component import."""
from pathlib import Path
import sys,os,json,time,subprocess,threading,urllib.request,urllib.error,http.cookiejar,hashlib,zipfile,argparse,re
parser=argparse.ArgumentParser();parser.add_argument('--version',default='v0.5.0');parser.add_argument('--issuer',type=Path,default=Path(__file__).resolve().parent/'授权管理/当前签发工具-v2/授权签发工具.exe');options=parser.parse_args();version=options.version
if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号无效')
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp/distribution-test'/time.strftime('%Y%m%d-%H%M%S');BASE.mkdir(parents=True,exist_ok=True)
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT/'release'/version/'漫剧工坊/_internal'),str(ROOT/'vendor')]
import licensing,win_security,local_session
sys.frozen=True
import server as s
assert s.__file__.endswith('.pyd'),s.__file__
s.PUBLIC=ROOT/'release'/version/'漫剧工坊/_internal/web'
dist=ROOT/'release'/version/'漫剧工坊';licensing.verify_distribution(dist)
checks=['compiled_core_loaded','signed_distribution_verified']
service=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);service.session=local_session.Session();url='http://127.0.0.1:'+str(service.server_address[1])
threading.Thread(target=service.serve_forever,daemon=True).start()
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def request(path,body=None,opener=client,headers=None):
    data=None if body is None else json.dumps(body).encode();h={'Content-Type':'application/json','X-Local-Client':'1'};h.update(headers or {})
    try:
        with opener.open(urllib.request.Request(url+path,data,headers=h),timeout=30) as r:return r.status,r.read(),dict(r.headers)
    except urllib.error.HTTPError as e:return e.code,e.read(),dict(e.headers)
assert request('/api/license',opener=urllib.request.build_opener())[0]==403;checks.append('unauthenticated_read_blocked')
assert request('/api/jobs/report?id=missing',opener=urllib.request.build_opener())[0]==403;checks.append('unauthenticated_diagnostic_blocked')
assert request('/launch/'+service.session.launch)[0]==200
assert request('/api/state')[0]==403 and request('/api/jobs',{'kind':'pipeline','ids':[]})[0]==403;checks.append('unlicensed_read_and_jobs_blocked')
assert request('/api/license',headers={'Origin':'https://attacker.example'})[0]==403;checks.append('foreign_origin_blocked')
assert request('/api/license',headers={'Host':'127.0.0.1:1'})[0]==403;checks.append('wrong_host_port_blocked')
machine=win_security.machine_code();issuer=options.issuer.resolve();tokenfile=BASE/'test-license.txt'
subprocess.run([str(issuer),'--issue',machine,'发行验收', '1',str(tokenfile)],check=True);token=tokenfile.read_text('utf-8')
assert licensing.validate(token)['machine']==machine
for name,t,kw in [('wrong_machine',token,{'device':'MJ-'+'0'*32}),('expired',token,{'now':licensing.validate(token)['expiresAt']+1}),('tampered_signature',token[:-8]+'AAAAAAAA',{}),('malformed','MJ1.bad.bad',{})]:
    try:licensing.validate(t,**kw)
    except Exception:checks.append(name+'_rejected')
    else:raise AssertionError(name)
assert request('/api/license/activate',{'token':'MJ1.bad.bad'})[0]==400
assert request('/api/license/activate',{'token':token})[0]==200;checks.append('http_activation_success')
assert token.encode() not in (s.DATA/'license.bin').read_bytes();checks.append('saved_license_dpapi_protected')
status=json.loads(request('/api/state')[1]);assert not status['projects'] and not status['accounts'];checks.append('clean_recipient_state')
assert request('/api/state')[2]['X-Frame-Options']=='DENY';checks.append('security_response_headers')
clock=s.DATA/'license-clock.bin';previous=clock.read_bytes();clock.write_bytes(win_security.protect(json.dumps({'licenseId':licensing.validate(token)['licenseId'],'seen':int(time.time())+86400}).encode()))
assert not licensing.status(s.DATA,True)['valid'];clock.write_bytes(previous);assert licensing.status(s.DATA,True)['valid'];checks.append('clock_rollback_rejected')
# Real FFmpeg task through the protected compiled HTTP backend.
source=BASE/'source';source.mkdir(exist_ok=True);video=source/'第1集.mp4'
s.ff(['-f','lavfi','-i','testsrc2=s=320x180:r=25:d=1.2','-f','lavfi','-i','sine=frequency=440:duration=1.2','-c:v','libx264','-c:a','aac','-shortest',str(video)])
assert request('/api/config',{'output':str(BASE/'output'),'width':320,'height':180,'segmentSeconds':1,'autoRecords':False,'autoCover':False})[0]==200
projects=json.loads(request('/api/scan',{'source':str(source)})[1])['projects'];pid=projects[0]['id']
code,data,_=request('/api/jobs',{'kind':'pipeline','ids':[pid]});assert code==200,data;jid=json.loads(data)['id']
end=time.time()+90
while time.time()<end:
    job=s.JOBS[jid]
    if job.get('finished'):break
    time.sleep(.2)
assert job['status']=='completed',job.get('error');checks.append('compiled_authorized_real_video_pipeline')
if version>='v0.7.0':
    code,body,_=request('/api/jobs/report?id='+jid);diagnostic=json.loads(body);assert code==200 and diagnostic['status']=='completed' and 'config' not in diagnostic
    assert token not in body.decode('utf-8');checks.append('authenticated_diagnostic_excludes_license_and_configuration')
source_digest=s.sha256(video);assert source_digest
# Tamper only our disposable web asset; restore before any other test.
asset=dist/'_internal/web/activation.css';saved=asset.read_bytes()
try:
    asset.write_bytes(saved+b'\n/* altered */')
    try:licensing.verify_distribution(dist)
    except RuntimeError:checks.append('changed_application_file_rejected')
    else:raise AssertionError('tamper accepted')
finally:asset.write_bytes(saved)
licensing.verify_distribution(dist)
# UI test host remains active only while explicitly requested; token stays in a local test file.
(BASE/'report.json').write_text(json.dumps({'checks':checks,'compiledCore':s.__file__,'pipelineOutput':job.get('results',[]),'sourceSha256':source_digest},ensure_ascii=False,indent=2),'utf-8')
(ROOT/'tmp/latest-distribution-acceptance.json').write_text(json.dumps({'checks':checks,'version':version,'base':str(BASE),'compiledCore':s.__file__},ensure_ascii=False,indent=2),'utf-8')
print('DISTRIBUTION_CHECKS_OK',len(checks),flush=True)
service.shutdown();s.shutdown_jobs()
