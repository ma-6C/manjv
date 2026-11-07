"""Install only the account-fixture-free payload after isolated acceptance."""
from pathlib import Path
import hashlib
import json
import shutil
import time
from repair_xiaovmiao_network import read_asar,digest

ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'modules/xiaovmiao'
STAGE=ROOT/'tmp/xiaovmiao-local-accounts-stage'
PRODUCTION=ROOT/'tmp/xiaovmiao-local-accounts-production'
acceptance=json.loads((ROOT/'tmp/xiaovmiao-local-accounts-tests/latest.json').read_text('utf-8'))
build=json.loads((PRODUCTION/'build.json').read_text('utf-8'))
assert acceptance['ok'] and len(acceptance['results'])==4 and not acceptance['realPlatformLoginVerified']
assert 'comment_permission_failure_explained_without_fabricating_software_login'in acceptance['results'][0]['checks']
assert build['ok'] and not build['testCodeIncluded'] and not build['softwareLoginFlowChanged']
assert digest(MODULE/'程序/resources/app.asar')==build['sourceArchiveSha256']
assert digest(MODULE/'程序/vcat_local_init.exe')==build['sourceExecutableSha256']
_,stage_items=read_asar(STAGE/'程序/resources/app.asar')
_,prod_items=read_asar(PRODUCTION/'程序/resources/app.asar')
stage={name:data for name,_,data in stage_items};prod={name:data for name,_,data in prod_items}
assert 'manju_account_acceptance.js'not in prod
assert prod['manju_local_accounts.js']==stage['manju_local_accounts.js']==(ROOT/'engines/xiaovmiao-local-accounts.js').read_bytes()
assert prod['manju_platform_network.js']==stage['manju_platform_network.js']
stage_main=stage['main.js'].decode('utf-8')
start=stage_main.index(" if(process.env.MANJU_XIAOVMIAO_LOCAL_ACCOUNT_TEST==='1'){")
end=stage_main.index('\n }\n',start)+len('\n }\n')
assert stage_main[:start]+stage_main[end:]==prod['main.js'].decode('utf-8')
assert prod['assets/app.min.js']==stage['assets/app.min.js']
assert b'9000000000000000001'not in prod['manju_local_accounts.js']
assert b'MANJU_XIAOVMIAO_LOCAL_ACCOUNT_TEST'not in prod['main.js']
targets=['resources/app.asar','vcat_local_init.exe']
for name in targets:
    with (MODULE/'程序'/name).open('rb+'):pass
backup=ROOT/'tmp/xiaovmiao-local-accounts-backups'/str(time.time_ns());backup.mkdir(parents=True)
for name in targets:
    target=backup/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(MODULE/'程序'/name,target)
shutil.copy2(MODULE/'module.json',backup/'module.json')
manifest=json.loads((MODULE/'module.json').read_text('utf-8'))
for name in targets:
    target=MODULE/'程序'/name;temporary=target.with_suffix(target.suffix+'.accounts-new')
    shutil.copy2(PRODUCTION/'程序'/name,temporary);temporary.replace(target);manifest['files'][name]=digest(target)
manifest.update(mode='local-platform-accounts',accountRegistration='official-profile-local')
(MODULE/'module.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
report={'ok':True,'mode':manifest['mode'],'testFixtureExcluded':True,'testedLogicMatchesProduction':True,
        'softwareSignInChanged':False,'userProfileSelectionUnchanged':True,'realPlatformLoginVerified':False,'backup':str(backup)}
(ROOT/'tmp/xiaovmiao-local-accounts-promotion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=True))
