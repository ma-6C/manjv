"""Controlled publishing/recovery checks; no official browser or upload is run."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace

import publish_workflow
from studio_flow_adapter import Adapter

ROOT = Path(__file__).resolve().parent
BASE = Path(tempfile.mkdtemp(prefix='studio-flow-adapter-', dir=ROOT / 'tmp'))
checks = []
failures = []


def check(label, value):
    checks.append(label)
    if not value:
        failures.append(label)
    print(('PASS ' if value else 'FAIL ') + label, flush=True)


class Workspace:
    def __init__(self):
        self.tasks = []
        self.records = []
        self.calls = []
        self.fp = 'fp1'
        self.results = {}

    def public(self):
        return copy.deepcopy({'tasks': self.tasks, 'records': self.records})

    def browser(self, aid, action, pid, *, operation_id=None, retry=False):
        previous = next((t for t in self.tasks if t.get('operationId') == operation_id), None)
        if previous and not (retry and previous['status'] not in ('queued', 'running')):
            return {'taskId': previous['id'], 'reused': True}
        self.calls.append((action, pid, retry))
        if previous:
            self.tasks.remove(previous)
        task = {'id': str(len(self.calls)), 'operationId': operation_id, 'kind': 'browser_' + action,
                'status': 'completed', 'createdAt': time.time(), 'finishedAt': time.time(), 'projectId': pid,
                'result': self.results.get(action, {'browserOpen': True, 'loginState': 'login_required', 'formRecognized': False})}
        self.tasks.append(task)
        return {'taskId': task['id']}

    def inspect(self, pid):
        return {'projectId': pid, 'ready': True, 'title': pid, 'errors': [], 'fingerprint': self.fp}

    def export(self, pid, *, operation_id=None, retry=False):
        return self.browser('', 'export', pid, operation_id=operation_id, retry=retry)


def fixture():
    video = BASE / 'fixture.mp4'
    video.write_bytes(b'controlled-output-no-media-decoding')
    st = video.stat()
    p = {'id': 'p1', 'finalJob': 'j1', 'finalVideoPaths': [str(video)]}
    workspace = Workspace()
    state = {'studioFlowTasks': []}
    service = SimpleNamespace(LOCK=threading.RLock(), STATE=state, JOBS={},
                              get_project=lambda pid: p, publish_workspace=lambda: workspace,
                              save=lambda: None, ai=SimpleNamespace(redact=lambda text: text))
    adapter = Adapter(service)
    flow = {'id': 'f1', 'projectIds': ['p1'], 'options': {'accountId': 'a1'}, 'projectNames': {'p1': '样片'},
            'stages': [{'key': 'production', 'result': {'jobId': 'j1', 'videos': {'p1': [
                {'path': str(video), 'bytes': st.st_size, 'mtime': st.st_mtime_ns}]}}},
                       {'key': 'materials', 'result': {'fingerprints': {'p1': 'fp1'}}}]}
    stage = {'key': 'publish', 'operationId': 'f1:publish', 'status': 'running'}
    return adapter, workspace, flow, stage


def task(workspace, suffix, *, state=None, status='completed', age=0, pid='p1'):
    row = {'id': pid + ':' + suffix, 'operationId': 'f1:publish:' + pid + ':' + suffix, 'status': status,
           'kind': 'browser_' + suffix, 'projectId': pid, 'accountId': 'a1',
           'createdAt': time.time() - age, 'finishedAt': time.time() - age,
           'stage': suffix, 'result': state or {}}
    workspace.tasks.append(row)
    return row


def run():
    adapter, workspace, flow, stage = fixture()
    first = adapter._browser(flow, stage, stage['operationId'])
    check('首次发布准备只打开官方后台，不直接填表', first['status'] == 'running' and [c[0] for c in workspace.calls] == ['open'])
    for _ in range(3):
        adapter._browser(flow, stage, stage['operationId'])
    check('等待扫码时不重复创建打开或辅助填写任务', [c[0] for c in workspace.calls].count('open') == 1 and not any(c[0] == 'assist' for c in workspace.calls))

    adapter, workspace, flow, stage = fixture()
    task(workspace, 'open', state={'browserOpen': True, 'loginState': 'authenticated', 'formRecognized': True})
    ready = adapter._browser(flow, stage, stage['operationId'])
    check('只有真实识别到已登录表单才辅助填写', ready['status'] == 'running' and workspace.calls[0][0] == 'assist')
    task(workspace, 'assist', state={'browserOpen': True, 'state': 'awaiting_confirmation', 'submitted': False})
    waiting = adapter._browser(flow, stage, stage['operationId'])
    check('辅助填写后保留本人提交确认，不标记已发布', waiting['status'] == 'waiting_action' and waiting.get('reason') == 'submission' and waiting['result']['submitted'] is False)

    adapter, workspace, flow, stage = fixture()
    task(workspace, 'open', state={'browserOpen': True, 'loginState': 'authenticated', 'formRecognized': True})
    task(workspace, 'assist', state={'browserOpen': True, 'state': 'needs_login', 'loginState': 'login_required', 'submitted': False})
    expired = adapter._browser(flow, stage, stage['operationId'])
    check('填表前登录失效明确等待登录，不能宣称进入提交', expired.get('reason') in {'login', 'confirmation'} and expired.get('reason') != 'submission')
    task(workspace, 'assist', state={'browserOpen': True, 'state': 'needs_navigation', 'loginState': 'authenticated', 'submitted': False})
    # Replace same operation to match the unique persisted workspace slot.
    workspace.tasks = [t for i, t in enumerate(workspace.tasks) if t['id'] != 'p1:assist' or i == len(workspace.tasks)-1]
    moved = adapter._browser(flow, stage, stage['operationId'])
    check('填表页变化显示导航或明确核对等待，不标记待提交', moved.get('reason') in {'navigation', 'confirmation'} and moved.get('reason') != 'submission')

    adapter, workspace, flow, stage = fixture()
    task(workspace, 'open', state={'browserOpen': True, 'loginState': 'authenticated', 'formRecognized': True})
    task(workspace, 'assist', state={'browserOpen': True, 'state': 'needs_login', 'loginState': 'login_required', 'submitted': False})
    workspace.results['check'] = {'browserOpen': True, 'loginState': 'authenticated', 'formRecognized': True}
    workspace.results['assist'] = {'browserOpen': True, 'loginState': 'authenticated', 'state': 'awaiting_confirmation', 'submitted': False}
    resumed = adapter.resume(flow, stage, stage['operationId'])
    stage.setdefault('result', {}).update(resumed.get('result', {}))
    for _ in range(4):
        resumed = adapter._browser(flow, stage, stage['operationId'])
        stage.setdefault('result', {}).update(resumed.get('result', {}))
    check('本人恢复后复检登录并仅重试一次从未填表的操作',
          resumed.get('reason') == 'submission' and len([c for c in workspace.calls if c[0] == 'assist']) == 1)

    adapter, workspace, flow, stage = fixture()
    p1 = adapter.s.get_project('p1')
    adapter.s.get_project = lambda pid: dict(p1, id=pid)
    flow['projectIds'].append('p2')
    flow['stages'][0]['result']['videos']['p2'] = copy.deepcopy(flow['stages'][0]['result']['videos']['p1'])
    flow['stages'][1]['result']['fingerprints']['p2'] = 'fp1'
    workspace.records.append({'projectId': 'p1', 'accountId': 'a1', 'fingerprint': 'fp1', 'status': 'submitted'})
    for pid in ('p1', 'p2'):
        task(workspace, 'open', pid=pid, state={'browserOpen': True, 'loginState': 'authenticated', 'formRecognized': True})
        task(workspace, 'assist', pid=pid, state={'browserOpen': True, 'state': 'needs_login', 'loginState': 'login_required', 'submitted': False})
    workspace.results['check'] = {'browserOpen': True, 'loginState': 'authenticated', 'formRecognized': True}
    workspace.results['assist'] = {'browserOpen': True, 'loginState': 'authenticated', 'state': 'awaiting_confirmation', 'submitted': False}
    stage['result'] = {'projectId': 'p2'}
    resumed = adapter.resume(flow, stage, stage['operationId'])
    stage['result'].update(resumed.get('result', {}))
    for _ in range(4):
        resumed = adapter._browser(flow, stage, stage['operationId'])
        stage['result'].update(resumed.get('result', {}))
    check('多部剧恢复只核对当前未提交剧，历史失败不会抢占恢复',
          resumed.get('reason') == 'submission' and all(call[1] == 'p2' for call in workspace.calls))

    adapter, workspace, flow, stage = fixture()
    task(workspace, 'open', state={'browserOpen': True, 'loginState': 'authenticated'}, age=15)
    task(workspace, 'check', state={'browserOpen': False, 'loginState': 'unknown', 'state': 'needs_navigation'}, age=15)
    adapter._browser(flow, stage, stage['operationId'])
    check('重启后检测窗口不存在会重新打开，仍不重复辅助填写', any(c[0] == 'open' and c[2] for c in workspace.calls) and not any(c[0] == 'assist' for c in workspace.calls))
    workspace.results['check'] = {'browserOpen': True, 'loginState': 'login_required', 'formRecognized': False}
    adapter._browser(flow, stage, stage['operationId'])
    adapter._browser(flow, stage, stage['operationId'])
    check('重新打开后刷新只读检测，旧窗口关闭快照不触发重复打开',
          len([c for c in workspace.calls if c[0] == 'open']) == 1 and any(c[0] == 'check' for c in workspace.calls))

    adapter, workspace, flow, stage = fixture()
    workspace.records.append({'projectId': 'p1', 'accountId': 'a1', 'fingerprint': 'fp1', 'status': 'submitted'})
    completed = adapter._browser(flow, stage, stage['operationId'])
    check('相同资料的本人提交记录才完成工作流，仍不冒充平台审核', completed['status'] == 'completed' and completed['result']['platformVerified'] is False)

    adapter, workspace, flow, stage = fixture()
    workspace.fp = 'fp2'
    workspace.records.append({'projectId': 'p1', 'accountId': 'a1', 'fingerprint': 'fp2', 'status': 'submitted'})
    changed = adapter._browser(flow, stage, stage['operationId'])
    check('资料改动后的实际版本重新核对并匹配同版本本人记录',
          (changed['status'] == 'completed' and changed.get('result', {}).get('platformVerified') is False)
          or (changed['status'] == 'waiting_action' and changed.get('reason') in {'materials', 'confirmation'} and not workspace.calls))

    # Use the real Workspace._start retention/retry logic with harmless in-memory
    # export work. No filesystem copying, browser, upload, or server import.
    class RealWorkspace(publish_workflow.Workspace):
        def __init__(self):
            self.state = {'publishWorkspace': {'tasks': [], 'settings': {}, 'plans': {}, 'browser': {}, 'records': []}}
            self.lock = threading.RLock(); self.save = lambda: None
            self._stop = threading.Event(); self._threads = set(); self.executed = []
        def export(self, pid, *, operation_id=None, retry=False):
            def work(row):
                self.executed.append(pid)
                return {'directory': 'controlled-only'}
            return self._start('export', pid, '', work, operation_id=operation_id, retry=retry)
        def inspect(self, pid):
            return {'projectId': pid, 'ready': True, 'title': pid, 'errors': [], 'fingerprint': 'fp1'}

    adapter, _, flow, _ = fixture()
    real = RealWorkspace()
    real.value['tasks'].append({'id': 'old-export', 'kind': 'export', 'projectId': 'p1', 'accountId': '',
                               'operationId': 'f1:export:p1', 'status': 'completed', 'result': {'directory': 'already-done'}})
    adapter.s.publish_workspace = lambda: real
    result = adapter.resume(flow, {'key': 'export'}, 'f1:export')
    end = time.monotonic() + 2
    while real._threads and time.monotonic() < end:
        time.sleep(.01)
    check('恢复导出复用已完成资料包，不删除原任务重新复制', not real.executed and result['ref']['ids'] == ['old-export'])

    report = {'passed': len(checks)-len(failures), 'checks': checks, 'failures': failures,
              'controlledAdapter': True, 'officialBrowserOpened': False, 'platformSubmitted': False}
    (ROOT / 'tmp/studio-flow-adapter-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'passed': report['passed'], 'failed': len(failures), 'failures': failures}, ensure_ascii=False))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    run()
