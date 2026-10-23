from pathlib import Path
import json,hashlib,subprocess,argparse
parser=argparse.ArgumentParser();parser.add_argument('--version',default='v0.5.0');parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--issuer',type=Path,default=Path(__file__).resolve().parent/'授权管理/当前签发工具-v2/授权签发工具.exe');options=parser.parse_args();version=options.version
if not __import__('re').fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号无效')
ROOT=Path(__file__).resolve().parent;DIST=ROOT/'release'/version/'漫剧工坊'
# Runtime/import checks can create bytecode beside collected upstream sources.
# Do not ship or sign mutable interpreter caches as application payload.
for cached in list(DIST.rglob('*.pyc')):
    if '__pycache__' in cached.parts:
        if not cached.resolve().is_relative_to(DIST.resolve()):raise ValueError('缓存路径超出发行目录')
        cached.unlink()
for folder in sorted(DIST.rglob('__pycache__'),key=lambda p:len(p.parts),reverse=True):
    if folder.resolve().is_relative_to(DIST.resolve()) and not any(folder.iterdir()):folder.rmdir()
m={'format':1,'product':'ManjuStudio','kind':'application','version':version[1:],'files':[]}
for p in sorted(DIST.rglob('*')):
    if p.is_file() and p.name!='integrity.json':
        with p.open('rb') as f:d=hashlib.file_digest(f,'sha256').hexdigest()
        m['files'].append({'path':p.relative_to(DIST).as_posix(),'bytes':p.stat().st_size,'sha256':d})
plain=ROOT/('tmp/application-manifest-'+version+'.json');plain.write_text(json.dumps(m,ensure_ascii=False,separators=(',',':')),'utf-8')
if options.prepare_only:
    print('MANIFEST_PREPARED_ONLY',len(m['files']),plain);raise SystemExit(0)
subprocess.run([str(options.issuer.resolve()),'--sign-file',str(plain),str(DIST/'integrity.json')],check=True,timeout=60)
import licensing
assert licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))==m,'Signed manifest differs from prepared application'
print('SIGNED',len(m['files']))
