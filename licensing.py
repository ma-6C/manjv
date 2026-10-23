"""Offline, signed and machine-bound licenses. No signing key is distributed."""
from __future__ import annotations
import base64,json,time,threading,sys,os
from pathlib import Path
from win_security import protect,verify,machine_code
from release_key import TRUSTED_PUBLIC_KEYS_B64
LOCK=threading.RLock();CACHE={}

def required():return bool(getattr(sys,'frozen',False))
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

def _clock(data,home,write=False):
    file=home/'license-clock.bin';now=int(time.time());previous={}
    if file.exists():
        try:previous=json.loads(protect(file.read_bytes(),decrypt=True))
        except Exception:raise ValueError('授权时间记录异常，请重新输入授权码') from None
        if previous.get('licenseId')==data['licenseId'] and now<int(previous.get('seen',0))-300:raise ValueError('系统时间早于上次使用记录，请校准时间后重试')
    if write and now-int(previous.get('seen',0))>=60:
        value=protect(json.dumps({'licenseId':data['licenseId'],'seen':max(now,int(previous.get('seen',0)))}).encode())
        temp=file.with_suffix('.tmp');temp.write_bytes(value);temp.replace(file)

def status(home,force=False):
    home=Path(home);key=str(home)
    if not required():return {'required':False,'valid':True,'machineCode':machine_code(),'customer':'开发环境','expiresAt':0}
    with LOCK:
        cached=CACHE.get(key)
        if not force and cached and time.monotonic()-cached[0]<5:return cached[1]
        result={'required':True,'valid':False,'machineCode':machine_code(),'message':'请联系签发方获取这台电脑的授权码'}
        try:
            token=protect((home/'license.bin').read_bytes(),decrypt=True).decode('utf-8');data=validate(token);_clock(data,home,True)
            result.update(valid=True,customer=data.get('customer',''),licenseId=data['licenseId'],expiresAt=data['expiresAt'],message='授权有效')
        except FileNotFoundError:pass
        except Exception as error:result['message']=str(error)
        CACHE[key]=(time.monotonic(),result);return result

def activate(home,token):
    home=Path(home)
    with LOCK:
        data=validate(token);home.mkdir(parents=True,exist_ok=True)
        temp=home/'license.tmp';temp.write_bytes(protect(token.strip().encode()));temp.replace(home/'license.bin')
        clock=home/'license-clock.bin'
        # Explicit activation establishes a fresh clock record after signature verification.
        temp=home/'license-clock.tmp';temp.write_bytes(protect(json.dumps({'licenseId':data['licenseId'],'seen':int(time.time())}).encode()));temp.replace(clock)
        CACHE.pop(str(home),None);return status(home,True)

def require(home):
    result=status(home)
    if not result['valid']:raise PermissionError(result['message'])

def verify_distribution(home):
    if not required():return
    home=Path(home);path=home/'integrity.json'
    if not path.is_file():raise RuntimeError('缺少安装完整性清单，请使用原始安装包重新安装')
    data=signed_payload(json.loads(path.read_text('utf-8')))
    if data.get('product')!='ManjuStudio' or data.get('kind')!='application':raise RuntimeError('安装清单不属于本程序')
    import hashlib
    for item in data.get('files',[]):
        p=(home/item['path']).resolve()
        if not p.is_relative_to(home.resolve()) or not p.is_file() or p.stat().st_size!=item['bytes']:raise RuntimeError('程序文件缺失或被修改，请重新安装')
        h=hashlib.sha256()
        with p.open('rb') as f:
            while chunk:=f.read(1024*1024):h.update(chunk)
        if h.hexdigest()!=item['sha256']:raise RuntimeError('程序文件校验失败，请重新安装')
