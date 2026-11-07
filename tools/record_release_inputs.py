"""Record or verify exact desktop build inputs without reading user data."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import re
import subprocess
import time
import ssl

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
    changed += [name for name,sha in record.get('runtimeSha256',{}).items()
                if not Path(name).is_file() or digest(Path(name))!=sha]
    print(json.dumps({'version': args.version, 'inputs': len(record['sourceSha256']),
                      'changedOrMissing': changed}, ensure_ascii=False))
    raise SystemExit(bool(changed))

if target.exists():
    raise FileExistsError('Build inputs already recorded; use --verify or choose a new release version')

tree = ast.parse((ROOT / 'build_hardened.py').read_text('utf-8'))
modules = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'MODULES' for t in n.targets))
files = {ROOT / (name + '.py') for name in modules}
files.update(ROOT / name for name in ['desktop.py', 'build_hardened.py', 'build_installer.py',
                                     'PrerequisiteRunner.cs', 'InstallerSettings.cs', 'installer_ui.nsh', 'installer_upgrade.nsh', 'sign_distribution.py', 'requirements.txt', 'package.json'])
files.update(ROOT/name for name in ['tools/dramaclip_sidecar.py','tools/prepare_dramaclip.py','tools/bundle_dramaclip_runtime.py','tools/release_safety.py','tools/rebuild_hongguo_core.py'])
files.update(path for path in (ROOT/'tools/guoapp_compat').rglob('*')
             if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc')
planner_manifest=ROOT/'engines/dramaclip/source-manifest.json'
if planner_manifest.is_file():
    files.add(planner_manifest)
    planner_source=json.loads(planner_manifest.read_text('utf-8'))
    for name in planner_source.get('sourceSha256',{}):
        path=ROOT/'engines/dramaclip/source'/name
        if not path.resolve().is_relative_to((ROOT/'engines/dramaclip/source').resolve()):
            raise ValueError('Invalid DramaClip source manifest path')
        files.add(path)
for folder in ['web', 'assets', 'engines/guoapp-core', 'engines/jianying-draft',
               'engines/social-auto-upload/uploader', 'engines/social-auto-upload/utils']:
    files.update(p for p in (ROOT / folder).rglob('*') if p.is_file()
                 and '__pycache__' not in p.parts and p.suffix not in {'.pyc', '.log'})
files.update(ROOT / 'engines/social-auto-upload' / name for name in ['conf.py', 'LICENSE'])
if (ROOT/'engines/xiaovmiao-platform-network.js').is_file():
    files.add(ROOT/'engines/xiaovmiao-platform-network.js')
if (ROOT/'engines/xiaovmiao-local-accounts.js').is_file():
    files.add(ROOT/'engines/xiaovmiao-local-accounts.js')
if (ROOT/'modules/xiaovmiao/module.json').is_file():
    files.add(ROOT/'modules/xiaovmiao/module.json')
    files.update(p for p in (ROOT/'modules/xiaovmiao/程序').rglob('*') if p.is_file())
for path in files:
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError('Build input resolves outside workspace')
runtime_files=[Path(ssl.__file__)]
ssl_policy=Path(ssl.__file__).parent/'codex-rejected-cas.pem'
if 'codex-rejected-cas.pem' in Path(ssl.__file__).read_text('utf-8'):runtime_files.append(ssl_policy)
record = {'version': args.version, 'recordedAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
          'baseCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
          'compiledProductModules': modules,'runtimeSha256':{str(p):digest(p) for p in runtime_files},
          'sourceSha256': {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(files)}}
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
print(json.dumps({'version': args.version, 'inputs': len(files), 'compiledModules': len(modules)}))
