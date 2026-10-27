"""Record or verify exact desktop build inputs without reading user data."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--version', required=True)
parser.add_argument('--verify', action='store_true')
args = parser.parse_args()
if not re.fullmatch(r'v\d+\.\d+\.\d+', args.version):
    raise ValueError('Invalid release version')
target = ROOT / 'versions' / args.version / 'build-inputs.json'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


if args.verify:
    record = json.loads(target.read_text('utf-8'))
    changed = [name for name, sha in record['sourceSha256'].items()
               if not (ROOT / name).is_file() or digest(ROOT / name) != sha]
    print(json.dumps({'version': args.version, 'inputs': len(record['sourceSha256']),
                      'changedOrMissing': changed}, ensure_ascii=False))
    raise SystemExit(bool(changed))

tree = ast.parse((ROOT / 'build_hardened.py').read_text('utf-8'))
modules = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'MODULES' for t in n.targets))
files = {ROOT / (name + '.py') for name in modules}
files.update(ROOT / name for name in ['desktop.py', 'build_hardened.py', 'build_installer.py',
                                     'PrerequisiteRunner.cs', 'sign_distribution.py', 'requirements.txt', 'package.json'])
for folder in ['web', 'assets', 'engines/guoapp-core', 'engines/jianying-draft',
               'engines/social-auto-upload/uploader', 'engines/social-auto-upload/utils']:
    files.update(p for p in (ROOT / folder).rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.log'})
files.update(ROOT / 'engines/social-auto-upload' / name for name in ['conf.py', 'LICENSE'])
for path in files:
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Build input resolves outside workspace')
record = {'version': args.version, 'recordedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
          'baseCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
          'compiledProductModules': modules,
          'sourceSha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}}
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps({'version': args.version, 'inputs': len(files), 'compiledModules': len(modules)}))
