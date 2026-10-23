from pathlib import Path
import json,subprocess,hashlib,zipfile,uuid
import engine_manager as m
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp/component-security-test'/uuid.uuid4().hex;BASE.mkdir(parents=True)
issuer=ROOT/'授权管理/授权签发工具.exe';checks=[]
def archive(name,files,override=None,extra=None):
    rows=[{'path':p,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for p,b in files.items()]
    if override:override(rows)
    manifest={'format':1,'product':'ManjuStudio','kind':'engine','files':rows};plain=BASE/(name+'.json');signed=BASE/(name+'-signed.json');plain.write_text(json.dumps(manifest),'utf-8')
    subprocess.run([str(issuer),'--sign-file',str(plain),str(signed)],check=True)
    zpath=BASE/(name+'.zip')
    with zipfile.ZipFile(zpath,'w') as z:
        z.write(signed,'component-signature.json')
        for p,b in files.items():z.writestr(p,b)
        if extra:extra(z)
    return zpath
files={'engine.json':json.dumps({'id':'test-component','python':'python/python.exe','root':'backend','mode':'sttn-auto'}).encode(),'python/python.exe':b'test placeholder - never execute','backend/README.txt':b'test placeholder'}
home=BASE/'data';value=m.install(archive('valid',files),home);assert value['id']=='test-component';checks.append('valid_signed_component_import')
before=(home/'engines/active.json').read_bytes()
cases=[('traversal',archive('traversal',{'../escape.txt':b'x'})),('hash',archive('hash',files,lambda r:r[0].update(sha256='0'*64))),('extra',archive('extra',files,extra=lambda z:z.writestr('unlisted.py',b'x'))),('oversize',archive('oversize',files,lambda r:r[0].update(bytes=21*1024**3)))]
for name,p in cases:
    try:m.install(p,home)
    except Exception:checks.append(name+'_rejected')
    else:raise AssertionError(name)
    assert (home/'engines/active.json').read_bytes()==before
assert not (BASE/'escape.txt').exists();assert not list((home/'engines').glob('_import-*'));checks.append('failed_import_preserves_active_and_cleans_owned_stage')
(BASE/'report.json').write_text(json.dumps({'checks':checks},indent=2),'utf-8');print('COMPONENT_SECURITY_OK',len(checks))
