"""Create signed offline engine ZIP64 from verified relocatable staging."""
from pathlib import Path
import os,json,hashlib,subprocess,zipfile,time
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp/portable-engine-v1'
OUT=ROOT/'release/v0.5.0';OUT.mkdir(parents=True,exist_ok=True)
files=[p for p in sorted(BASE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pyc','.log']]
manifest={'format':1,'product':'ManjuStudio','kind':'engine','version':'vsr-1.4.0-sttn-cu126','files':[]}
for i,p in enumerate(files):
    with p.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    manifest['files'].append({'path':p.relative_to(BASE).as_posix(),'bytes':p.stat().st_size,'sha256':digest})
    if i%5000==0:print('HASH',i,len(files),flush=True)
plain=ROOT/'tmp/engine-manifest.json';plain.write_text(json.dumps(manifest,separators=(',',':')),'utf-8')
signed=ROOT/'tmp/component-signature.json'
subprocess.run([str(ROOT/'授权管理/授权签发工具.exe'),'--sign-file',str(plain),str(signed)],check=True)
target=OUT/'漫剧工坊-AI离线引擎-v1.zip'
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=1,allowZip64=True) as z:
    z.write(signed,'component-signature.json')
    for i,p in enumerate(files):
        z.write(p,p.relative_to(BASE).as_posix())
        if i%5000==0:print('ZIP',i,len(files),flush=True)
with target.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
print(json.dumps({'file':str(target),'bytes':target.stat().st_size,'sha256':digest,'unpackedBytes':sum(x['bytes'] for x in manifest['files'])}),flush=True)
