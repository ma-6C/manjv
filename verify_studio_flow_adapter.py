"""Controlled publishing/recovery checks; no official browser or upload is run."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

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


def editor_fixture():
    adapter, _, flow, _ = fixture()
    row = {'projectId': 'p1', 'directory': str(BASE / 'controlled-draft'), 'name': 'source-draft'}
    adapter.s.JOBS['jy1'] = {'id': 'jy1', 'jianyingResults': [row]}
    flow['jianyingOptions'] = {}
    flow['status'] = 'running'
    flow['stages'].append({'key': 'jianying', 'ref': {'ids': ['jy1']}})
    adapter.s.STATE['studioFlows'] = {'flows': [flow]}
    imported = {'directory': str(BASE / 'controlled-import'), 'name': 'actual-imported-draft',
                'editorValidated': False}
    stage = {'key': 'editor_import', 'operationId': 'f1:editor_import', 'status': 'running'}
    return adapter, flow, stage, imported


def wait_handoff(adapter, flow, stage):
    deadline = time.monotonic() + 3
    while adapter.threads and time.monotonic() < deadline:
        time.sleep(.01)
    if adapter.threads:
        raise AssertionError('controlled editor worker did not finish')
    return adapter.poll(flow, stage)


def editor_checks():
    adapter, flow, stage, imported = editor_fixture()
    waiting = {'status': 'waiting_action', 'reason': 'editor_project', 'projectOpened': False,
               'timelineVerified': False, 'projectTitleVerified': False,
               'message': '请打开 actual-imported-draft 后重新检测'}
    verified = {'status': 'completed', 'projectOpened': True, 'timelineVerified': True,
                'projectTitleVerified': True, 'editorValidated': False,
                'message': '已定位本次工程的真实时间线'}
    with patch('jianying_projects.install_to_editor', return_value=imported) as install, \
         patch('jianying_automation.open_registered_project', return_value=waiting) as native:
        result = adapter.start(flow, stage, stage['operationId'])
        stage['ref'] = result['ref']
        result = wait_handoff(adapter, flow, stage)
        check('草稿复制完成而工程未打开时停在交接步骤',
              result['status'] == 'waiting_action' and result['reason'] == 'editor_project'
              and result['result']['imports'][0]['name'] == imported['name']
              and result['result']['editor']['projectOpened'] is False)
        for _ in range(6):
            adapter.poll(flow, stage)
        check('等待时轮询只读交接记录，不重复调用原生动作或复制',
              native.call_count == 1 and install.call_count == 1 and len(adapter.s.JOBS) == 1)
        native.return_value = verified
        result = adapter.resume(flow, stage, stage['operationId'])
        stage['ref'] = result['ref']
        result = wait_handoff(adapter, flow, stage)
        check('本人打开后显式重检可以完成同一交接任务',
              result['status'] == 'completed' and result['result']['editor']['projectOpened'] is True
              and result['reason'] == '' and len(adapter.s.STATE['studioFlowTasks']) == 1
              and adapter.s.STATE['studioFlowTasks'][0]['id'] == stage['operationId'])
        check('重新检测复用已导入副本，不重编码不重生成不重拷贝',
              native.call_count == 2 and install.call_count == 1 and len(adapter.s.JOBS) == 1
              and native.call_args.args[0]['directory'] == imported['directory'])
        for _ in range(4):
            adapter.poll(flow, stage)
        check('交接完成后轮询不重新启动原生操作', native.call_count == 2 and install.call_count == 1)

    # A misleading completed status, a launch, or a timeline alone is not
    # enough to finish this step without the exact project title as well.
    for missing in ('projectOpened', 'timelineVerified', 'projectTitleVerified'):
        adapter, flow, _, imported = editor_fixture()
        with patch('jianying_projects.install_to_editor', return_value=imported), \
             patch('jianying_automation.open_registered_project', return_value={**verified, missing: False, 'appLaunched': True}):
            result = adapter._editor(flow)
        check('缺少实际核验字段保持等待：'+missing,
              result['status'] == 'waiting_action' and result['reason'] == 'editor_project')

    adapter, flow, stage, imported = editor_fixture()
    with patch('jianying_projects.install_to_editor', return_value=imported) as install, \
         patch('jianying_automation.open_registered_project', side_effect=[RuntimeError('controlled native failure'), waiting, verified]) as native:
        result = adapter.start(flow, stage, stage['operationId'])
        stage['ref'] = result['ref']
        result = wait_handoff(adapter, flow, stage)
        check('原生打开失败保留已完成草稿副本',
              result['status'] == 'failed' and adapter.s.JOBS['jy1']['jianyingResults'][0]['editorImport'] == imported)
        for expected in ('waiting_action', 'completed'):
            result = adapter.resume(flow, stage, stage['operationId'])
            stage['ref'] = result['ref']
            result = wait_handoff(adapter, flow, stage)
            check('失败后恢复原交接并核对实际状态：'+expected, result['status'] == expected)
        check('失败后多次显式恢复仍复用唯一交接和草稿副本',
              len(adapter.s.STATE['studioFlowTasks']) == 1 and native.call_count == 3 and install.call_count == 1)


def export_and_browser_recovery_checks():
    adapter, workspace, flow, _ = fixture()
    stage = {'key': 'export', 'operationId': 'f1:export', 'status': 'queued', 'result': {}, 'ref': {}}
    workspace.fp = 'fp2'
    blocked = adapter.start(flow, stage, stage['operationId'])
    stage.update(blocked)
    check('导出派发前资料改动先等待核对，不创建资料包',
          blocked['status'] == 'waiting_action' and blocked['reason'] == 'materials' and not workspace.calls)
    for _ in range(3):
        adapter.last_poll.clear()
        result = adapter.poll(flow, stage)
        stage.update(result)
    check('资料改动后的普通轮询不会把空任务列表当作导出完成',
          result['status'] == 'waiting_action' and result['reason'] == 'materials' and not workspace.calls)
    resumed = adapter.resume(flow, stage, stage['operationId'])
    stage.update(resumed)
    adapter.last_poll.clear()
    completed = adapter.poll(flow, stage)
    check('本人继续后接受新资料版本并等待实际导出任务完成',
          resumed['status'] == 'running' and bool(resumed.get('ref', {}).get('ids'))
          and completed['status'] == 'completed' and bool(completed['result']['tasks'])
          and flow['stages'][1]['result']['fingerprints'] == {'p1': 'fp2'}
          and [c[0] for c in workspace.calls] == ['export'])
    check('缺失全部导出任务引用明确失败，不能完成空资料包',
          adapter._publish_tasks([])['status'] == 'failed')

    adapter, workspace, flow, _ = fixture()
    stage = {'key': 'export', 'operationId': 'f1:export', 'status': 'queued', 'result': {}, 'ref': {}}
    workspace.inspect = lambda pid: {'projectId': pid, 'ready': False, 'title': pid,
                                     'errors': ['封面已丢失'], 'fingerprint': 'missing-cover'}
    blocked = adapter.start(flow, stage, stage['operationId'])
    stage.update(blocked)
    adapter.last_poll.clear()
    polled = adapter.poll(flow, stage)
    check('导出时附件缺失在派发和后续轮询都保持资料门禁',
          blocked['status'] == polled['status'] == 'waiting_action'
          and polled['reason'] == 'materials' and not workspace.calls)

    adapter, workspace, flow, _ = fixture()
    old = task(workspace, 'export', state={'directory': 'old-version-packet'})
    stage = {'key': 'export', 'operationId': 'f1:export', 'status': 'running',
             'ref': {'ids': [old['id']]}, 'result': {}}
    workspace.fp = 'fp2'
    polled = adapter.poll(flow, stage)
    check('旧版本资料包即使已完成也不能越过新资料版本核对',
          polled['status'] == 'waiting_action' and polled['reason'] == 'materials' and not workspace.calls)

    adapter, workspace, flow, _ = fixture()
    flow['projectIds'].append('p2')
    flow['stages'][1]['result']['fingerprints']['p2'] = 'fp1'
    workspace.inspect = lambda pid: {'projectId': pid, 'ready': pid == 'p1', 'title': pid,
                                     'errors': [] if pid == 'p1' else ['第二部缺少封面'], 'fingerprint': 'fp1'}
    missing = adapter._material_version(flow)
    check('多剧资料缺项聚焦实际缺项剧目，避免一直显示第一部',
          missing['result']['projectId'] == 'p2' and missing['result']['missing'][0]['projectId'] == 'p2')
    workspace.inspect = lambda pid: {'projectId': pid, 'ready': True, 'title': pid,
                                     'errors': [], 'fingerprint': 'fp2' if pid == 'p2' else 'fp1'}
    changed = adapter._material_version(flow)
    check('多剧资料变更聚焦实际改动版本',
          changed['result']['projectId'] == 'p2' and changed['result']['changedProjectIds'] == ['p2'])

    for state in ('failed', 'interrupted'):
        adapter, workspace, flow, stage = fixture()
        task(workspace, 'open', status=state)
        results = [adapter._browser(flow, stage, stage['operationId']) for _ in range(3)]
        check('后台打开中断不在普通轮询重复打开：'+state,
              all(r['status'] == 'failed' for r in results) and not workspace.calls)
        resumed = adapter.resume(flow, stage, stage['operationId'])
        check('本人恢复只重试打开官方后台，不辅助填写：'+state,
              resumed['status'] == 'running' and [c[0] for c in workspace.calls] == ['open']
              and workspace.calls[0][2] is True)
        for _ in range(3):
            adapter._browser(flow, stage, stage['operationId'])
        check('恢复后的后续轮询复用打开结果并等待扫码：'+state,
              [c[0] for c in workspace.calls].count('open') == 1
              and not any(c[0] == 'assist' for c in workspace.calls))


def run():
    editor_checks()
    export_and_browser_recovery_checks()
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
