"""Persistent orchestration for the local production-to-publishing workflow.

Adapters own real work. This manager only advances when an adapter reports an
actual result; a browser opening is never converted into a published result.
"""
from __future__ import annotations

import copy
import json
import re
import threading
import time
import uuid


STAGES = (
    ('production', '自动制作', 'progress'),
    ('review', '检查成品', 'progress'),
    ('jianying', '生成剪映工程', 'tracks'),
    ('editor_import', '交接到剪映', 'tracks'),
    ('evidence', '保存真实工程截图', 'tracks'),
    ('materials', '核对发布资料', 'publish'),
    ('export', '导出发布资料包', 'publish'),
    ('publish', '发布准备与确认', 'publish'),
)
TERMINAL = {'completed', 'cancelled'}
STAGE_DONE = {'completed', 'skipped'}
SENSITIVE = re.compile(r'password|passwd|cookie|secret|credential|api.?key|access.?token|refresh.?token|authorization', re.I)


def clean(value, depth=0):
    """Keep JSON state and public output free of credential fields/runtime objects."""
    if depth > 20:
        raise ValueError('流程数据嵌套过深')
    if isinstance(value, dict):
        return {str(k): clean(v, depth + 1) for k, v in value.items()
                if not SENSITIVE.search(str(k))}
    if isinstance(value, (list, tuple)):
        return [clean(v, depth + 1) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        # Disallow NaN/Infinity, which cannot round-trip as portable JSON.
        json.dumps(value, allow_nan=False)
        return value
    raise ValueError('流程数据必须是可保存的 JSON 数据')


class Manager:
    def __init__(self, state, lock, save, callbacks):
        self.state, self.lock, self.save, self.callbacks = state, lock, save, callbacks
        self._tick_lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._closed = False
        with lock:
            value = state.setdefault('studioFlows', {'flows': [], 'activeFlowId': ''})
            # Accommodate an early local list-shaped state without discarding it.
            if isinstance(value, list):
                value = state['studioFlows'] = {'flows': value, 'activeFlowId': ''}
            value.setdefault('flows', [])
            value.setdefault('activeFlowId', '')
            changed = False
            for flow in value['flows']:
                stage = self._stage(flow)
                if flow.get('status') == 'running' and stage:
                    stage.update(status='waiting_action', reason='interrupted',
                                 message='上次运行已中断，恢复后先核对原任务，不会重复创建')
                    flow.update(status='waiting_action', reason='interrupted', message=stage['message'])
                    self._transition(flow)
                    changed = True
            if changed:
                save()

    @property
    def value(self):
        return self.state['studioFlows']

    def _callback(self, name):
        return self.callbacks.get(name) if isinstance(self.callbacks, dict) else getattr(self.callbacks, name, None)

    def _find(self, flow_id):
        flow = next((f for f in self.value['flows'] if f['id'] == flow_id), None)
        if not flow:
            raise ValueError('没有找到这条工作流程')
        return flow

    @staticmethod
    def _stage(flow):
        return next((s for s in flow.get('stages', []) if s['key'] == flow.get('currentStage')), None)

    @staticmethod
    def _transition(flow):
        flow['sequence'] = int(flow.get('sequence', 0)) + 1
        flow['routeVersion'] = flow['sequence']
        flow['updatedAt'] = time.time()

    @staticmethod
    def _target(stage):
        """The currently actionable drama, independent of progress telemetry."""
        result = stage.get('result') or {}
        if result.get('projectId'):
            return result['projectId']
        missing = result.get('missingProjectIds') or []
        if missing:
            return missing[0]
        rows = result.get('missing') or []
        return rows[0].get('projectId', '') if rows and isinstance(rows[0], dict) else ''

    def _advance(self, flow):
        stage = next((s for s in flow['stages'] if s['status'] not in STAGE_DONE), None)
        if stage is None:
            if flow['status'] != 'completed':
                flow.update(status='completed', currentStage='', reason='', progress=100,
                            message='所选流程已完成', completedAt=time.time())
                self._transition(flow)
            return
        if flow.get('currentStage') != stage['key']:
            flow.update(currentStage=stage['key'], route=stage['route'], status='running',
                        reason='', message=stage.get('message') or stage['label'], progress=0)
            self._transition(flow)

    def public(self):
        with self.lock:
            value = copy.deepcopy(self.value)
        value['flows'] = [self._public_flow(flow) for flow in value['flows']]
        return clean(value)

    @staticmethod
    def _public_flow(flow):
        flow = copy.deepcopy(flow)
        flow.pop('config', None)
        flow.pop('sourceSnapshot', None)
        flow.pop('prepared', None)
        for stage in flow.get('stages', []):
            stage.pop('resumeData', None)
        return clean(flow)

    def start(self, body):
        if self._closed:
            raise ValueError('流程服务正在关闭')
        if not isinstance(body, dict):
            raise ValueError('流程参数无效')
        prepare = self._callback('prepare')
        if not prepare:
            raise ValueError('流程适配器尚未就绪')
        prepared = clean(copy.deepcopy(prepare(copy.deepcopy(body))))
        ids = prepared.get('projectIds') or prepared.get('ids') or []
        if not isinstance(ids, list) or not ids or any(not isinstance(x, str) for x in ids):
            raise ValueError('请先选择需要处理的剧目和视频')
        ids = list(dict.fromkeys(ids))
        options = {'withJianying': True, 'withEvidence': True, 'withExport': True,
                   'withPublish': False, 'reviewRequired': False, 'accountId': ''}
        options.update(prepared.get('options') or {})
        for key in ('withJianying', 'withEvidence', 'withExport', 'withPublish', 'reviewRequired'):
            if type(options[key]) is not bool:
                raise ValueError('流程开关必须为布尔值')
        stages = []
        for key, label, route in STAGES:
            enabled = (key == 'production' or
                       key == 'review' and options['reviewRequired'] or
                       key in ('jianying', 'editor_import') and options['withJianying'] or
                       key == 'evidence' and options['withJianying'] and options['withEvidence'] or
                       key == 'materials' and (options['withExport'] or options['withPublish']) or
                       key == 'export' and options['withExport'] or
                       key == 'publish' and options['withPublish'])
            stages.append({'key': key, 'label': label, 'route': route,
                           'status': 'queued' if enabled else 'skipped',
                           'message': '' if enabled else '本次未选择', 'result': {}, 'ref': {}})
        now = time.time()
        flow = dict(prepared, id=uuid.uuid4().hex[:16], projectIds=ids, options=options,
                    stages=stages, status='running', currentStage='', route='progress',
                    sequence=0, createdAt=now, updatedAt=now, reason='', message='准备开始')
        with self._tick_lock:
            with self.lock:
                for existing in self.value['flows']:
                    if existing.get('status') not in TERMINAL and set(ids).intersection(existing.get('projectIds', [])):
                        raise ValueError('所选剧目已有未结束的工作流程，请先恢复或取消原流程')
                self.value['flows'].append(flow)
                self.value['activeFlowId'] = flow['id']
                self._advance(flow)
                self.save()
            self.tick()
        with self.lock:
            return self._public_flow(flow)

    def _apply(self, flow, stage, response):
        if not isinstance(response, dict):
            raise ValueError('流程步骤没有返回有效状态')
        response = clean(response)
        status = response.get('status', 'running')
        if status == 'waiting_confirmation':
            status = 'waiting_action'
            response.setdefault('reason', 'confirmation')
        if status not in {'running', 'completed', 'skipped', 'waiting_action', 'failed'}:
            raise ValueError('流程步骤返回了不支持的状态')
        old = (stage.get('status'), flow.get('route'), stage.get('reason', ''), self._target(stage))
        stage.update(status=status, message=str(response.get('message', stage.get('message') or stage['label']))[:4000],
                     reason=str(response.get('reason', ''))[:100], updatedAt=time.time())
        if 'ref' in response:
            if not isinstance(response['ref'], dict):
                raise ValueError('流程任务引用无效')
            stage['ref'] = response['ref']
        if 'result' in response:
            if not isinstance(response['result'], dict):
                raise ValueError('流程步骤结果无效')
            stage.setdefault('result', {}).update(response['result'])
        if 'progress' in response:
            progress = response['progress']
            if isinstance(progress, (int, float)) and not isinstance(progress, bool):
                stage['progress'] = max(0, min(100, progress))
        route = response.get('route') or stage['route']
        if route not in {'studio', 'progress', 'tracks', 'publish', 'review', 'subtitle', 'sources'}:
            route = stage['route']
        flow.update(status='running' if status in STAGE_DONE else status,
                    route=route, message=stage['message'], reason=stage['reason'],
                    progress=stage.get('progress', 0), updatedAt=time.time())
        if status in STAGE_DONE:
            stage['completedAt'] = time.time()
            stage['progress'] = 100
            self._advance(flow)
        elif old != (status, flow['route'], stage.get('reason', ''), self._target(stage)):
            self._transition(flow)

    def _run_callback(self, flow, stage, method):
        callback = self._callback(method)
        if callback is None:
            return {'status': 'waiting_action', 'reason': 'adapter_unavailable', 'message': '当前步骤需要继续核对'}
        args = (copy.deepcopy(flow), copy.deepcopy(stage))
        if method in ('start', 'resume'):
            return callback(*args, stage['operationId'])
        return callback(*args)

    def _tick_flow(self, flow_id):
        with self.lock:
            flow = self._find(flow_id)
            if flow['status'] in TERMINAL | {'paused', 'failed'}:
                return
            stage = self._stage(flow)
            if not stage:
                self._advance(flow)
                self.save()
                return
            if stage.get('reason') in {'interrupted', 'confirmation', 'review'}:
                return
            method = 'start' if stage['status'] == 'queued' else 'poll'
            if method == 'start':
                stage.setdefault('operationId', flow['id'] + ':' + stage['key'])
                stage.update(status='dispatching', startedAt=time.time())
                # Persist the intent before calling anything with side effects.
                try:
                    self.save()
                except Exception:
                    # No callback ran, so retrying the same saved intent later
                    # is safe. Do not poll a job which was never dispatched.
                    stage['status'] = 'queued'
                    raise
        try:
            response = self._run_callback(flow, stage, method)
            with self.lock:
                self._apply(flow, stage, response)
                self.save()
        except Exception as exc:
            with self.lock:
                stage.update(status='failed', reason='error', message=str(exc)[:4000])
                flow.update(status='failed', reason='error', message=stage['message'])
                self._transition(flow)
                self.save()

    def tick(self):
        if self._closed or not self._tick_lock.acquire(blocking=False):
            return
        try:
            with self.lock:
                ids = [f['id'] for f in self.value['flows'] if f.get('status') not in TERMINAL]
            for flow_id in ids:
                if self._stop.is_set():
                    break
                self._tick_flow(flow_id)
        finally:
            self._tick_lock.release()

    def control(self, flow_id, action, body=None):
        if self._closed:
            raise ValueError('流程服务正在关闭')
        if action not in {'pause', 'resume', 'continue', 'cancel', 'activate'}:
            raise ValueError('流程操作无效')
        body = clean(copy.deepcopy(body or {}))
        with self._tick_lock:
            with self.lock:
                flow = self._find(flow_id)
                stage = self._stage(flow)
                if action == 'activate':
                    self.value['activeFlowId'] = flow_id
                    self.save()
                    return self._public_flow(flow)
                if flow['status'] in TERMINAL:
                    raise ValueError('这条流程已经结束')
            if action in {'pause', 'cancel'}:
                with self.lock:
                    before = flow['status']
                    if action == 'pause' and before == 'paused':
                        return self._public_flow(flow)
                    snapshots = (copy.deepcopy(flow), copy.deepcopy(stage))
                control = self._callback('control')
                if control and stage and stage.get('operationId'):
                    # Adapters run outside the application state lock, so a
                    # native-app handoff never blocks unrelated status reads.
                    control(*snapshots, action)
                with self.lock:
                    if action == 'pause':
                        flow['beforePause'] = before
                        flow.update(status='paused', message='流程已暂停，已完成步骤会保留')
                    else:
                        flow.update(status='cancelled', message='流程已停止，已完成的文件会保留', completedAt=time.time())
                        if stage and stage['status'] not in STAGE_DONE:
                            stage['status'] = 'cancelled'
                    self._transition(flow)
                    self.save()
                    return self._public_flow(flow)
            with self.lock:
                if flow['status'] == 'running':
                    return self._public_flow(flow)
                if not stage:
                    self._advance(flow)
                    self.save()
                    return self._public_flow(flow)
                stage['resumeData'] = body
                needs_resume = False
                if stage['status'] == 'queued':
                    flow.update(status='running', reason='', message=stage['label'])
                    self._transition(flow)
                    self.save()
                else:
                    # Never blindly dispatch again after interruption/failure.
                    stage.setdefault('operationId', flow['id'] + ':' + stage['key'])
                    resume = self._callback('resume')
                    if resume is None:
                        return self._public_flow(flow)
                    stage['status'] = 'dispatching'
                    # An asynchronous resume callback may launch a worker
                    # immediately. Publish the accepted running state first so
                    # that worker does not mistake this resume for a still-
                    # paused flow and abort its own handoff.
                    flow.update(status='running', reason='', message='正在恢复：' + stage['label'])
                    self._transition(flow)
                    self.save()
                    needs_resume = True
            if needs_resume:
                try:
                    response = self._run_callback(flow, stage, 'resume')
                    with self.lock:
                        self._apply(flow, stage, response)
                        self.save()
                except Exception as exc:
                    with self.lock:
                        stage.update(status='failed', reason='error', message=str(exc)[:4000])
                        flow.update(status='failed', reason='error', message=stage['message'])
                        self._transition(flow)
                        self.save()
            self.tick()
            with self.lock:
                return self._public_flow(flow)

    def start_background(self, interval=.5):
        if self._closed:
            raise ValueError('流程服务已关闭')
        if self._thread and self._thread.is_alive():
            return
        interval = max(.05, min(60, float(interval)))
        def work():
            while not self._stop.wait(interval):
                try:
                    self.tick()
                except Exception:
                    # Persistence failures leave the persisted dispatch intent in
                    # place; the thread remains available for a later retry.
                    continue
        self._thread = threading.Thread(target=work, name='studio-flow', daemon=True)
        self._thread.start()

    def shutdown(self):
        self._stop.set()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        self._closed = True
