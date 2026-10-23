"""Exercise the explicitly approved two-key rotation without exposing credentials."""
from pathlib import Path
import base64,hashlib,json,os,re,subprocess,sys,tempfile,time,zipfile

ROOT=Path(__file__).resolve().parent
COMPILED='--compiled' in sys.argv
VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.2'
sys.dont_write_bytecode=True
if COMPILED:sys.path.insert(0,str(ROOT/'release'/VERSION/'漫剧工坊/_internal'))
else:sys.path.insert(0,str(ROOT))
import licensing as lic,release_key as keys,win_security as sec

BASE=Path(tempfile.mkdtemp(prefix='signing-compatibility-',dir=ROOT/'tmp'))
checks=[]
def check(name,value=True):
    assert value,name
    checks.append(name)
def rejected(name,fn):
    try:fn()
    except (ValueError,RuntimeError):check(name)
    else:raise AssertionError(name)
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def token_in(path):
    return re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',path.read_text('utf-8-sig')).group(0)
def envelope(token,kind='license'):
    parts=token.split('.')
    return {'kind':kind,'payload':parts[1],'signature':parts[2]}

original_files=[ROOT/'授权管理'/name for name in ('issuer-key.dpapi','public-key.txt','授权签发工具.exe','本机长期授权码.txt','客户电脑-33E306E5-永久授权码.txt')]
before={str(p):digest(p) for p in original_files}
check('exactly_two_distinct_pinned_keys',len(keys.TRUSTED_PUBLIC_KEYS_B64)==2 and len(set(keys.TRUSTED_PUBLIC_KEYS_B64))==2)
check('original_public_key_preserved',keys.PUBLIC_KEY_B64==(ROOT/'授权管理/public-key.txt').read_text('utf-8-sig').strip())
check('current_public_key_matches_separate_issuer',keys.CURRENT_PUBLIC_KEY_B64==(ROOT/'授权管理/当前签发工具-v2/public-key.txt').read_text('utf-8-sig').strip())
if COMPILED:check('compiled_licensing_loaded',lic.__file__.endswith('.pyd'))
owner=token_in(ROOT/'授权管理/本机长期授权码.txt')
check('existing_owner_permanent_license_valid',lic.validate(owner)['expiresAt']==0)
customer=token_in(ROOT/'授权管理/客户电脑-33E306E5-永久授权码.txt')
customer_device='MJ-33E306E57474704301B22F3CD9B874C2'
check('existing_customer_permanent_license_valid',lic.validate(customer,device=customer_device)['expiresAt']==0)
rejected('old_license_still_machine_bound',lambda:lic.validate(customer,device='MJ-'+'0'*32))
rejected('old_license_future_clock_rejected',lambda:lic.validate(owner,now=lic.validate(owner)['issuedAt']-301))
with zipfile.ZipFile(ROOT/'release/v0.8.1/对外发送/漫剧工坊-AI离线引擎-v1.zip') as archive:
    engine=lic.signed_payload(json.loads(archive.read('component-signature.json')))
check('unchanged_old_offline_engine_signature_valid',engine['product']=='ManjuStudio' and engine['kind']=='engine' and bool(engine['files']))
old_envelope=json.loads((ROOT/'release/v0.8.1/漫剧工坊/integrity.json').read_text('utf-8'))
old_manifest=lic.signed_payload(old_envelope)
check('old_application_manifest_signature_valid',old_manifest['kind']=='application' and old_manifest['version']=='0.8.1')

issuer=ROOT/'授权管理/当前签发工具-v2/授权签发工具.exe'
new_file=BASE/'one-day-test-license.txt'
subprocess.run([str(issuer),'--issue',sec.machine_code(),'签名兼容验收','1',str(new_file)],check=True,timeout=30)
new=new_file.read_text('utf-8-sig');new_data=lic.validate(new)
check('current_issuer_license_valid',new_data['expiresAt']>new_data['issuedAt'])
rejected('new_license_wrong_machine_rejected',lambda:lic.validate(new,device='MJ-'+'0'*32))
rejected('new_license_expiry_rejected',lambda:lic.validate(new,now=new_data['expiresAt']))
rejected('new_license_future_issue_rejected',lambda:lic.validate(new,now=new_data['issuedAt']-301))
tampered=envelope(new);raw=bytearray(lic.decode(tampered['signature']));raw[0]^=1
tampered['signature']=base64.urlsafe_b64encode(raw).decode().rstrip('=')
rejected('tampered_signature_rejected',lambda:lic.signed_payload(tampered,'license'))
changed=envelope(new);changed['payload']=base64.urlsafe_b64encode(json.dumps({**new_data,'machine':'MJ-'+'0'*32}).encode()).decode().rstrip('=')
rejected('altered_signed_payload_rejected',lambda:lic.signed_payload(changed,'license'))
rejected('license_signature_cannot_sign_artifact',lambda:lic.signed_payload(envelope(new,'artifact')))
rejected('artifact_signature_cannot_issue_license',lambda:lic.signed_payload({**old_envelope,'kind':'license'},'license'))
rejected('unknown_envelope_kind_rejected',lambda:lic.signed_payload({'kind':'other','payload':'e30','signature':'AA'},'other'))
rejected('unsigned_license_rejected',lambda:lic.validate('MJ1.e30.AA'))

# A valid signature made by a fresh, memory-only key must not become trusted by
# supplying that public key in the envelope. No private key leaves this process.
script="""$alg = New-Object System.Security.Cryptography.ECDsaCng; try { $alg.KeySize = 256; $alg.HashAlgorithm = [System.Security.Cryptography.CngAlgorithm]::Sha256; $payload = [Text.Encoding]::UTF8.GetBytes('{}'); $msg = [Text.Encoding]::UTF8.GetBytes(\"ManjuStudio/Artifact1`n{}\"); [pscustomobject]@{kind='artifact';payload=[Convert]::ToBase64String($payload);signature=[Convert]::ToBase64String($alg.SignData($msg));publicKey=[Convert]::ToBase64String($alg.Key.Export([System.Security.Cryptography.CngKeyBlobFormat]::EccPublicBlob))} | ConvertTo-Json -Compress } finally { $alg.Dispose() }"""
unknown=json.loads(subprocess.check_output(['powershell','-NoProfile','-NonInteractive','-Command',script],timeout=30).decode('utf-8-sig'))
check('unknown_key_signature_is_cryptographically_valid',sec.verify(base64.b64decode(unknown['publicKey']),b'ManjuStudio/Artifact1\n{}',lic.decode(unknown['signature'])))
rejected('envelope_supplied_unpinned_key_rejected',lambda:lic.signed_payload(unknown))

payload={'format':1,'product':'ManjuStudio','kind':'application','version':'test','files':[{'path':'payload.txt','bytes':4,'sha256':hashlib.sha256(b'safe').hexdigest()}]}
manifest_plain=BASE/'manifest-input.json';manifest_plain.write_text(json.dumps(payload),'utf-8')
manifest_signed=BASE/'integrity.json'
subprocess.run([str(issuer),'--sign-file',str(manifest_plain),str(manifest_signed)],check=True,timeout=30)
check('current_issuer_artifact_signature_valid',lic.signed_payload(json.loads(manifest_signed.read_text('utf-8')))==payload)
old_frozen=getattr(sys,'frozen',None);sys.frozen=True
try:
    (BASE/'payload.txt').write_bytes(b'safe');lic.verify_distribution(BASE);check('new_signed_distribution_integrity_verified')
    (BASE/'payload.txt').write_bytes(b'evil')
    rejected('same_size_file_modification_rejected',lambda:lic.verify_distribution(BASE))
    (BASE/'payload.txt').unlink()
    rejected('missing_file_rejected',lambda:lic.verify_distribution(BASE))
    (BASE/'payload.txt').write_bytes(b'safe')
    # Activation and clock checks use only this disposable directory.
    status=lic.activate(BASE/'data',new)
    check('new_license_activation_valid',status['valid'])
    protected=(BASE/'data/license.bin').read_bytes()
    check('stored_license_remains_dpapi_protected',new.encode() not in protected and sec.protect(protected,decrypt=True).decode()==new)
    clock=BASE/'data/license-clock.bin';saved=clock.read_bytes()
    clock.write_bytes(sec.protect(json.dumps({'licenseId':new_data['licenseId'],'seen':int(time.time())+86400}).encode()))
    check('clock_rollback_remains_blocked',not lic.status(BASE/'data',True)['valid'])
    clock.write_bytes(saved);check('restored_test_clock_valid',lic.status(BASE/'data',True)['valid'])
finally:
    if old_frozen is None:del sys.frozen
    else:sys.frozen=old_frozen
check('original_keys_issuer_and_licenses_unchanged',before=={str(p):digest(p) for p in original_files})
report={'version':VERSION.lstrip('v'),'compiled':COMPILED,'passed':len(checks),'checks':checks,'base':str(BASE),'originalFilesPreserved':True,'privateKeyExported':False}
out=ROOT/('tmp/signing-compatibility-compiled.json' if COMPILED else 'tmp/signing-compatibility-source.json')
out.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'compiled':COMPILED,'originalFilesPreserved':True},ensure_ascii=False))
