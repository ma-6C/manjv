"""Observe original startup with a new profile; do not automate sign-in."""
from pathlib import Path
import json
import os
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'tmp/xiaovmiao-normal-account-flow'
profile=BASE/('test-profile-'+str(time.time_ns()));profile.mkdir(parents=True)
report=BASE/'startup.json';report.unlink(missing_ok=True)
env=os.environ.copy()
for key in ('NODE_OPTIONS','NODE_PATH','ELECTRON_RUN_AS_NODE'):env.pop(key,None)
env.update(MANJU_XIAOVMIAO_PROFILE=str(profile),MANJU_XIAOVMIAO_FLOW_REPORT=str(report))
program=BASE/'程序/vcat_local_init.exe'
with (BASE/'stdout.log').open('wb')as out,(BASE/'stderr.log').open('wb')as err:
    result=subprocess.run([str(program)],cwd=program.parent,env=env,stdin=subprocess.DEVNULL,stdout=out,stderr=err,
                          timeout=50,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
value=json.loads(report.read_text('utf-8'))if report.is_file()else {'ok':False,'error':'No startup report'}
print(json.dumps({'exitCode':result.returncode,**value},ensure_ascii=True))
raise SystemExit(not value.get('ok'))
