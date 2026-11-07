"""Check a diagnostic installed EXE through its own authenticated loopback server.

This does not replace native UI acceptance. It uses only the fresh profile and
launch URL created by this run and never prints its temporary session token.
"""
from pathlib import Path
import argparse
import hashlib
import http.cookiejar
import json
import os
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--diagnostic', type=Path, required=True)
parser.add_argument('--version', required=True)
args = parser.parse_args()
diagnostic = json.loads(args.diagnostic.read_text('utf-8'))
BASE, EXE = Path(diagnostic['base']).resolve(), Path(diagnostic['exe']).resolve()
assert BASE.is_relative_to((ROOT / 'tmp').resolve()) and EXE.is_relative_to((ROOT / 'tmp').resolve())
scan = json.loads((ROOT / 'versions' / args.version / 'defender-scan.json').read_text('utf-8-sig'))
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
assert hashlib.sha256(EXE.read_bytes()).hexdigest() == scan['executableSha256']
history = BASE / 'data/desktop-profile/EBWebView/Default/History'
launch = None
history_deadline = time.monotonic() + 60
while launch is None and time.monotonic() < history_deadline:
    try:
        with sqlite3.connect(history.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
            urls = [row[0] for row in connection.execute('SELECT url FROM urls ORDER BY last_visit_time DESC')]
        launch = next((url for url in urls if urllib.parse.urlsplit(url).path.startswith('/launch/')
                       and ('appServicePort' not in diagnostic or urllib.parse.urlsplit(url).port == diagnostic['appServicePort'])), None)
    except sqlite3.Error:
        pass
    if launch is None:
        time.sleep(.25)
assert launch, 'The installed WebView did not commit its own launch URL within 60 seconds'
parts = urllib.parse.urlsplit(launch)
assert parts.scheme == 'http' and parts.hostname == '127.0.0.1'
if 'appServicePort' in diagnostic:
    assert parts.port == diagnostic['appServicePort'], 'Launch URL is not owned by the diagnosed installed EXE'
origin = 'http://' + parts.netloc
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
report = {'version': args.version, 'base': str(BASE), 'actualInstalledExecutable': str(EXE),
          'processId': diagnostic['pid'], 'checks': [], 'uiAcceptanceReplaced': False,
          'customerDataUsed': False, 'paidOrAccountCalls': False}


def check(name, value=True):
    assert value, name
    report['checks'].append(name)
    print('PASS ' + name, flush=True)


def api(route, body=None):
    request = urllib.request.Request(origin + '/api/' + route,
        data=json.dumps(body).encode('utf-8') if body is not None else None,
        headers={'Content-Type': 'application/json', 'X-Local-Client': '1'})
    with opener.open(request, timeout=240) as response:
        return json.load(response)


try:
    with opener.open(launch, timeout=20) as response:
        landing = response.read()
    license = api('license')
    license_free = tuple(map(int, args.version.removeprefix('v').split('.'))) >= (0, 10, 13)
    if license_free:
        license_files = [BASE / 'data' / name for name in ('license.bin', 'license-clock.bin')]
        check('fresh_profile_has_no_license_files', not any(path.exists() for path in license_files))
        check('actual_exe_opens_workbench_without_activation', b'id="content"' in landing and b'activation-form' not in landing)
        check('actual_exe_reports_no_activation_required', license['valid'] and not license['required'])
        check('actual_exe_omits_machine_and_expiry_fields', 'machineCode' not in license and 'expiresAt' not in license)
        check('actual_exe_state_accessible_without_license', isinstance(api('state')['projects'], list))
        report.update(noActivationRequired=True, activationCodeIssued=False)
    else:
        check('actual_exe_serves_activation_page', b'activation-form' in landing)
        check('actual_exe_requires_signed_activation', license['required'] and not license['valid'])
        token = BASE / 'temporary-test-license.txt'
        subprocess.run([str(ROOT / '授权管理/当前签发工具-v2/授权签发工具.exe'), '--issue',
                        license['machineCode'], args.version + '独立HTTP验收', '1', str(token)],
                       check=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        check('actual_exe_accepts_temporary_signed_license', api('license/activate', {'token': token.read_text('utf-8-sig').strip()})['valid'])
        with opener.open(origin + '/', timeout=20) as response:
            check('actual_exe_serves_workbench_after_activation', b'id="content"' in response.read())
    runtime = api('promotion/engines')['dramaclip']
    check('installed_portable_planner_is_ready', runtime['ready'] and runtime['runtimeReady'])
    check('installed_planner_uses_shipped_directory', Path(runtime['root']).resolve() == EXE.parent / 'engines/dramaclip')
    report['promotionRuntime'] = runtime
    opened = api('xiaovmiao/open', {})
    check('actual_exe_launches_bundled_xiaovmiao', opened['launchRequested'])
    companion = api('xiaovmiao')
    check('bundled_xiaovmiao_stays_running', companion['processRunning'])
    report['xiaovmiao'] = companion
    source = BASE / '本机合成素材'; source.mkdir()
    video = source / '第001集.mp4'
    ffmpeg = next((EXE.parent / '_internal/imageio_ffmpeg/binaries').glob('*.exe'))
    subprocess.run([str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i',
        'testsrc2=size=320x180:rate=15:duration=2', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
        '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(video)], check=True, timeout=20)
    original = hashlib.sha256(video.read_bytes()).hexdigest()
    api('tracks/import', {'paths': [str(video)]})
    output = BASE / '本机验收成片'
    api('config', {'output': str(output), 'subtitleMode': 'local', 'gpu': False})
    state = api('state'); project = next(p for p in state['projects'] if any(v['path'] == str(video) for v in p['videos']))
    job = api('jobs', {'kind': 'subtitle', 'ids': [project['id']],
                      'sourceVideoPaths': {project['id']: [str(video)]}})
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        state = api('state'); current = next(item for item in state['jobs'] if item['id'] == job['id'])
        if current['status'] in ('completed', 'failed', 'cancelled'):
            break
        time.sleep(0.5)
    check('actual_installed_video_task_completes', current['status'] == 'completed')
    artifacts = [a['path'] for p in state['projects'] for a in p.get('artifacts', [])
                 if a.get('job') == job['id'] and a['path'].endswith('.mp4')]
    check('actual_task_uses_selected_output_directory', artifacts and all(Path(p).is_relative_to(output) for p in artifacts))
    for path in artifacts:
        subprocess.run([str(ffmpeg), '-v', 'error', '-i', path, '-map', '0:v:0', '-map', '0:a:0?', '-f', 'null', '-'], check=True, timeout=30)
    check('installed_output_decodes_completely')
    check('synthetic_original_remains_unchanged', original == hashlib.sha256(video.read_bytes()).hexdigest())
    if license_free:
        check('task_finishes_without_creating_license_files', not any(path.exists() for path in license_files))
    report.update(ok=True, jobId=job['id'], outputs=artifacts)
finally:
    (BASE / 'installed-http-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    (ROOT / 'versions' / args.version / 'installed-http-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print('INSTALLED_EXE_HTTP_OK', len(report['checks']))
