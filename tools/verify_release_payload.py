"""Check compiled release content, runtime resources and accidental secrets."""
from pathlib import Path
import argparse,ast,hashlib,json,os,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.dont_write_bytecode=True
import licensing
from tools.release_safety import verify_manifest_file_set
parser=argparse.ArgumentParser();parser.add_argument('--version',required=True);args=parser.parse_args()
if not re.fullmatch(r'v\d+\.\d+\.\d+',args.version):raise ValueError('Invalid version')
dist=ROOT/'release'/args.version/'漫剧工坊';record=ROOT/'versions'/args.version
inputs=json.loads((record/'build-inputs.json').read_text('utf-8'))
manifest=licensing.signed_payload(json.loads((dist/'integrity.json').read_text('utf-8-sig')))
assert manifest['version']==args.version[1:]
previous=getattr(sys,'frozen',None);sys.frozen=True
try:licensing.verify_distribution(dist)
finally:
    if previous is None:del sys.frozen
    else:sys.frozen=previous
verify_manifest_file_set(dist,manifest)
modules=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'build_hardened.py').read_text('utf-8')).body
             if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MODULES' for t in n.targets))
compiled={}
for name in modules:
    p=next((dist/'_internal').glob(name+'.cp312-win_amd64.pyd'));compiled[name]=p.relative_to(dist).as_posix()
    assert not (dist/'_internal'/(name+'.py')).exists()
policy=next(Path(p) for p in inputs['runtimeSha256'] if p.endswith('codex-rejected-cas.pem'))
with policy.open('rb') as f:policy_hash=hashlib.file_digest(f,'sha256').hexdigest()
with (dist/'_internal'/policy.name).open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==policy_hash
upstream_fixture='modules/xiaovmiao/程序/resources/app/node_modules/node-gyp/test/fixtures/server.key'
protocol_schema='engines/dramaclip/source/protocol/schemas/jobs.json'
schema=dist/protocol_schema
schema_hash=None
if schema.is_file():
    planner=json.loads((dist/'engines/dramaclip/source-manifest.json').read_text('utf-8'))
    assert planner['commit']=='3562664e0d7f00dc4a5ff5784337751c510925a2'
    schema_hash=hashlib.sha256(schema.read_bytes()).hexdigest()
    assert schema_hash==planner['sourceSha256']['protocol/schemas/jobs.json']==inputs['sourceSha256'][protocol_schema]
    assert schema_hash==hashlib.sha256((ROOT/protocol_schema).read_bytes()).hexdigest()
    specification=json.loads(schema.read_text('utf-8'))
    assert specification['$schema']=='https://json-schema.org/draft/2020-12/schema'
    assert specification['$id']=='https://dramaclip.dev/protocol/jobs.json' and specification['namespace']=='jobs'
fixture=dist/upstream_fixture
fixture_hash=None
if fixture.is_file():
    module=json.loads((dist/'modules/xiaovmiao/module.json').read_text('utf-8'))
    source=ROOT/upstream_fixture
    fixture_hash=hashlib.sha256(fixture.read_bytes()).hexdigest()
    assert fixture_hash==module['files']['resources/app/node_modules/node-gyp/test/fixtures/server.key']
    assert source.is_file() and fixture_hash==hashlib.sha256(source.read_bytes()).hexdigest()
    # Its use in node-gyp's HTTPS test identifies this static fixture; retain
    # exact manifest/source hashes rather than allowing arbitrary .key files.
    test=fixture.parent.parent/'test-download.js'
    assert "fixtures/server.key" in test.read_text('utf-8')
sensitive=[p.relative_to(dist).as_posix() for p in dist.rglob('*') if p.is_file() and
           ((p.suffix.lower() in ['.dpapi','.mjk','.pfx','.pem','.key'] and p.name!=policy.name)
            or p.name in ['state.json','jobs.json','license.bin','issuer-key.dpapi'])
           and p.relative_to(dist).as_posix() not in {upstream_fixture,protocol_schema}]
assert not sensitive,sensitive
secret=os.environ.get('MANJU_REAL_API_KEY','').encode();scanned=0
for p in dist.rglob('*'):
    if not p.is_file():continue
    scanned+=1
    if not secret:continue
    tail=b''
    with p.open('rb') as f:
        while chunk:=f.read(1024*1024):
            block=tail+chunk;assert secret not in block,'Credential found in '+str(p.relative_to(dist));tail=block[-len(secret):]
core=json.loads((dist/'_internal/engines/guoapp-core/manifest.json').read_text('utf-8'))
with (dist/'_internal/engines/guoapp-core/duanju_core.dll').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==core['sha256']
report={'version':args.version[1:],'signedManifestVersion':manifest['version'],'signedFiles':len(manifest['files']),
        'signedFileHashesVerified':True,'unsignedExtraFilesAbsent':True,
        'compiledModules':compiled,'sourceProductModulesAbsent':True,'credentialScanFiles':scanned,
        'credentialScanPerformed':bool(secret),'customerKeysFound':False,'privateMaterialsFound':False,
        'nativeCoreHashVerified':True,'sslPolicyIncluded':True,'sslPolicySha256':policy_hash,
        'pinnedDramaClipJobsProtocolSchema':{'path':protocol_schema,'sha256':schema_hash} if schema_hash else None,
        'upstreamNodeGypFixtureKey':{'path':upstream_fixture,'sha256':fixture_hash} if fixture_hash else None}
(record/'payload-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'version':report['version'],'signedFiles':len(manifest['files']),'compiledModules':len(compiled),
                  'customerKeysFound':False,'sslPolicyIncluded':True}))
