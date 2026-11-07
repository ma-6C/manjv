"""Fused local promotion engine: Manju ASR/encoding + pinned DramaClip planning.

No customer key is sent to the sidecar. Its authenticated loopback HTTP bridge
calls the application's existing provider router and exists for this job only.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import secrets
import socket
import subprocess
import sys
import threading
import time

COMMIT = '3562664e0d7f00dc4a5ff5784337751c510925a2'
BASE = Path(__file__).resolve().parent
APP_HOME = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else BASE


def file_hash(path):
    try:
        with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
    except OSError: return ''


def locations(options=None):
    options = options or {}
    root = Path(options.get('root') or APP_HOME / 'engines/dramaclip').resolve()
    source = next((p for p in (root / 'source/service', root / 'service', root)
                   if (p / 'dramaclip/service_app.py').is_file()), root / 'source/service')
    python = Path(options.get('python') or root / ('runtime/Scripts/python.exe' if os.name == 'nt' else 'runtime/bin/python')).resolve()
    return root, source, python


def status(options=None):
    """Fast read-only readiness; preparation writes the successful import marker."""
    root, source, python = locations(options)
    source_ready = (source / 'dramaclip/service_app.py').is_file()
    marker = {}
    try:
        marker = json.loads((root / 'runtime-ready.json').read_text('utf-8'))
    except (OSError, ValueError):
        pass
    expected_python = (root / str(marker.get('pythonRelative', ''))).resolve()
    runtime_ready = bool(python.is_file() and marker.get('format') == 2 and
                         marker.get('serviceImportVerified') and marker.get('rpcVerified') and
                         expected_python == python and marker.get('pythonSha256') == file_hash(python) and
                         marker.get('sidecarSha256') == file_hash(BASE / 'tools/dramaclip_sidecar.py') and
                         marker.get('serviceEntrySha256') == file_hash(source / 'dramaclip/service_app.py') and
                         marker.get('commit') == COMMIT)
    model = APP_HOME / 'engines/jianying-ai/models/faster-whisper/model.bin'
    asr_ready = model.is_file() and any((APP_HOME / p).is_file() for p in
        ('engines/jianying-ai/runtime/Scripts/python.exe', 'engines/jianying-ai/python/python.exe'))
    missing = []
    if not source_ready: missing.append('固定版本的 DramaClip Python 源码')
    if not runtime_ready: missing.append('已通过导入检查的独立规划运行环境')
    ready = source_ready and runtime_ready
    return {'ready': ready, 'sourceReady': source_ready, 'runtimeReady': runtime_ready,
            'asrReady': asr_ready, 'visionReady': False, 'root': str(root), 'python': str(python),
            'commit': COMMIT, 'mode': 'highlight', 'model': 'faster-whisper small（复用本地文件）',
            'basis': '台词冲突与跨集故事线；视觉模型未启用',
            'message': ('本地融合规划引擎已就绪；转写使用同名 SRT 或已安装的 ASR，成片由本地编码' if ready else '缺少：' + '、'.join(missing)),
            'missing': missing, 'prepareCommand': 'python tools/prepare_dramaclip.py --local-dependencies'}


class LlmBridge(AbstractContextManager):
    def __init__(self, cfg, cancel, direction='', generate=None):
        self.cfg, self.cancel, self.direction = cfg, cancel, direction
        self.generate = generate
        self.token = secrets.token_urlsafe(32)
        self.errors = []
        self.requests = 0

    def __enter__(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args): pass

            def do_POST(self):
                if self.path != '/v1/chat/completions' or not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + outer.token):
                    self.send_error(403); return
                try:
                    if outer.cancel.is_set(): raise InterruptedError('任务已停止')
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 2_000_000: raise ValueError('DramaClip 模型请求超出上限')
                    body = json.loads(self.rfile.read(size))
                    messages = body.get('messages', [])
                    system = '\n'.join(str(m.get('content', '')) for m in messages if m.get('role') == 'system')
                    user = '\n'.join(str(m.get('content', '')) for m in messages if m.get('role') != 'system')
                    if outer.direction:
                        system += '\n用户剪辑偏好（只影响取材，不能编造素材）：' + outer.direction
                    if outer.generate is None:
                        import ai_providers
                        generate = ai_providers.text_generate
                    else: generate = outer.generate
                    response = generate(outer.cfg, system, user, min(12000, max(1024, int(body.get('max_tokens', 6500)))))
                    text = response['text']
                    if not isinstance(text, str) or not text.strip(): raise ValueError('文字模型返回空内容')
                    outer.requests += 1
                    data = json.dumps({'id': 'manju-local', 'choices': [{'message': {'role': 'assistant', 'content': text}}]}, ensure_ascii=False).encode()
                    self.send_response(200); self.send_header('Content-Type', 'application/json; charset=utf-8')
                    self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
                except Exception as exc:
                    # Provider exceptions can contain endpoint diagnostics; keep
                    # raw exception text in the parent process, never sidecar DB.
                    import ai_providers
                    outer.errors.append(ai_providers.redact(str(exc)))
                    data = json.dumps({'error': {'message': 'Manju text provider failed; inspect task diagnostics', 'type': type(exc).__name__}}).encode()
                    self.send_response(502); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.http.daemon_threads = True
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.base = f'http://127.0.0.1:{self.http.server_port}/v1'
        return self

    def __exit__(self, *_args):
        self.http.shutdown(); self.http.server_close(); self.thread.join(2)


class Sidecar(AbstractContextManager):
    def __init__(self, options, data, cancel, notify=None):
        self.root, self.source, self.python = locations(options)
        self.data, self.cancel, self.notify = Path(data), cancel, notify
        self.token = secrets.token_urlsafe(32)
        self.seq = 0
        self.replies = queue.Queue()
        self.tail = []

    def __enter__(self):
        self.data.mkdir(parents=True, exist_ok=True)
        listener = socket.socket(); listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(.2)
        env = dict(os.environ, DRAMACLIP_SERVICE_ADDRESS=f'127.0.0.1:{listener.getsockname()[1]}',
                   DRAMACLIP_AUTH_TOKEN=self.token, DRAMACLIP_DATA_DIR=str(self.data),
                   MANJU_DRAMACLIP_SOURCE=str(self.source), PYTHONUTF8='1', HF_HUB_OFFLINE='1')
        # Isolated python ignores PYTHONPATH; the small bootstrap inserts exactly
        # the selected service source and never loads user's site/customizations.
        self.process = subprocess.Popen([str(self.python), '-I', '-B', '-u', str(BASE / 'tools/dramaclip_sidecar.py')],
            env=env, cwd=str(self.root), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def logs():
            for line in iter(self.process.stdout.readline, b''):
                text = line.decode('utf-8', 'replace').strip()
                if text:
                    self.tail.append(text); self.tail = self.tail[-30:]
        threading.Thread(target=logs, daemon=True).start()
        try:
            deadline = time.monotonic() + 40
            while True:
                if self.cancel.is_set(): raise InterruptedError('本地融合引擎已停止')
                if self.process.poll() is not None: raise RuntimeError('DramaClip 启动失败：' + '\n'.join(self.tail[-12:]))
                if time.monotonic() > deadline: raise TimeoutError('DramaClip 启动握手超时')
                try: self.sock, _ = listener.accept(); break
                except socket.timeout: continue
            self.reader = self.sock.makefile('rb')
            self.sock.settimeout(10)
            hello = json.loads(self.reader.readline(16 * 1024 * 1024))
            if hello.get('type') != 'hello' or not secrets.compare_digest(str(hello.get('token', '')), self.token):
                raise ValueError('DramaClip token 握手校验失败')
            self.sock.settimeout(None)
            self.sock.sendall(b'{"type":"hello-ack"}\n')
            self.version = hello.get('service_version')
            threading.Thread(target=self._read, daemon=True).start()
        except BaseException:
            self.close(); raise
        finally: listener.close()
        return self

    def _read(self):
        try:
            for line in self.reader:
                if len(line) > 16 * 1024 * 1024: raise ValueError('DramaClip response too large')
                message = json.loads(line)
                if 'id' in message: self.replies.put(message)
                elif self.notify: self.notify(message)
        except Exception as exc:
            self.replies.put({'error': {'message': 'DramaClip 连接中断：' + str(exc)}})
        finally: self.replies.put({'error': {'message': 'DramaClip 工作进程连接已关闭'}})

    def call(self, method, params=None, timeout=900):
        self.seq += 1; ident = self.seq
        self.sock.sendall((json.dumps({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params or {}}, ensure_ascii=False) + '\n').encode())
        deadline = time.monotonic() + timeout
        while True:
            if self.cancel.is_set(): raise InterruptedError('本地融合引擎已停止')
            if time.monotonic() > deadline: raise TimeoutError('DramaClip RPC 超时：' + method)
            try: response = self.replies.get(timeout=.2)
            except queue.Empty: continue
            if response.get('id') not in (None, ident): continue
            if response.get('error'):
                cause = 'DramaClip ' + method + '：' + str(response['error']['message'])
                if getattr(self, 'provider_errors', None):
                    cause += '\n文字接口原始错误：' + '\n'.join(self.provider_errors[-3:])
                raise RuntimeError(cause)
            return response.get('result')

    def close(self):
        if hasattr(self, 'sock'):
            try: self.sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            self.sock.close()
        if hasattr(self, 'process') and self.process.poll() is None:
            try: self.process.wait(timeout=4)
            except subprocess.TimeoutExpired: self.process.terminate(); self.process.wait(timeout=5)

    def __exit__(self, *_args): self.close()


def _converted(plans, episodes, sources, count, seconds, cues=None):
    import promotion_studio
    by_id = {e['id']: i for i, e in enumerate(episodes)}
    result = []
    for row in plans:
        segments = []
        remaining = float(seconds)
        for segment in row['plan_data'].get('timeline', []):
            if len(segments) >= 24 or remaining < .5: break
            index = by_id.get(segment.get('episode_id'))
            if index is None: raise ValueError('DramaClip 方案引用了未选择的视频')
            start = float(segment['start']); end = min(float(segment['end']), sources[index]['duration'], start + remaining)
            if cues and end < float(segment['end']) - .05:
                # Target length is a budget, not permission to cut a spoken line
                # in half. Prefer a complete utterance ending inside the budget.
                endings = [float(c['end']) for c in cues[index] if start + .5 <= float(c['end']) <= end + .01]
                if endings: end = min(end, max(endings))
                else: break
            if end - start < .5: continue
            segments.append({'source': index, 'start': start, 'end': end, 'reason': row.get('angle_reason', '')})
            remaining -= end - start
        result.append({'title': row.get('angle') or '剧情高光', 'reason': row.get('angle_reason', ''),
                       'description': row.get('angle_reason', ''), 'segments': segments})
    clean = promotion_studio.validate_plans({'clips': result}, sources, count, seconds)
    # Stable upstream plan ids make completed render checkpoints reusable.
    for item, upstream in zip(clean, plans): item['id'] = upstream['id']
    return clean


def _supplement_single_episode(api, cfg, jid, opts, sources, cues, plans):
    """Request different timed excerpts when DramaClip can only plan one raw clip."""
    import promotion_studio
    seconds = opts['seconds']
    transcript = [{'source': 0, 'start': c['start'], 'end': c['end'], 'text': c['text']} for c in cues[0]]
    minimum = max(5, seconds * .5)
    payload = {'count': 1, 'targetSeconds': seconds, 'minimumSeconds': minimum,
               'maximumSeconds': seconds, 'direction': opts['direction'],
               'sourceDuration': sources[0]['duration'], 'transcript': transcript,
               'rule': '为同一集补充一条有不同重点的原声混剪。时间必须选自台词的起止点，保留完整句子。'
                       f'各段 end-start 之和必须在 {minimum:g} 到 {seconds:g} 秒之间，尽量接近目标。'
                       '优先选择已有方案之外的连续对话，尽量达到目标时长的90%以上。'
                       '与任意已有方案相比，重叠秒数不得超过较短方案的60%。'
                       '返回前先计算总秒数与重叠秒数。'}
    if len(json.dumps(payload, ensure_ascii=False)) > 180000:
        api.log('单集台词过长，已保留 DramaClip 已生成的方案。', level='warning', job=jid)
        return 0
    added = 0
    for _ in range(len(plans), opts['count']):
        payload['existing'] = [plan['segments'] for plan in plans]
        api.stage(jid, f'单集补选不同高光 {len(plans)+1}/{opts["count"]}', 80)
        payload.pop('correction', None)
        for _ in range(2):
            if api.JOBS[jid]['cancel'].is_set():
                raise InterruptedError('本地融合引擎已停止')
            try:
                response = promotion_studio.ai_providers.text_generate(cfg, promotion_studio.SYSTEM,
                    json.dumps(payload, ensure_ascii=False), 2400)
            except (ValueError, RuntimeError) as error:
                api.log('单集补选文字请求失败，保留已生成的高光。'+api.diagnostic_text(error), level='warning', job=jid)
                return added
            try:
                candidate = _validate_supplement(response['text'], sources, seconds, transcript, plans)
            except ValueError as error:
                payload['correction'] = f'上次未通过：{error}。重新核算时长与重叠后返回一条不同方案。'
                api.log('单集补选未通过校验。'+str(error), level='warning', job=jid)
            else:
                plans.append(candidate)
                added += 1
                break
        else:
            break
    return added


def _validate_supplement(text, sources, seconds, transcript, plans):
    import promotion_studio
    candidate, = promotion_studio.validate_plans(promotion_studio.decode_json(text), sources, 1, seconds)
    if candidate['seconds'] > seconds + .05:
        raise ValueError('补选方案超过目标时长')
    for segment in candidate['segments']:
        if not (any(abs(segment['start'] - c['start']) <= .05 for c in transcript)
                and any(abs(segment['end'] - c['end']) <= .05 for c in transcript)):
            raise ValueError('补选方案没有按完整台词切分')
    if _too_similar(candidate['segments'], candidate['seconds'], plans):
        raise ValueError('补选方案与已有成片取材重叠超过 60%')
    _extend_single_episode(candidate, transcript, sources[0]['duration'], seconds, plans)
    return candidate


def _too_similar(segments, seconds, plans):
    for plan in plans:
        overlap = sum(max(0, min(a['end'], b['end']) - max(a['start'], b['start']))
                      for a in plan['segments'] for b in segments)
        if overlap > .6 * min(plan['seconds'], seconds):
            return True
    return False


def _extend_single_episode(plan, transcript, duration, target, existing=()):
    """Lengthen existing excerpts with adjacent complete dialogue under the budget."""
    segments = plan['segments']
    by_start = sorted(transcript, key=lambda cue: cue['start'], reverse=True)
    by_end = sorted(transcript, key=lambda cue: cue['end'])
    seconds = plan['seconds']
    while seconds < target - .05:
        choices = []
        for index, segment in enumerate(segments):
            before = next((cue for cue in by_start if cue['start'] < segment['start'] - .05), None)
            after = next((cue for cue in by_end if segment['end'] + .05 < cue['end'] <= duration), None)
            for edge, cue in (('start', before), ('end', after)):
                if cue is None:
                    continue
                gap = segment['start'] - cue['end'] if edge == 'start' else cue['start'] - segment['end']
                added = abs(cue[edge] - segment[edge])
                if gap > 2 or seconds + added > target:
                    continue
                extended = {**segment, edge: round(cue[edge], 3)}
                other = segments[:index] + segments[index+1:]
                if any(extended['start'] < s['end'] and extended['end'] > s['start'] for s in other):
                    continue
                if _too_similar(segments[:index] + [extended] + segments[index+1:], seconds + added, existing):
                    continue
                choices.append((max(0, gap), -added, index, extended))
        if not choices:
            break
        _, _, index, extended = min(choices, key=lambda choice: choice[:2])
        segments[index] = extended
        seconds = sum(s['end'] - s['start'] for s in segments)
    plan['seconds'] = round(seconds, 3)


def run(api, project, cfg, jid, opts, sources):
    import promotion_studio
    engine = opts.get('engineOptions', {})
    ready = status(engine)
    if not ready['ready']: raise ValueError(ready['message'])
    promotion_studio.check_sources(sources)
    job = api.JOBS[jid]
    out = api.project_dir(project, cfg) / '智能推广' / jid; out.mkdir(parents=True, exist_ok=True)
    state = job.setdefault('promotionDramaClip', {})
    digest = hashlib.sha256(json.dumps({'sources': sources, 'count': opts['count'], 'seconds': opts['seconds'],
                                      'direction': opts.get('direction', ''), 'commit': COMMIT}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if state.get('inputDigest') not in (None, digest): raise ValueError('恢复任务的输入或剪辑设置已改变，请新建任务')
    state.update(inputDigest=digest, commit=COMMIT, dataDir=str(out / 'DramaClip数据'))
    api.persist_jobs()
    api.log('本地融合引擎：现有 ASR/SRT → DramaClip 冲突评分与跨集故事线 → 本地 FFmpeg；视觉模型未启用', job=jid)
    analysis = state.get('analysis')
    if analysis is None:
        base_count = 1 if len(sources) == 1 else opts['count']
        cues = promotion_studio.transcripts(api, project, cfg, jid, sources, out)
        def notice(message):
            if message.get('method') == 'log.append':
                params = message.get('params', {})
                level = {'warn': 'warning', 'warning': 'warning', 'error': 'error'}.get(params.get('level'), 'info')
                api.log('DramaClip：' + str(params.get('message', '')), level=level, job=jid)
        with LlmBridge(cfg, job['cancel'], opts.get('direction', '')) as bridge:
            with Sidecar(engine, out / 'DramaClip数据', job['cancel'], notice) as dra:
                dra.provider_errors = bridge.errors
                api.log('DramaClip 工作进程握手成功，版本 ' + str(dra.version) + '，来源 ' + COMMIT[:12], job=jid)
                dra.call('manju.configure', {'base_url': bridge.base, 'token': bridge.token})
                imported = dra.call('manju.import', {'project_id': state.get('projectId'), 'name': project['name'], 'sources': sources})
                if state.get('projectId') and state['projectId'] != imported['project']['id']:
                    state.pop('episodeAnalysis', None); state.pop('planTaskId', None); state.pop('planIds', None)
                    api.log('DramaClip 本任务数据库已重建，将重用本机转写缓存并恢复分析', level='warning', job=jid)
                state.update(projectId=imported['project']['id'], episodeIds=[e['id'] for e in imported['episodes']])
                api.persist_jobs()
                done = state.setdefault('episodeAnalysis', {})
                for i, (episode, transcript) in enumerate(zip(imported['episodes'], cues)):
                    if episode['id'] in done and episode.get('status') == 'done': continue
                    api.stage(jid, f'融合引擎分析冲突 {i+1}/{len(sources)}', 55 + 20 * i / len(sources))
                    value = dra.call('manju.analyse_transcript', {'episode_id': episode['id'], 'cues': transcript})
                    done[episode['id']] = value; api.persist_jobs()
                    api.log(f"DramaClip 第{i+1}集：{value['sceneCount']}个完整台词窗口，题材{value['genre']}，分析已保存", job=jid)
                batch = state.get('planTaskId')
                reusable_plans = None
                if batch:
                    previous = dra.call('jobs.get', {'job_id': batch})['job']
                    if previous['status'] != 'completed':
                        saved_plans = dra.call('narration.list_plans', {'project_id': state['projectId'], 'batch_id': batch})
                        if len(saved_plans) == base_count:
                            try:
                                _converted(saved_plans, imported['episodes'], sources, base_count, opts['seconds'], cues)
                                reusable_plans = saved_plans
                            except (ValueError, KeyError, TypeError): pass
                        if reusable_plans:
                            api.log('复用 DramaClip 上次已保存的方案，继续完成本地混剪', job=jid)
                        else:
                            history = state.setdefault('planAttempts', [])
                            history.append({'taskId': batch, 'status': previous['status'], 'error': previous.get('error'), 'at': time.time()})
                            state['planAttempts'] = history[-20:]
                            state.pop('planTaskId', None); batch = None
                            api.persist_jobs()
                            api.log('DramaClip 上次规划未完成，保留已完成的分集分析，重新提交故事线规划', level='warning', job=jid)
                if not batch:
                    batch = dra.call('narration.plan_variants', {'project_id': state['projectId'], 'modes': ['raw_clip'], 'k': base_count})['job_id']
                    state['planTaskId'] = batch; api.persist_jobs()
                deadline = time.monotonic() + 1800
                while reusable_plans is None:
                    task = dra.call('jobs.get', {'job_id': batch})['job']
                    if task['status'] == 'completed': break
                    if task['status'] in ('failed', 'cancelled', 'interrupted'):
                        cause = 'DramaClip 规划失败：' + str(task.get('error') or task['status'])
                        if bridge.errors: cause += '\n文字接口原始错误：' + '\n'.join(bridge.errors[-3:])
                        raise RuntimeError(api.diagnostic_text(cause))
                    if time.monotonic() > deadline: raise TimeoutError('DramaClip 故事线规划超时')
                    api.stage(jid, 'DramaClip 编排跨集高光：' + str(task.get('label') or '选取故事线'), 78)
                    if job['cancel'].wait(.5):
                        dra.call('jobs.cancel', {'job_id': batch}); raise InterruptedError('本地融合引擎已停止')
                plans = reusable_plans or dra.call('narration.list_plans', {'project_id': state['projectId'], 'batch_id': batch})
                state['planIds'] = [p['id'] for p in plans]
                converted = _converted(plans, imported['episodes'], sources, base_count, opts['seconds'], cues)
                if len(sources) == 1:
                    _extend_single_episode(converted[0], cues[0], sources[0]['duration'], opts['seconds'])
                supplemental = _supplement_single_episode(api, cfg, jid, opts, sources, cues, converted) if base_count < opts['count'] else 0
                if len(converted) < opts['count']:
                    api.log(f'请求 {opts["count"]} 条，本次有 {len(converted)} 条符合取材要求，将先导出合格成片。', level='warning', job=jid)
                analysis = {'id': jid, 'sources': sources, 'clips': converted, 'settings': opts,
                            'renderSize': promotion_studio.promotion_render_size(sources),
                            'basis': 'DramaClip timed-transcript conflict scoring and cross-episode original-audio planning',
                            'model': 'configured-text-provider', 'engine': 'manju-dramaclip', 'supplementalClips': supplemental,
                            'commit': COMMIT, 'createdAt': time.time()}
                state.update(analysis=analysis, llmRequests=bridge.requests)
                api.persist_jobs()
    promotion_studio.check_sources(sources)
    path = out / '融合高光分析.json'; path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), 'utf-8')
    with api.LOCK:
        project['promotionAnalysis'] = analysis; api.register(project, path, '推广分析', jid); api.save()
    clips = promotion_studio.render(api, project, cfg, jid, analysis)
    with api.LOCK:
        for clip in clips:
            clip['engine'] = 'manju-dramaclip'
            plan_id = clip['id'].removeprefix(jid + '-')
            if plan_id in state.get('planIds', []):
                clip['dramaclipPlanId'] = plan_id
            else:
                clip['planSource'] = 'timed_transcript_supplement'
        api.save()
    job['result'] = {'clipIds': [c['id'] for c in clips], 'paths': [c['path'] for c in clips],
                     'engine': 'manju-dramaclip', 'analysisPath': str(path), 'planIds': state.get('planIds', []),
                     'requestedClipCount': opts['count']}
    api.persist_jobs()
