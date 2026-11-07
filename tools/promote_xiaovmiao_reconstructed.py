"""Replace the complete companion payload after isolated startup verification."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import time
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from xiaovmiao import Manager,checked_executable


def promote(stage,profile):
    stage=Path(stage).resolve();profile=Path(profile).resolve()
    if not stage.is_relative_to(ROOT/'tmp'):raise ValueError('Expected a staged module')
    report=json.loads((stage.parent/'smoke.json').read_text('utf-8'))
    if not report.get('ok')or report.get('realUserProfileUsed')is not False:raise ValueError('Missing isolated startup verification')
    manifest=json.loads((stage/'module.json').read_text('utf-8'))
    if manifest.get('mode')!='local-reconstructed'or manifest.get('profileLayout')!='workspace':raise ValueError('Wrong payload mode')
    checked_executable(str(stage/'程序'/manifest['executable']))
    if not(profile/'workspace/.vcat/offline-local/vcat.db').is_file():raise ValueError('新版现有数据目录未找到；未切换到空库')
    files=manifest['files']
    for name,sha in files.items():
        path=stage/'程序'/name
        if not path.resolve().is_relative_to((stage/'程序').resolve()):raise ValueError('Invalid payload path')
        if path.name.casefold()in {'cookies','vcat.db','login data'}:raise ValueError('Unexpected user data in payload')
        with path.open('rb')as stream:
            if hashlib.file_digest(stream,'sha256').hexdigest()!=sha:raise ValueError('Payload hash mismatch: '+name)
    module=ROOT/'modules/xiaovmiao'
    backup=ROOT/'tmp/xiaovmiao-replacement-backups'/str(time.time_ns());backup.mkdir(parents=True)
    settings=ROOT/'data/xiaovmiao.json'
    if settings.exists():shutil.copy2(settings,backup/'xiaovmiao.json')
    # Preserve startup evidence outside the clean distributable module.
    if(stage/'logs').exists():(stage/'logs').rename(stage.parent/('smoke-logs-'+str(time.time_ns())))
    if any(p.name not in {'程序','module.json'}for p in stage.iterdir()):raise ValueError('Unexpected staged module contents')
    module.rename(backup/'module')
    try:
        stage.rename(module)
        manager=Manager(ROOT/'data',ROOT)
        manager.configure(str(module/'程序'/manifest['executable']),str(profile))
    except BaseException:
        if module.exists():module.rename(stage)
        (backup/'module').rename(module)
        if(backup/'xiaovmiao.json').exists():shutil.copy2(backup/'xiaovmiao.json',settings)
        raise
    result={'ok':True,'mode':manifest['mode'],'version':manifest['version'],'build':manifest['build'],
            'filesVerified':len(files),'backup':str(backup),'executable':manager.path,'profile':manager.profile,
            'oldDataPreserved':True,'newProfileCopied':False,'isolatedStartupVerified':True,
            'realAccountBusinessReverified':False,'restartHostRequired':True}
    (ROOT/'tmp/xiaovmiao-reconstructed-replacement.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--stage',type=Path,required=True);parser.add_argument('--profile',type=Path,required=True)
    args=parser.parse_args();print(json.dumps(promote(args.stage,args.profile),ensure_ascii=True))
