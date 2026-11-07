"""Verify same-session recognition, real SQLite persistence and native restart."""
from pathlib import Path
import json
import os
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'tmp/xiaovmiao-local-accounts-tests'
BASE.mkdir(parents=True,exist_ok=True)
profile=BASE/('profile-'+str(time.time_ns()));profile.mkdir()
env=os.environ.copy()
for key in ('NODE_OPTIONS','NODE_PATH','ELECTRON_RUN_AS_NODE'):env.pop(key,None)
env.update(MANJU_XIAOVMIAO_LOCAL_ACCOUNT_TEST='1',MANJU_XIAOVMIAO_PROFILE=str(profile),MANJU_XIAOVMIAO_ACCOUNT_TEST_ROOT=str(BASE))
program=ROOT/'tmp/xiaovmiao-local-accounts-stage/程序/vcat_local_init.exe'
results=[]
for phase in ['save','restart','prepare_recovery','recover']:
    if phase=='prepare_recovery':
        profile=BASE/('profile-recovery-'+str(time.time_ns()));profile.mkdir();env['MANJU_XIAOVMIAO_PROFILE']=str(profile)
    report=BASE/(phase+'-'+profile.name+'.json')
    env.update(MANJU_XIAOVMIAO_ACCOUNT_TEST_PHASE=phase,MANJU_XIAOVMIAO_ACCOUNT_REPORT=str(report))
    with report.with_suffix('.stdout.log').open('wb')as out,report.with_suffix('.stderr.log').open('wb')as err:
        result=subprocess.run([str(program)],cwd=program.parent,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                              timeout=45,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    value=json.loads(report.read_text('utf-8'))if report.is_file()else {'ok':False,'error':'No acceptance report'}
    results.append(value);print(json.dumps(value,ensure_ascii=True),flush=True)
    if not value.get('ok'):break
summary={'ok':len(results)==4 and all(v.get('ok')for v in results),'fixture':True,'realPlatformLoginVerified':False,'results':results,'profile':str(profile)}
(BASE/'latest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf-8')
raise SystemExit(not summary['ok'])
