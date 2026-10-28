"""Apply the pinned playback compatibility sources and rebuild the Windows core."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = 'https://github.com/limbia/guoapp/commit/5fee5b4e93893cfb75ed0df9e1cbb387b334172d'
VERSION = '0.2.67+74'
SOURCES = ('provider_hongguo_multi_media.go', 'provider_hongguo_pure_sign.go')


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / '参考' / 'guoapp')
    parser.add_argument('--deploy', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    native = source / 'native' / 'core'
    media = native / 'provider_hongguo_native_media.go'
    if not media.is_file() or not (source / 'scripts' / 'build_native.py').is_file():
        raise ValueError('请指定完整的 guoapp 源码目录')
    text = media.read_text('utf-8')
    text, replaced = re.subn(
        r'func \(downloader \*Downloader\) resolveHongguoAppMedia\([^\n]+\n.*?\n}\n\n',
        '', text, count=1, flags=re.S,
    )
    if replaced:
        text = text.replace('\n\t"net/http"', '')
    elif not (native / SOURCES[0]).is_file():
        raise ValueError('未找到预期的旧播放入口，请先核对源码版本')
    if 'context.' not in text:
        text = text.replace('\n\t"context"', '')
    media.write_text(text, 'utf-8')
    for name in SOURCES:
        shutil.copyfile(ROOT / 'tools' / 'guoapp_compat' / name, native / name)
    pubspec = source / 'pubspec.yaml'
    text = pubspec.read_text('utf-8')
    if re.search(r'^version: 0\.2\.66\+73\s*$', text, flags=re.M):
        pubspec.write_text(re.sub(r'^version: 0\.2\.66\+73\s*$', 'version: ' + VERSION,
                                 text, count=1, flags=re.M), 'utf-8')
    readme = source / 'README.md'
    text = readme.read_text('utf-8')
    if '2026-10-28 播放接口修订' not in text:
        note = ('2026-10-28 播放接口修订：移植 [' + UPSTREAM.rsplit('/', 1)[-1][:8]
                + '](' + UPSTREAM + ') 的 multi_video_model/v1 请求与响应适配。'
                '保留已有画质候选、分段传输和断点续传；修正请求时间戳一致性与随机 ID 生成，'
                '限制响应体和片源域名，保留直接播放模型的兼容。仅构建 Windows 原生 DLL，'
                '未执行测试、真实下载或多平台验证，作为未验收开发修订。\n\n')
        text = text.replace('**0.2.66+73**', '**' + VERSION + '**')
        position = text.find('2026-10-22至23日下载调度修订')
        if position < 0:
            raise ValueError('未找到本地兼容版本说明的位置')
        readme.write_text(text[:position] + note + text[position:], 'utf-8')
    environment = os.environ.copy()
    compiler = ROOT / '参考' / 'tools' / 'mingw64' / 'bin'
    environment['PATH'] = str(compiler) + os.pathsep + environment.get('PATH', '')
    environment.setdefault('GOCACHE', str(ROOT / '参考' / 'tools' / 'go-cache'))
    environment.setdefault('GOMODCACHE', str(ROOT / '参考' / 'tools' / 'go-mod'))
    gofmt = shutil.which('gofmt', path=environment['PATH'])
    if not gofmt:
        raise ValueError('未找到 Go 工具链')
    subprocess.run([gofmt, '-w', str(media), *(str(native / name) for name in SOURCES)],
                   check=True, env=environment)
    subprocess.run([sys.executable, 'scripts/build_native.py', '--platform', 'windows'],
                   cwd=source, check=True, env=environment)
    built = source / 'windows' / 'runner' / 'duanju_core.dll'
    record = {'createdAt': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'version': VERSION,
              'upstreamPatch': UPSTREAM, 'sha256': sha256(built),
              'sourceSha256': {name: sha256(native / name) for name in (*SOURCES, media.name)},
              'testsRun': False, 'liveDownloadVerified': False, 'deployed': False}
    output = ROOT / 'tmp' / 'hongguo-core-build-20261028.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    if args.deploy:
        target = ROOT / 'engines' / 'guoapp-core'
        manifest_path = target / 'manifest.json'
        manifest = json.loads(manifest_path.read_text('utf-8'))
        backup = ROOT / 'tmp' / 'hongguo-core-backups' / sha256(target / 'duanju_core.dll')
        backup.mkdir(parents=True, exist_ok=True)
        for name in ('duanju_core.dll', 'manifest.json'):
            if not (backup / name).exists():
                shutil.copy2(target / name, backup / name)
        temporary = target / 'duanju_core.dll.new'
        shutil.copy2(built, temporary)
        temporary.replace(target / 'duanju_core.dll')
        manifest.update(version=VERSION + '-manju.1', sha256=record['sha256'],
                        playbackCompatibilityPatch=UPSTREAM,
                        playbackRequest='multi_video_model/v1',
                        playbackVerification='build-only; live download not verified')
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', 'utf-8', newline='\n')
        record['deployed'] = True
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    main()
