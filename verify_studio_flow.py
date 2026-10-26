"""Controlled adapter checks for orchestration; real media lives in adapter tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import threading
import time

import studio_flow


checks = []


def check(label, condition):
    assert condition, label
    checks.append(label)
    print('PASS ' + label, flush=True)


class Adapter:
    def __init__(self):
        self.calls = []
        self.tasks = {}
        self.finished = set()
        self.gates = set()
        self.block = None
        self.enter = threading.Event()
        self.prepared = None

    def prepare(self, body):
        self.prepared = {'projectIds': body.get('projectIds', ['p1']),
                         'sourceVideoPaths': ['one.mp4'],
                         'config': {'width': 1920, 'apiKey': 'never persist me'},
                         'options': body.get('options', {})}
        return self.prepared

    def start(self, flow, stage, operation):
        self.calls.append(('start', stage['key'], operation))
        if self.block:
            self.enter.set()
            self.block.wait(2)
        if stage['key'] == 'review':
            return {'status': 'waiting_action', 'reason': 'confirmation', 'message': '请确认成品'}
        if stage['key'] in ('materials', 'evidence', 'publish'):
            return {'status': 'waiting_action', 'reason': stage['key'], 'message': '请补充'}
        self.tasks.setdefault(operation, {'id': operation, 'kind': 'job'})
        return {'status': 'running', 'ref': self.tasks[operation], 'message': '实际任务运行中'}

    def poll(self, flow, stage):
        self.calls.append(('poll', stage['key'], stage['operationId']))
        if stage['key'] in self.finished or stage['key'] in self.gates:
            return {'status': 'completed', 'message': '实际任务完成',
                    'result': {'files': [stage['key'] + '.mp4']}}
        return {'status': stage['status'] if stage['status'] != 'dispatching' else 'running',
                'reason': stage.get('reason', ''), 'progress': 42}

    def control(self, flow, stage, action):
        self.calls.append((action, stage['key'], stage.get('operationId')))

    def resume(self, flow, stage, operation):
        self.calls.append(('resume', stage['key'], operation))
        if stage['key'] == 'review':
            return {'status': 'completed' if stage.get('resumeData', {}).get('confirmed') is True else 'waiting_action',
                    'reason': '' if stage.get('resumeData', {}).get('confirmed') is True else 'confirmation'}
        return self.poll(flow, stage)


def fixture(adapter=None):
    state = {}
    writes = []
    manager = studio_flow.Manager(state, threading.RLock(), lambda: writes.append(copy.deepcopy(state)), adapter or Adapter())
    return manager, state, writes


def advance(manager, count=30):
    for _ in range(count):
        manager.tick()


def run():
    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'projectIds': ['p1'], 'options': {'withJianying': False, 'withExport': False}})
    fid = flow['id']
    check('派发前保存稳定 operationId', any(w['studioFlows']['flows'][0]['stages'][0]['status'] == 'dispatching' for w in writes))
    op = state['studioFlows']['flows'][0]['stages'][0]['operationId']
    check('稳定操作标识可用于外部任务去重', op == fid + ':production')
    check('启动结果和公共状态不暴露冻结配置', 'config' not in flow and 'config' not in manager.public()['flows'][0])
    check('凭据字段从持久数据中移除', 'never persist me' not in json.dumps(state))
    adapter.prepared['config']['width'] = 5
    adapter.prepared['sourceVideoPaths'].append('mutated.mp4')
    check('选集与配置快照不受调用者后续修改', state['studioFlows']['flows'][0]['config']['width'] == 1920 and state['studioFlows']['flows'][0]['sourceVideoPaths'] == ['one.mp4'])
    seq = manager.public()['flows'][0]['sequence']
    advance(manager, 5)
    check('轮询只更新进度不重复派发或强制导航', len([c for c in adapter.calls if c[0] == 'start']) == 1 and manager.public()['flows'][0]['sequence'] == seq)
    pending = {'status': 'running', 'result': {'projectId': 'p1'}, 'progress': 10}
    original_poll = adapter.poll
    adapter.poll = lambda *_: copy.deepcopy(pending)
    manager.tick();target_sequence = manager.public()['flows'][0]['sequence']
    pending['progress'] = 33
    manager.tick()
    check('同一剧目进度更新保持导航序号不变', manager.public()['flows'][0]['sequence'] == target_sequence)
    pending['result']['projectId'] = 'p2'
    manager.tick()
    check('同一步骤切换下一部剧会通知界面跟随', manager.public()['flows'][0]['sequence'] == target_sequence + 1)
    pending.update(status='waiting_action', reason='evidence', result={'projectId': '', 'missingProjectIds': ['p1', 'p2']})
    manager.tick();target_sequence = manager.public()['flows'][0]['sequence']
    pending['result']['missingProjectIds'] = ['p2']
    manager.tick()
    check('补齐一部截图后聚焦下一部缺项，不重复跳向原剧目', manager.public()['flows'][0]['sequence'] == target_sequence + 1)
    adapter.poll = original_poll
    adapter.finished.add('production')
    advance(manager)
    done = manager.public()['flows'][0]
    check('未选模块跳过，实际完成后流程才完成', done['status'] == 'completed' and all(s['status'] in {'completed', 'skipped'} for s in done['stages']))

    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'reviewRequired': True, 'withJianying': False, 'withExport': True}})
    adapter.finished.add('production')
    advance(manager)
    check('人工确认单独等待，不被轮询伪造通过', manager.public()['flows'][0]['currentStage'] == 'review' and not any(c[:2] == ('poll', 'review') for c in adapter.calls))
    manager.control(flow['id'], 'continue', {'confirmed': True, 'apiKey': 'do not retain'})
    advance(manager)
    check('确认后进入资料检查，没有重跑制作', manager.public()['flows'][0]['currentStage'] == 'materials' and len([c for c in adapter.calls if c[:2] == ('start', 'production')]) == 1)
    adapter.gates.add('materials')
    advance(manager, 2)
    check('补齐资料可自动进入导出，无需重复点继续', manager.public()['flows'][0]['currentStage'] == 'export')
    check('恢复参数不向界面暴露，且剔除凭据', 'resumeData' not in manager.public()['flows'][0]['stages'][1] and 'do not retain' not in json.dumps(state))

    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'withJianying': False, 'withExport': False}})
    manager.control(flow['id'], 'pause')
    call_count = len(adapter.calls)
    advance(manager)
    check('暂停后不轮询或派发后续步骤', len(adapter.calls) == call_count and manager.public()['flows'][0]['status'] == 'paused')
    adapter.finished.add('production')
    manager.control(flow['id'], 'resume')
    advance(manager)
    check('恢复沿用原任务，已完成处理无需重做', manager.public()['flows'][0]['status'] == 'completed' and len([c for c in adapter.calls if c[0] == 'start']) == 1)

    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'withJianying': False, 'withExport': False}})
    manager.control(flow['id'], 'pause')
    observed = []
    original_resume = adapter.resume
    def observe_resume(*args):
        worker = threading.Thread(target=lambda: observed.append((
            state['studioFlows']['flows'][0]['status'], args[0]['status'],
            writes[-1]['studioFlows']['flows'][0]['status'])))
        worker.start();worker.join(1)
        return original_resume(*args)
    adapter.resume = observe_resume
    manager.control(flow['id'], 'resume')
    check('恢复前先发布运行状态，立即启动的交接线程不会误判暂停', observed == [('running', 'running', 'running')])

    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'withJianying': False, 'withExport': False}})
    saved = copy.deepcopy(state)
    before = len(adapter.calls)
    recovered = studio_flow.Manager(saved, threading.RLock(), lambda: None, adapter)
    advance(recovered)
    check('重启不盲目重派运行中任务', len(adapter.calls) == before and recovered.public()['flows'][0]['reason'] == 'interrupted')
    recovered.control(flow['id'], 'resume')
    check('重启恢复通过适配器核对原引用', any(c[0] == 'resume' for c in adapter.calls) and len([c for c in adapter.calls if c[0] == 'start']) == 1)
    recovered.control(flow['id'], 'cancel')
    advance(recovered)
    check('停止持久化，不再派发且保留任务引用', recovered.public()['flows'][0]['status'] == 'cancelled' and bool(recovered.public()['flows'][0]['stages'][0]['ref']))

    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'projectIds': ['p1']})
    rejected = False
    try:
        manager.start({'projectIds': ['p1', 'p2']})
    except ValueError:
        rejected = True
    check('同一剧目不能同时创建冲突流程', rejected and len(manager.public()['flows']) == 1)
    second = manager.start({'projectIds': ['p2']})
    check('不同剧目流程可保留且活动流程可切换', len(manager.public()['flows']) == 2 and manager.public()['activeFlowId'] == second['id'])
    manager.control(flow['id'], 'activate')
    check('激活仅选择流程，不重复创建任务', manager.public()['activeFlowId'] == flow['id'] and len([c for c in adapter.calls if c[0] == 'start']) == 2)

    adapter = Adapter()
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'withJianying': False, 'withExport': False}})
    adapter.block = threading.Event()
    # Polling, like starting, may be called from the background and an API tick.
    old_poll = adapter.poll
    def slow_poll(*args):
        adapter.enter.set()
        adapter.block.wait(2)
        return old_poll(*args)
    adapter.poll = slow_poll
    thread = threading.Thread(target=manager.tick)
    thread.start()
    assert adapter.enter.wait(1)
    manager.tick()
    adapter.block.set()
    thread.join(2)
    check('后台与接口并发 tick 不重复轮询同一步', len([c for c in adapter.calls if c[0] == 'poll']) == 1)
    manager.start_background(.05)
    time.sleep(.12)
    manager.shutdown()
    count = len(adapter.calls)
    time.sleep(.08)
    check('后台调度可独立运行并安全停止', len(adapter.calls) == count and not manager._thread.is_alive())

    adapter = Adapter()
    adapter.finished.update(key for key, _, _ in studio_flow.STAGES)
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'withPublish': True}})
    routes = []
    for _ in range(40):
        current = manager.public()['flows'][0]
        routes.append(current['route'])
        manager.tick()
    order = [c[1] for c in adapter.calls if c[0] == 'start']
    check('连续工作按实际完成结果依序交接全部已选步骤', order == ['production', 'jianying', 'editor_import', 'evidence', 'materials', 'export', 'publish'] and manager.public()['flows'][0]['status'] == 'completed')
    check('自动步骤提供进度、剪映、发布三个真实目标页面', set(routes) >= {'progress', 'tracks', 'publish'})

    adapter = Adapter()
    original_start = adapter.start
    def uncertain_start(*args):
        original_start(*args)
        raise RuntimeError('派发成功但返回结果中断')
    adapter.start = uncertain_start
    manager, state, writes = fixture(adapter)
    flow = manager.start({'options': {'withJianying': False, 'withExport': False}})
    check('派发结果不确定先失败，不循环创建新任务', flow['status'] == 'failed' and len(adapter.tasks) == 1)
    adapter.finished.add('production')
    manager.control(flow['id'], 'resume')
    check('不确定派发恢复仍核对同一 operationId', manager.public()['flows'][0]['status'] == 'completed' and len(adapter.tasks) == 1 and len([c for c in adapter.calls if c[0] == 'start']) == 1)

    adapter = Adapter()
    state = {}
    allow_save = [False]
    def guarded_save():
        if state.get('studioFlows', {}).get('flows') and state['studioFlows']['flows'][0]['stages'][0]['status'] == 'dispatching' and not allow_save[0]:
            raise OSError('controlled persistence unavailable')
    manager = studio_flow.Manager(state, threading.RLock(), guarded_save, adapter)
    try:
        manager.start({'options': {'withJianying': False, 'withExport': False}})
    except OSError:
        pass
    check('无法保存派发意图时不执行有副作用的适配器', not adapter.calls and state['studioFlows']['flows'][0]['stages'][0]['status'] == 'queued')
    allow_save[0] = True
    manager.tick()
    check('存储恢复后以原 operationId 正常派发一次', len([c for c in adapter.calls if c[0] == 'start']) == 1)
    report = {'passed': len(checks), 'checks': checks, 'adapter': 'controlled',
              'realMediaTested': False, 'platformSubmitTested': False}
    directory = Path(__file__).resolve().parent / 'tmp'
    directory.mkdir(exist_ok=True)
    (directory / 'studio-flow-engine-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'passed': len(checks), 'errors': []}, ensure_ascii=False))


if __name__ == '__main__':
    run()
