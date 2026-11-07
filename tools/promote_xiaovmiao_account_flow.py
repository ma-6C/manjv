"""Publish the verified startup payload into the local companion module."""
from pathlib import Path
import hashlib
import json
import shutil
import time
import argparse

parser=argparse.ArgumentParser(description='Restore the original software sign-in flow; withdrawn from the current companion module')
parser.add_argument('--restore-software-sign-in',action='store_true')
options=parser.parse_args()
if not options.restore_software_sign_in:
    raise SystemExit('此方案会重新出现小v猫软件自身的登录页，已从当前模块撤回；没有明确恢复软件登录的要求时不要使用。')

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'tmp/xiaovmiao-normal-account-flow'
MODULE=ROOT/'modules/xiaovmiao'
prepared=json.loads((STAGE/'preparation.json').read_text('utf-8'))
started=json.loads((STAGE/'startup.json').read_text('utf-8'))
assert prepared['ok'] and started['ok'] and prepared['originalPreloadUnchanged'] and prepared['compiledBackendUnchanged']
assert prepared['originalAccountIpcRestored'] and prepared['fakeSoftwareLoginRemoved']
targets=['resources/app.asar','vcat_local_init.exe']
# Check image-file locks before changing either side of the integrity pair.
for name in targets:
    with (MODULE/'程序'/name).open('rb+'):pass
backup=ROOT/'tmp/xiaovmiao-account-flow-backups'/str(time.time_ns())
backup.mkdir(parents=True)
for name in targets:
    dest=backup/name;dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(MODULE/'程序'/name,dest)
shutil.copy2(MODULE/'module.json',backup/'module.json')
value=json.loads((MODULE/'module.json').read_text('utf-8'))
for name in targets:
    target=MODULE/'程序'/name;temporary=target.with_suffix(target.suffix+'.account-flow-new')
    shutil.copy2(STAGE/'程序'/name,temporary);temporary.replace(target)
    with target.open('rb')as stream:value['files'][name]=hashlib.file_digest(stream,'sha256').hexdigest()
value['mode']='standard-account-flow';value['accountFlow']='original-online'
(MODULE/'module.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8')
report={'ok':True,'mode':value['mode'],'originalDataKept':True,
        'userProfileSelectionUnchanged':True,'backup':str(backup),
        'realPlatformLoginVerified':False,'accountPersistenceVerified':False}
(ROOT/'tmp/xiaovmiao-account-flow-promotion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=True))
