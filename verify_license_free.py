"""Fresh and historical local profiles can run jobs without device activation."""
from pathlib import Path
import argparse
import http.cookiejar
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument('--version', default='v0.10.13')
args = parser.parse_args()
BASE = Path(tempfile.mkdtemp(prefix='license-free-', dir=ROOT/'tmp'))
os.environ['MANJU_DATA'] = str(BASE/'data')
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT/'vendor')]
import server as s
import local_session

COMPILED = Path(s.__file__).suffix == '.pyd'
if COMPILED:
    s.PUBLIC = ROOT/'release'/args.version/'漫剧工坊/_internal/web'
checks = []
report = {'ok': False, 'version': args.version, 'compiled': COMPILED, 'base': str(BASE),
          'checks': checks, 'customerDataUsed': False, 'paidOrAccountCalls': False}
host = s.ThreadingHTTPServer(('127.0.0.1', 0), s.Handler)
host.session = local_session.Session()
thread = threading.Thread(target=host.serve_forever, daemon=True)
thread.start()
origin = 'http://127.0.0.1:'+str(host.server_address[1])
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS '+name, flush=True)


def request(path, body=None, opener=client):
    req = urllib.request.Request(origin+path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', 'X-Local-Client': '1'})
    try:
        with opener.open(req, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def api(path, body=None):
    status, data = request('/api/'+path, body)
    if status != 200:
        raise AssertionError(path+' returned '+str(status)+': '+data.decode('utf-8', 'replace'))
    return json.loads(data)


try:
    with patch.object(sys, 'frozen', True, create=True), patch.object(s.licensing, 'machine_code', side_effect=AssertionError('Device probing is unnecessary')):
        check('frozen_usage_does_not_require_activation', not s.licensing.required() and s.licensing.status(s.DATA)['valid'])
        check('usage_does_not_probe_machine_identity', 'machineCode' not in s.licensing.status(s.DATA))
    check('fresh_profile_has_no_license_files', not any(s.DATA.glob('license*')))
    check('local_session_still_required', request('/api/state', opener=urllib.request.build_opener())[0] == 403)
    code, page = request('/launch/'+host.session.launch)
    check('fresh_launch_opens_workbench', code == 200 and b'id="content"' in page and b'activation-form' not in page)
    status = api('license')
    check('compatibility_status_reports_direct_use', status['valid'] and status['required'] is False)
    check('no_device_or_expiry_fields_returned', not {'machineCode', 'expiresAt', 'licenseId'} & status.keys())
    check('state_accessible_without_activation', isinstance(api('state')['projects'], list))
    check('components_accessible_without_activation', 'active' in api('component'))
    code, old_page = request('/activation.html')
    check('old_activation_page_has_no_input_form', code == 200 and b'activation-form' not in old_page and b'url=/' in old_page)
    check('legacy_activation_endpoint_needs_no_token', api('license/activate', {})['required'] is False)
    check('compatibility_call_does_not_write_license', not any(s.DATA.glob('license*')))
    old_files = {'license.bin': b'old-unreadable-license', 'license-clock.bin': b'old-future-or-corrupt-clock'}
    for name, content in old_files.items():
        (s.DATA/name).write_bytes(content)
    check('old_unreadable_license_and_clock_do_not_block_state', isinstance(api('state')['projects'], list))
    check('old_files_do_not_change_direct_usage_status', api('license')['valid'])
    source = BASE/'source'
    source.mkdir()
    video = source/'01.mp4'
    s.ff(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15:duration=2', '-f', 'lavfi', '-i',
          'sine=frequency=440:duration=2', '-shortest', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(video)])
    original = s.sha256(video)
    project = api('scan', {'source': str(source)})['projects'][0]
    api('config', {'output': str(BASE/'output'), 'subtitleMode': 'local', 'gpu': False})
    job_id = api('jobs', {'kind': 'subtitle', 'ids': [project['id']]})['id']
    deadline = time.monotonic()+60
    while time.monotonic() < deadline:
        current = next(job for job in api('state')['jobs'] if job['id'] == job_id)
        if current['status'] in ('completed', 'failed', 'cancelled'):
            break
        time.sleep(.1)
    check('real_job_completes_without_activation', current['status'] == 'completed')
    artifacts = [item['path'] for item in s.get_project(project['id'])['artifacts'] if item.get('job') == job_id]
    check('real_job_saved_media', bool(artifacts))
    for path in artifacts:
        subprocess.run([s.FFMPEG, '-hide_banner', '-v', 'error', '-xerror', '-i', path,
                        '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', 'NUL'], check=True, timeout=30)
    check('output_fully_decodes_with_audio', all(s.probe(path)['audio'] for path in artifacts))
    check('original_media_unchanged', s.sha256(video) == original)
    check('old_license_files_unchanged', all((s.DATA/name).read_bytes() == content for name, content in old_files.items()))
    report.update(ok=True, jobId=job_id, outputs=artifacts, moduleOrigins={name: str(sys.modules[name].__file__) for name in ('server', 'licensing')})
finally:
    s.shutdown_jobs()
    host.shutdown()
    host.server_close()
    thread.join(3)
    target = BASE/'report.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    (ROOT/'tmp'/('license-free-compiled-report.json' if COMPILED else 'license-free-source-report.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps({'ok': report['ok'], 'passed': len(checks), 'report': str(target)}, ensure_ascii=True))
