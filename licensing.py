"""Signed artifact verification and compatibility helpers for historical licenses."""
from __future__ import annotations
import base64,json,time,sys
from pathlib import Path
from win_security import verify,machine_code
from release_key import TRUSTED_PUBLIC_KEYS_B64
def required():return False
def decode(value):
    if not isinstance(value,str) or len(value)>48*1024*1024:raise ValueError('签名数据格式无效')
    return base64.b64decode(value+'='*((-len(value))%4),altchars=b'-_',validate=True)

def signed_payload(envelope,kind='artifact'):
    if kind not in ('artifact','license') or not isinstance(envelope,dict) or envelope.get('kind')!=kind:raise ValueError('签名清单类型无效')
    payload=decode(envelope.get('payload'));signature=decode(envelope.get('signature'))
    message=('ManjuStudio/'+('L1' if kind=='license' else 'Artifact1')+'\n').encode()+payload
    # Only owner-pinned public keys are accepted. Envelope fields cannot add a key.
    if not any(verify(base64.b64decode(key),message,signature) for key in TRUSTED_PUBLIC_KEYS_B64):raise ValueError('签名校验失败，文件可能被修改')
    return json.loads(payload)

def validate(token,device=None,now=None):
    if not isinstance(token,str) or len(token)>12000:raise ValueError('授权码格式无效')
    parts=token.strip().split('.')
    if len(parts)!=3 or parts[0]!='MJ1':raise ValueError('请填写有效的 MJ1 授权码')
    data=signed_payload({'kind':'license','payload':parts[1],'signature':parts[2]},'license')
    if data.get('version')!=1 or data.get('machine')!=(device or machine_code()):raise ValueError('授权码与这台电脑不匹配')
    clock=time.time() if now is None else now
    if not isinstance(data.get('issuedAt'),int) or data['issuedAt']>clock+300:raise ValueError('授权尚未生效，请核对系统时间')
    expires=data.get('expiresAt')
    if type(expires) is not int or (expires and expires<=clock):raise ValueError('授权已到期，请联系签发方续期')
    if not isinstance(data.get('licenseId'),str):raise ValueError('授权信息不完整')
    return data

def status(home,force=False):
    return {'required':False,'valid':True,'message':'本地直接使用'}

def activate(home,token):
    return status(home)

def require(home):
    return None

def verify_distribution(home):
    if not getattr(sys,'frozen',False):return
    home=Path(home).resolve();path=home/'integrity.json'
    if not path.is_file():raise RuntimeError('缺少安装完整性清单，请使用原始安装包重新安装')
    data=signed_payload(json.loads(path.read_text('utf-8')))
    if data.get('product')!='ManjuStudio' or data.get('kind')!='application':raise RuntimeError('安装清单不属于本程序')
    import hashlib,re
    from concurrent.futures import ThreadPoolExecutor
    files=data.get('files')
    if not isinstance(files,list) or not files:raise RuntimeError('安装完整性清单为空或无效，请重新安装')
    names=set()
    for item in files:
        if not isinstance(item,dict):raise RuntimeError('安装完整性清单格式无效，请重新安装')
        name=item.get('path');size=item.get('bytes');digest=item.get('sha256')
        if (not isinstance(name,str) or not name or Path(name).is_absolute() or Path(name).drive or
                '..' in Path(name).parts or ':' in name or name.casefold() in names or
                type(size) is not int or size<0 or not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest)):
            raise RuntimeError('安装完整性清单格式无效，请重新安装')
        names.add(name.casefold())
    def verify_file(item):
        try:
            p=(home/item['path']).resolve(strict=True)
            if not p.is_relative_to(home) or not p.is_file() or p.stat().st_size!=item['bytes']:
                raise RuntimeError('程序文件缺失或被修改，请重新安装')
            with p.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
            if actual!=item['sha256']:raise RuntimeError('程序文件校验失败，请重新安装')
        except OSError as error:
            raise RuntimeError('程序文件缺失或无法读取，请重新安装')from error
    # Large optional program bundles contain thousands of small files. Bound the
    # I/O concurrency while still resolving, sizing and hashing every signed row.
    with ThreadPoolExecutor(max_workers=min(8,len(files))) as pool:
        for _ in pool.map(verify_file,files):pass
