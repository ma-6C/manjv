"""Load the public Douyin creator entry in a real isolated Electron webview."""
from pathlib import Path
import json
import argparse
import os
import subprocess

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--program',type=Path,default=ROOT/'modules/xiaovmiao/程序/vcat_local_init.exe')
parser.add_argument('--output-dir',type=Path,default=ROOT/'tmp/xiaovmiao-network-check')
parser.add_argument('--software-rendering',action='store_true')
args=parser.parse_args()
check=args.output_dir.resolve()
if not check.is_relative_to((ROOT/'tmp').resolve()):raise ValueError('Network test output must stay in the isolated workspace test directory')
check.mkdir(parents=True,exist_ok=True)
report=check/'page-load.json';report.unlink(missing_ok=True)
env=os.environ.copy()
for name in ('NODE_OPTIONS','NODE_PATH','ELECTRON_RUN_AS_NODE'):env.pop(name,None)
env.update(MANJU_XIAOVMIAO_NETWORK_CHECK='1',MANJU_XIAOVMIAO_PROFILE=str(check/'isolated-profile'),
           MANJU_XIAOVMIAO_NETWORK_REPORT=str(report))
program=args.program.resolve()
with (check/'stdout.log').open('wb') as stdout,(check/'stderr.log').open('wb') as stderr:
    flags=['--disable-gpu','--disable-renderer-backgrounding','--disable-backgrounding-occluded-windows'] if args.software_rendering else []
    result=subprocess.run([str(program),*flags],cwd=program.parent,env=env,stdin=subprocess.DEVNULL,
        stdout=stdout,stderr=stderr,timeout=60,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
value=json.loads(report.read_text('utf-8')) if report.is_file() else {'ok':False,'error':'No Electron check report'}
print(json.dumps({'exitCode':result.returncode,**value},ensure_ascii=False))
raise SystemExit(not value.get('ok'))
