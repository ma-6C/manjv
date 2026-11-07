"""Exercise removal with legacy records, real media/files and the real HTTP API.

--serve leaves the isolated fixture available for the Edge regression script.
No customer data, native editor, external provider or installer is used.
"""
from pathlib import Path
from unittest.mock import patch
import copy
import http.cookiejar
import json
import os
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent
BASE = Path(tempfile.mkdtemp(prefix='studio-removed-', dir=ROOT / 'tmp'))
DATA = BASE / 'data'
DATA.mkdir()
legacy = {'flows': [{'id': 'legacy-active', 'status': 'waiting_action',
                    'projectIds': ['fixture', 'remove-fixture'], 'currentStage': 'editor_import',
                    'stages': [{'key': 'editor_import', 'status': 'waiting_action', 'ref': {}}]}],
          'activeFlowId': 'legacy-active'}
legacy_tasks = [{'id': 'legacy-editor-task', 'status': 'waiting_action'}]
(DATA / 'state.json').write_text(json.dumps({'config': {}, 'projects': [],
    'studioFlows': legacy, 'studioFlowTasks': legacy_tasks}), 'utf-8')
os.environ['MANJU_DATA'] = str(DATA)
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
import server as s
import local_session

checks = []


def check(name, value):
    assert value, name
    checks.append(name)
    print('PASS ' + name, flush=True)


source = BASE / 'source'
source.mkdir()
video = source / '第0001集.mp4'
s.ff(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=15:duration=2',
      '-c:v', 'libx264', '-preset', 'ultrafast', '-an', str(video)])
original_video = video.read_bytes()
artifact = BASE / '原有成品.mp4'
artifact.write_bytes(original_video)
project = {'id': 'fixture', 'name': '模块移除核验剧集', 'originalName': '模块移除核验剧集',
           'intro': '已保存的剧集简介', 'videos': s.video_entries([video]),
           'source': str(source), 'cover': '', 'artifacts': [], 'rights': True,
           'status': '待处理', 'review': '待准备', 'notes': '保留客户备注'}
s.STATE['projects'] = [project, dict(copy.deepcopy(project), id='remove-fixture')]
s.STATE['config'].update(output=str(BASE / 'output'), gpu=False, subtitleMode='local')
s.save()
s.environment = lambda *a, **kw: {'gpu': {'ready': False, 'detail': 'isolated fixture'},
    'ffmpeg': bool(s.FFMPEG), 'fonts': True, 'cpu': 4, 'python': sys.version.split()[0]}
host = s.ThreadingHTTPServer(('127.0.0.1', 0), s.Handler)
host.session = local_session.Session()
url = 'http://127.0.0.1:' + str(host.server_address[1])
launch = url + '/launch/' + host.session.launch
thread = threading.Thread(target=host.serve_forever, daemon=True)
thread.start()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(path, body=None):
    headers = {'Content-Type': 'application/json', 'X-Local-Client': '1'}
    req = urllib.request.Request(url + '/api/' + path,
        data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with opener.open(req, timeout=15) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


try:
    opener.open(launch, timeout=15).close()
    before = copy.deepcopy(s.STATE)
    for _ in range(3):
        code, state = request('state')
        assert code == 200
        assert 'studioFlows' not in state and 'studioFlowTasks' not in state
    time.sleep(1.7)  # Past two ticks of the retired dispatcher's old interval.
    check('状态轮询不再派发旧流程或创建后台任务', not s.JOBS and s.STATE == before)
    check('保留磁盘上的流程历史但不再加载调度器',
          json.loads((DATA / 'state.json').read_text('utf-8'))['studioFlows'] == legacy
          and 'studio_flow' not in sys.modules and 'studio_flow_adapter' not in sys.modules)
    for path, body in [('studio-flows', None),
                       ('studio-flows/start', {'projectIds': ['fixture']}),
                       ('studio-flows/control', {'id': 'legacy-active', 'action': 'continue'})]:
        code, result = request(path, body)
        check('旧接口明确停用_' + path, code == 410 and '已移除' in result.get('error', ''))
    check('旧客户端请求没有生成新任务或改写历史', not s.JOBS and s.STATE == before)
    with patch.object(s, 'ensure_runner'):
        code, result = request('jobs', {'kind': 'subtitle', 'ids': ['fixture']})
        check('独立去字幕入口可对旧流程中的素材新建任务', code == 200 and result['id'] in s.JOBS)
        jid = result['id']
        request('jobs/control', {'id': jid, 'action': 'pause'})
        code, result = request('jobs/control', {'id': jid, 'action': 'resume'})
        check('独立任务可通过任务管理恢复', code == 200 and result['status'] == 'queued')
        request('jobs/control', {'id': jid, 'action': 'cancel'})
        code, result = request('jobs', {'kind': 'transcode', 'ids': ['remove-fixture']})
        check('旧流程记录不再锁住独立视频处理', code == 200 and result['id'] in s.JOBS)
        guard_id = result['id']
        code, result = request('remove', {'id': 'remove-fixture'})
        check('独立任务运行中的素材仍受移除保护', code == 400 and '任务运行中' in result['error'])
        request('jobs/control', {'id': guard_id, 'action': 'cancel'})
        code, result = request('remove', {'id': 'remove-fixture'})
        check('停止独立任务后可移除旧流程的素材记录', code == 200 and result['removed'])
    code, state = request('state')
    check('素材配置和备注保留', code == 200 and state['projects'] == [project]
          and state['config']['output'] == str(BASE / 'output'))
    check('已有素材与输出文件逐字节保留', video.read_bytes() == original_video
          and artifact.read_bytes() == original_video)
    saved = json.loads((DATA / 'state.json').read_text('utf-8'))
    check('保存其他功能时仍保留旧流程历史', saved['studioFlows'] == legacy
          and saved['studioFlowTasks'] == legacy_tasks)
    report = {'passed': len(checks), 'checks': checks, 'base': str(BASE),
              'scope': 'Source HTTP/backend, real media/files; job queue dispatch disabled during control tests; no installer.'}
    (BASE / 'studio-module-removed-backend.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    (ROOT / 'tmp/studio-removed-host.json').write_text(json.dumps({'base': str(BASE), 'url': url,
        'launch': launch, 'pid': os.getpid(), 'sourceOnly': True}), 'utf-8')
    print('STUDIO_REMOVED_OK ' + json.dumps({'passed': len(checks), 'base': str(BASE)}), flush=True)
    if '--serve' in sys.argv:
        threading.Event().wait()
finally:
    host.shutdown()
    host.server_close()
    s.shutdown_jobs()
