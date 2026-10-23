"""Compare source inputs with a recorded release without changing files."""
from pathlib import Path
import argparse,hashlib,json

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--version',default='v0.8.6');args=parser.parse_args()
record=json.loads((root/'versions'/args.version/'build-inputs.json').read_text('utf-8'))
matched=[];generated=[];errors=[]
for name,expected in record['sourceSha256'].items():
    path=root/name
    if not path.is_file():
        (generated if path.suffix.lower()=='.dll' else errors).append(name)
    elif hashlib.sha256(path.read_bytes()).hexdigest()!=expected:errors.append(name)
    else:matched.append(name)
print(json.dumps({'version':record['version'],'matched':len(matched),'generatedComponentsNotPresent':generated,'changedOrMissing':errors},ensure_ascii=False,indent=2))
raise SystemExit(bool(errors))
