"""Run a repository regression with product imports pinned to a signed build.

This validates compiled modules in the build interpreter. It is separate from
starting the frozen desktop executable and never changes the tested source.
"""
from pathlib import Path
import argparse
import ast
import hashlib
import importlib.abc
import importlib.machinery
import json
import re
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--version', required=True)
parser.add_argument('script')
args, remaining = parser.parse_known_args()
if not re.fullmatch(r'v\d+\.\d+\.\d+', args.version):
    raise ValueError('Invalid release version')
script = (ROOT / args.script).resolve()
if script.parent != ROOT or not script.name.startswith(('verify_', 'test_')) or script.suffix != '.py':
    raise ValueError('Only repository regression entry points are supported')
dist = ROOT / 'release' / args.version / '漫剧工坊'
internal = dist / '_internal'
tree = ast.parse((ROOT / 'build_hardened.py').read_text('utf-8'))
modules = next(ast.literal_eval(node.value) for node in tree.body
               if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'MODULES' for t in node.targets))


class ProductModules(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in modules:
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, [str(internal)])
        if spec is None or not isinstance(spec.loader, importlib.machinery.ExtensionFileLoader):
            raise ImportError('Compiled product module is missing: ' + fullname)
        return spec


sys.dont_write_bytecode = True
sys.path[:0] = [str(internal), str(ROOT / 'vendor'), str(ROOT)]
sys.meta_path.insert(0, ProductModules())
import licensing
previous = getattr(sys, 'frozen', None)
sys.frozen = True
try:
    licensing.verify_distribution(dist)
finally:
    if previous is None:
        del sys.frozen
    else:
        sys.frozen = previous
sys.argv = [str(script), *remaining]
started = time.monotonic()
runpy.run_path(str(script), run_name='__main__')
loaded = {}
for name in modules:
    if name in sys.modules:
        path = Path(sys.modules[name].__file__).resolve()
        if path.parent != internal.resolve() or path.suffix != '.pyd':
            raise AssertionError('Source fallback detected: ' + name)
        loaded[name] = {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
report = {'version': args.version, 'test': script.name, 'compiledModules': loaded,
          'signedBuildVerified': True, 'seconds': round(time.monotonic() - started, 3),
          'desktopExecutableStarted': False, 'sourceFallback': False}
out = dist.parent / '验收证据' / (script.stem + '-compiled-imports.json')
out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print('COMPILED_REGRESSION_OK', script.name, len(loaded))
