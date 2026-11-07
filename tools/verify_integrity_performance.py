"""Compare both compiled verifiers on the same signed payload in both orders."""
from pathlib import Path
import argparse,json,os,subprocess,sys,time

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--version',required=True);parser.add_argument('--baseline',default='v0.10.10');args=parser.parse_args()
target=ROOT/'release'/args.version/'漫剧工坊'
snippet='''from pathlib import Path
import hashlib,json,sys,time
sys.path.insert(0,sys.argv[1])
import licensing
assert Path(licensing.__file__).resolve().parent==Path(sys.argv[1]).resolve() and licensing.__file__.endswith('.pyd')
sys.frozen=True
started=time.monotonic();licensing.verify_distribution(sys.argv[2]);elapsed=time.monotonic()-started
print(json.dumps({'seconds':round(elapsed,3),'module':licensing.__file__,'moduleSHA256':hashlib.sha256(Path(licensing.__file__).read_bytes()).hexdigest(),'allSignedFilesVerified':True}))
'''
env=os.environ.copy();env.pop('MANJU_REAL_API_KEY',None);env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1')
report={'version':args.version,'baseline':args.baseline,'testedPayload':str(target),'method':'separate fresh CPython processes; same signed payload; reverse-order repetition; OS file cache not forcibly purged','runs':[]}
for version in (args.baseline,args.version,args.version,args.baseline):
    result=subprocess.run([sys.executable,'-c',snippet,str(ROOT/'release'/version/'漫剧工坊/_internal'),str(target)],env=env,capture_output=True,text=True,timeout=360,check=True)
    row=json.loads(result.stdout.strip().splitlines()[-1]);row['verifierVersion']=version;report['runs'].append(row)
    print(json.dumps(row,ensure_ascii=True),flush=True)
report['ok']=all(row['allSignedFilesVerified'] for row in report['runs'])
(ROOT/'versions'/args.version/'integrity-performance-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print('INTEGRITY_COMPARISON_OK',flush=True)
