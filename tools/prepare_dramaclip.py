"""Prepare the pinned DramaClip Python service in an isolated, optional engine folder.

No application/customer configuration or credentials are read or copied. Models are
not downloaded: the adapter reuses a local Whisper model, or an accompanying SRT.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

COMMIT = '3562664e0d7f00dc4a5ff5784337751c510925a2'
URL = f'https://codeload.github.com/efarsoft/DramaClip/zip/{COMMIT}'
# Fused mode keeps ASR/encoding in Manju. Heavy upstream ML/TTS extras are not
# needed and would impose an unrelated av/ctranslate2/CUDA compatibility matrix.
REQUIREMENTS = ['pydantic>=2.7,<3']


def prepare(root: Path, source: Path | None, skip_install: bool = False, local_dependencies: bool = False):
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if source is None:
        with tempfile.TemporaryDirectory(prefix='manju-dramaclip-') as temp:
            archive = Path(temp) / 'source.zip'
            urllib.request.urlretrieve(URL, archive)
            with zipfile.ZipFile(archive) as z:
                # GitHub archive extraction is confined to this temporary folder.
                base = Path(temp).resolve()
                for member in z.infolist():
                    if not (base / member.filename).resolve().is_relative_to(base):
                        raise ValueError('Invalid upstream archive path')
                z.extractall(temp)
            source = next(Path(temp).glob('DramaClip-*'))
            _copy(root, source)
    else:
        source = source.resolve()
        actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != COMMIT:
            raise ValueError(f'Expected source {COMMIT}, got {actual}')
        if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
            raise ValueError('Source checkout contains uncommitted changes')
        _copy(root, source)
    runtime = root / 'runtime'
    python = runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip' if local_dependencies else '--copies', str(runtime)], check=True)
    if local_dependencies:
        # Fused original-audio mode needs pydantic only: ASR and encoding use
        # Manju's existing isolated workers. Copy installed distributions and their
        # metadata/licenses; never add a .pth link to another mutable environment.
        site = runtime / ('Lib/site-packages' if os.name == 'nt' else f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
        site.mkdir(parents=True, exist_ok=True)
        copied = []
        for name in ('pydantic', 'pydantic-core', 'annotated-types', 'typing-extensions', 'typing-inspection'):
            dist = importlib.metadata.distribution(name)
            for item in dist.files or ():
                if '..' in Path(str(item)).parts or str(item).endswith('.pyc'):
                    continue
                src = Path(dist.locate_file(item)); target = site / str(item)
                if src.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)
            copied.append({'name': name, 'version': dist.version, 'source': 'already-installed local Python distribution'})
        (root / 'local-dependencies.json').write_text(json.dumps(copied, indent=2), 'utf-8')
    if not skip_install and not local_dependencies:
        subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', *REQUIREMENTS], check=True)
        freeze = subprocess.check_output([str(python), '-m', 'pip', 'freeze'], text=True)
        (root / 'requirements-resolved.txt').write_text(freeze, encoding='utf-8')
    # Verify the actual narrowed router, not just a shallow package import.
    base = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(base))
    import threading
    import promotion_dramaclip
    with tempfile.TemporaryDirectory(prefix='manju-dra-probe-', dir=root) as probe_dir:
        with promotion_dramaclip.Sidecar({'root': str(root), 'python': str(python)}, Path(probe_dir), threading.Event()) as service:
            service.call('system.ping', timeout=15)
    marker = {'format': 2, 'pythonRelative': python.relative_to(root).as_posix(),
              'pythonSha256': promotion_dramaclip.file_hash(python),
              'serviceEntrySha256': promotion_dramaclip.file_hash(root / 'source/service/dramaclip/service_app.py'),
              'sidecarSha256': promotion_dramaclip.file_hash(base / 'tools/dramaclip_sidecar.py'),
              'commit': COMMIT, 'serviceImportVerified': True, 'rpcVerified': True, 'fusedMode': True,
              'dependencyProbe': 'pydantic + Manju narrow DramaClip router'}
    (root / 'runtime-ready.json').write_text(json.dumps(marker, indent=2), 'utf-8')
    print(json.dumps({'root': str(root), 'python': str(python), 'commit': COMMIT,
                      'modelsDownloaded': False}, ensure_ascii=False))


def _copy(root: Path, source: Path):
    dest = root / 'source'
    for name in ('service/dramaclip', 'resources/subtitle-presets', 'resources/fonts',
                 'resources/narration-styles', 'protocol'):
        src = source / name
        if src.is_dir():
            shutil.copytree(src, dest / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.exe'))
    for name in ('service/pyproject.toml', 'package.json', 'README.md', 'LICENSE', 'LICENSE.md'):
        src = source / name
        if src.is_file():
            target = dest / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
    hashes = {p.relative_to(dest).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in dest.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    manifest = {'repository': 'https://github.com/efarsoft/DramaClip', 'commit': COMMIT,
                'licenseDeclaredByUpstream': 'MIT', 'sourceSha256': hashes,
                'note': 'Source copied without modification. Manju integration lives outside source/.'}
    (root / 'source-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    (root / '.gitignore').write_text('*\n!.gitignore\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1] / 'engines/dramaclip')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--skip-install', action='store_true')
    parser.add_argument('--local-dependencies', action='store_true', help='Use locally installed pydantic only; no network, no new ML environment')
    args = parser.parse_args()
    prepare(args.root, args.source, args.skip_install, args.local_dependencies)
