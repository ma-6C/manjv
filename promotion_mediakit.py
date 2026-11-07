"""Volcengine AI MediaKit microdrama highlights, with resumable local bookkeeping.

Contract (verified against the official API reference, 2026-11-06):
https://docs.volcengine.com/docs/intelligent-processing/generate-highlights-microdrama
https://docs.volcengine.com/docs/intelligent-processing/request-media-upload-url

API keys only live in this process. A task with an uncertain submission is never
submitted again automatically, even though the provider also supports client_token.
"""
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
import copy
import hashlib
import http.client
import ipaddress
import json
import math
import mimetypes
import re
import socket
import ssl
import threading
import time
import uuid

DEFAULT_BASE = 'https://mediakit.cn-beijing.volces.com'
MAX_FILE_BYTES = 5 * 1024 ** 3
POLL_SECONDS = 3
POLL_TIMEOUT = 6 * 60 * 60
_KEYS = {}
_REDACTION_KEYS = set()
_KEY_LOCK = threading.RLock()
_SECRET_HEADERS = {'authorization', 'proxy-authorization', 'cookie', 'host',
                   'connection', 'transfer-encoding', 'content-length'}


def normalize_base(base=DEFAULT_BASE):
    if not isinstance(base, str) or base.rstrip('/') != DEFAULT_BASE:
        raise ValueError('火山 AI MediaKit 仅支持官方地址 ' + DEFAULT_BASE)
    return DEFAULT_BASE


def set_key(base, key):
    base = normalize_base(base)
    if not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in key):
        raise ValueError('MediaKit API Key 格式无效')
    with _KEY_LOCK:
        if key.strip():
            _KEYS[base] = key.strip()
            # An in-flight request can still fail after the user changes or
            # clears the active key. Keep process-local redaction coverage.
            _REDACTION_KEYS.add(key.strip())
        else:
            _KEYS.pop(base, None)


def key_status(base=DEFAULT_BASE):
    with _KEY_LOCK:
        return bool(_KEYS.get(normalize_base(base)))


def redact(text):
    text = str(text)
    with _KEY_LOCK:
        for secret in _REDACTION_KEYS:
            text = text.replace(secret, '[已隐藏]')
    text = re.sub(r'(?i)\bBearer\s+[^\s\"\'<>]+', 'Bearer [已隐藏]', text)
    # Signed media URLs never belong in logs, error messages or client snapshots.
    text = re.sub(r'https://[^\s\"\'<>]+', lambda m: m[0].split('?', 1)[0] + ('?[已隐藏]' if '?' in m[0] else ''), text)
    return text


def _cancel(cancel):
    if cancel.is_set():
        raise InterruptedError('云端高光任务已暂停；已提交的云任务仍可能运行，继续时将查询原任务')


def _media_url(url):
    try:
        p = urlsplit(url)
        port = p.port
    except (TypeError, ValueError):
        raise ValueError('云端返回的媒体地址无效') from None
    if (p.scheme != 'https' or not p.hostname or p.username or p.password or
            p.fragment or port not in (None, 443) or any(ord(c) < 33 for c in url)):
        raise ValueError('云端媒体地址必须是公开 HTTPS 地址，且不能包含账号或非标准端口')
    host = p.hostname.lower().rstrip('.')
    if '.' not in host or host.endswith(('.localhost', '.local', '.internal')):
        raise ValueError('云端媒体地址不能指向本地网络')
    return p


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Validate and pin a public IP while keeping hostname TLS verification."""
    def connect(self):
        addresses = socket.getaddrinfo(self.host, self.port, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('云端媒体地址解析到了本地或保留网络，已拒绝连接')
        last = None
        for family, kind, protocol, _, address in addresses:
            sock = socket.socket(family, kind, protocol)
            sock.settimeout(self.timeout)
            try:
                sock.connect(address)
                self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
                return
            except OSError as exc:
                last = exc
                sock.close()
        raise last or OSError('无法连接云端媒体地址')


def _connection(url):
    p = _media_url(url)
    return _PinnedHTTPSConnection(p.hostname, timeout=12, context=ssl.create_default_context()), urlunsplit(('', '', p.path or '/', p.query, ''))


class CloudHTTPError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'MediaKit HTTP {status}：' + redact(message))


def _request_json(base, key, method, path, payload, cancel):
    """Patchable transport boundary; API auth is used only on the fixed API origin."""
    normalize_base(base)
    if not path.startswith('/api/v1/') or '?' in path or '..' in path:
        raise ValueError('MediaKit API 路径无效')
    _cancel(cancel)
    connection, target = _connection(base + path)
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    try:
        connection.request(method, target, body=body, headers={
            'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'Accept': 'application/json'})
        response = connection.getresponse()
        _cancel(cancel)
        raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise RuntimeError('MediaKit 返回的数据超过 4MB 限制')
        if response.status < 200 or response.status >= 300:
            # Redirects are deliberately not followed, so API keys cannot escape.
            raise CloudHTTPError(response.status, raw.decode('utf-8', 'replace')[:4000])
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise RuntimeError('MediaKit 没有返回有效 JSON') from None
        if not isinstance(value, dict):
            raise RuntimeError('MediaKit 返回结构无效')
        return value
    except (TimeoutError, socket.timeout):
        raise TimeoutError('MediaKit 网络请求超时；请检查网络，已保存的云任务将通过原任务 ID 继续查询') from None
    except OSError as exc:
        raise ConnectionError('MediaKit 网络连接失败：' + redact(exc)) from None
    finally:
        connection.close()


def _upload_headers(raw, path):
    if not isinstance(raw, list):
        raise ValueError('MediaKit 上传凭证中的请求头格式无效')
    headers = {}
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get('key'), str) or not isinstance(item.get('value'), str):
            raise ValueError('MediaKit 上传凭证中的请求头格式无效')
        key, value = item['key'], item['value']
        if (not re.fullmatch(r'[!#$%&\'*+.^_`|~0-9A-Za-z-]+', key) or
                any(ord(c) < 32 or ord(c) == 127 for c in value) or key.lower() in _SECRET_HEADERS):
            raise ValueError('MediaKit 上传凭证包含不允许转发的请求头')
        headers[key] = value
    if not any(k.lower() == 'content-type' for k in headers):
        headers['Content-Type'] = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
    return headers


def _upload_file(url, headers, path, cancel, progress=None):
    """Stream PUT; separate connection and headers prevent API credential leakage."""
    _cancel(cancel)
    connection, target = _connection(url)
    size = Path(path).stat().st_size
    try:
        connection.putrequest('PUT', target)
        for name, value in headers.items():
            if name.lower() in _SECRET_HEADERS:
                raise ValueError('媒体上传不能转发 API 身份凭证')
            connection.putheader(name, value)
        connection.putheader('Content-Length', str(size))
        connection.endheaders()
        sent = 0
        with Path(path).open('rb') as source:
            while True:
                _cancel(cancel)
                chunk = source.read(256 * 1024)
                if not chunk:
                    break
                connection.send(chunk)
                sent += len(chunk)
                if progress:
                    progress(sent, size)
        if sent != size:
            raise RuntimeError('上传过程中源视频大小改变，请重新检查素材')
        response = connection.getresponse()
        response.read(4096)
        _cancel(cancel)
        if response.status < 200 or response.status >= 300:
            raise CloudHTTPError(response.status, '媒体上传失败，请重新连接后继续上传')
    except (TimeoutError, socket.timeout):
        raise TimeoutError('媒体上传超时；已完成的上传会保留，当前文件需完整重传') from None
    except OSError as exc:
        raise ConnectionError('媒体上传连接失败：' + redact(exc)) from None
    finally:
        connection.close()


def _download_file(url, target, cancel):
    _cancel(cancel)
    connection, endpoint = _connection(url)
    partial = Path(str(target) + '.part')
    try:
        # Neither the API key nor upload headers are accepted by this function.
        connection.request('GET', endpoint, headers={'Accept': 'video/*'})
        response = connection.getresponse()
        if response.status < 200 or response.status >= 300:
            raise CloudHTTPError(response.status, '成片下载失败；请核对原云任务。默认产物链接自生成起24小时有效，过期不支持续期，未自动重新生成')
        raw_length = response.getheader('Content-Length')
        try:
            length = int(raw_length) if raw_length is not None else None
        except ValueError:
            raise RuntimeError('云端成片的 Content-Length 无效') from None
        if length is not None and not 0 < length <= MAX_FILE_BYTES:
            raise RuntimeError('云端成片为空或超过 5GB 限制')
        received = 0
        with partial.open('wb') as out:
            while True:
                _cancel(cancel)
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > MAX_FILE_BYTES:
                    raise RuntimeError('云端成片超过 5GB 限制')
                out.write(chunk)
        if not received or (length is not None and received != length):
            raise RuntimeError('云端成片下载不完整，请继续原任务重新下载')
        _cancel(cancel)
        partial.replace(target)
    except (TimeoutError, socket.timeout):
        raise TimeoutError('云端成片下载超时；继续时将重新下载原云任务结果') from None
    except OSError as exc:
        raise ConnectionError('云端成片下载连接失败：' + redact(exc)) from None
    finally:
        connection.close()
        partial.unlink(missing_ok=True)


def _success(value):
    if value.get('success') is not True:
        error = value.get('error') or {}
        message = ': '.join(str(error[k]) for k in ('code', 'message') if error.get(k)) if isinstance(error, dict) else str(error)
        raise RuntimeError('MediaKit 返回失败：' + redact(message or '未提供错误详情'))
    return value


def _finite(value, low, high, label, integer=False):
    if (type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high or
            (integer and value != int(value))):
        raise ValueError(label + '超出有效范围')
    return int(value) if integer else float(value)


def _validate(sources, opts):
    if not sources or len(sources) > 30:
        raise ValueError('火山高光智剪每次需要 1 至 30 个视频')
    total = 0
    for source in sources:
        path = Path(source['path'])
        if not path.is_file():
            raise ValueError('源视频不存在：' + path.name)
        stat = path.stat()
        if source.get('stat') != {'bytes': stat.st_size, 'mtimeNs': stat.st_mtime_ns}:
            raise ValueError('源视频已经修改，请重新选择：' + path.name)
        if not 0 < stat.st_size <= MAX_FILE_BYTES:
            raise ValueError('云端上传单个视频需大于 0 且不超过 5GB：' + path.name)
        total += _finite(source.get('duration'), .001, 2700, '源视频时长')
        width = _finite(source.get('width'), 1, 1920, '源视频宽度', True)
        height = _finite(source.get('height'), 1, 1920, '源视频高度', True)
        if min(width, height) > 1080:
            raise ValueError('火山高光智剪最高支持 1080p：' + path.name)
        if not source.get('audio'):
            raise ValueError('火山高光智剪需要视频和音轨：' + path.name)
    if total > 2700:
        raise ValueError('火山高光智剪输入总时长不能超过 45 分钟')
    _finite(opts.get('count'), 1, 6, '成片数量', True)
    _finite(opts.get('seconds'), 10, 180, '成片目标时长')
    options = opts.get('engineOptions') or {}
    if not isinstance(options, dict) or options.get('cutMode', 'Mixed') not in ('Mixed', 'Sequential'):
        raise ValueError('火山高光剪辑模式须为 Mixed 或 Sequential')
    for name, maximum in (('title', 22), ('template', 30)):
        if not isinstance(options.get(name, ''), str) or len(options.get(name, '')) > maximum:
            raise ValueError('火山高光' + name + '长度或格式无效')
    template = options.get('template', '')
    if template and template not in tuple('热门短剧' + str(i) for i in range(1, 6)):
        raise ValueError('火山高光模板须为热门短剧1至热门短剧5')
    return options


def _payload(project, opts, urls, token):
    options = opts.get('engineOptions') or {}
    seconds = float(opts['seconds'])
    cuts = {'cut_mode': options.get('cutMode', 'Mixed'), 'enable_storyboard': True,
            'min_duration': max(1, seconds - 5), 'max_duration': seconds,
            'max_number': int(opts['count'])}
    if opts.get('direction'):
        cuts['highlight_segment_prompt'] = str(opts['direction'])[:1000]
    payload = {'video_urls': urls, 'mode': 'StorylineCuts', 'enable_generate_video': True,
               'highlight_cuts_param': cuts, 'client_token': token}
    # Apply the existing page's title/CTA to an actual provider template, rather
    # than merely recording them in metadata. Provider visual limits are 22/20.
    payload['edit_param'] = {'mode': 'TemplateEdit', 'template_edit': {
        'template': options.get('template') or '热门短剧1',
        'title': options.get('title') or str(project['name'])[:22],
        'hint': str(opts.get('cta', ''))[:20]}}
    return payload


def _persist(api, remote, **values):
    with api.LOCK:
        remote.update(values, updatedAt=time.time())
        api.persist_jobs()


def run(api, project, cfg, jid, opts, sources):
    options = _validate(sources, opts)
    base = normalize_base(options.get('base', DEFAULT_BASE))
    job = api.JOBS[jid]
    cancel = job['cancel']
    _cancel(cancel)
    with _KEY_LOCK:
        key = _KEYS.get(base)
    if not key:
        raise ValueError('请在推广设置中填写火山 AI MediaKit API Key；密钥仅在当前软件进程内保存')
    fingerprint = hashlib.sha256(json.dumps({'sources': sources, 'options': opts}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    remote = job.setdefault('promotionRemote', {'engine': 'mediakit', 'base': base, 'uploads': [],
                                              'clientToken': uuid.uuid4().hex, 'fingerprint': fingerprint})
    if remote.get('engine') != 'mediakit' or remote.get('base') != base or remote.get('fingerprint') != fingerprint:
        raise ValueError('云端任务对应的素材或参数已改变，请保留原任务并新建制作任务')
    if not remote.get('taskId') and remote.get('status') in ('submitting', 'submission_unknown'):
        raise RuntimeError('上次云端提交结果未知，未自动重交以避免重复计费。请在火山 AI MediaKit 控制台按请求凭证 '
                           + str(remote.get('clientToken', '')) + ' 核对原任务；确认后再新建任务')
    if not remote.get('taskId'):
        if len(str(project['name'])) > 22 or len(str(opts.get('cta', ''))) > 20:
            api.log('火山视觉模板限制：画面剧名保留前22字，引导文字保留前20字；完整原文保留在本地制作记录', job=jid)
        uploads = remote['uploads']
        for i, source in enumerate(sources):
            _cancel(cancel)
            existing = next((u for u in uploads if u.get('sourceIndex') == i and u.get('stat') == source['stat'] and
                             time.time() - u.get('uploadedAt', 0) < 29 * 86400), None)
            if existing:
                continue
            api.stage(jid, f'上传云端素材 {i + 1}/{len(sources)} · {source["name"]}', 5 + 30 * i / len(sources))
            ticket = _success(_request_json(base, key, 'POST', '/api/v1/tools-sync/request-media-upload-url', {}, cancel)).get('result') or {}
            file_id = ticket.get('file_id')
            if ticket.get('method') != 'PUT' or not isinstance(file_id, str) or not file_id.startswith('mediakit://') or len(file_id) > 8192:
                raise RuntimeError('MediaKit 没有返回有效的媒体上传凭证')
            _media_url(ticket.get('upload_url'))
            _upload_file(ticket['upload_url'], _upload_headers(ticket.get('upload_headers'), source['path']), source['path'], cancel)
            # Verify the same source still exists after streaming it.
            if Path(source['path']).stat().st_size != source['stat']['bytes'] or Path(source['path']).stat().st_mtime_ns != source['stat']['mtimeNs']:
                raise ValueError('上传时源视频发生改变，请重新选择：' + source['name'])
            uploads[:] = [u for u in uploads if u.get('sourceIndex') != i]
            uploads.append({'sourceIndex': i, 'stat': copy.deepcopy(source['stat']), 'fileId': file_id, 'uploadedAt': time.time()})
            _persist(api, remote, status='uploading')
        urls = [next(u['fileId'] for u in uploads if u['sourceIndex'] == i) for i in range(len(sources))]
        api.stage(jid, '提交火山高光智剪 · 可能产生云端费用', 38)
        _cancel(cancel)
        _persist(api, remote, status='submitting', submittedAt=time.time())
        try:
            submitted = _request_json(base, key, 'POST', '/api/v1/tools/generate-highlights-microdrama',
                                      _payload(project, opts, urls, remote['clientToken']), cancel)
        except BaseException as exc:
            # Even a 5xx response can follow a successful provider-side creation.
            _persist(api, remote, status='submission_unknown')
            if isinstance(exc, InterruptedError):
                raise
            raise RuntimeError('云端提交未获得可靠任务 ID，结果未知，禁止自动重交。请在火山控制台按请求凭证 '
                               + remote['clientToken'] + ' 核对。原始原因：' + redact(exc)) from None
        if submitted.get('success') is not True:
            _persist(api, remote, status='rejected')
            _success(submitted)
        task_id = submitted.get('task_id')
        if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', task_id):
            _persist(api, remote, status='submission_unknown')
            raise RuntimeError('云端已响应成功但缺少可靠任务 ID；请到火山控制台核对，未自动重交')
        _persist(api, remote, taskId=task_id, status='submitted', requestId=str(submitted.get('request_id', ''))[:200])
        api.log('火山高光智剪已提交，任务 ID：' + task_id + '；断线后继续查询此任务，不重复提交', job=jid)
    task_id = remote['taskId']
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', task_id):
        raise ValueError('保存的 MediaKit 任务 ID 无效，请核对火山控制台')
    deadline = time.monotonic() + POLL_TIMEOUT
    while True:
        _cancel(cancel)
        api.stage(jid, '查询火山高光智剪 · ' + task_id, 45)
        result = _success(_request_json(base, key, 'GET', '/api/v1/tasks/' + quote(task_id, safe=''), None, cancel))
        status = result.get('status')
        _persist(api, remote, status=status if isinstance(status, str) else 'invalid_status', lastCheckedAt=time.time())
        if status == 'completed':
            break
        if status in ('failed', 'cancelled', 'canceled'):
            detail = result.get('error') or result.get('message') or '服务端没有返回详细原因'
            raise RuntimeError('火山高光智剪云端任务失败：' + redact(json.dumps(detail, ensure_ascii=False)) + '；任务 ID：' + task_id)
        if not isinstance(status, str) or not status:
            raise RuntimeError('MediaKit 返回的任务状态无效；已保存原任务 ID，请继续原任务查询')
        if time.monotonic() >= deadline:
            raise TimeoutError('火山高光智剪查询已等待 6 小时；云任务可能仍在运行，继续原任务即可，不会重交')
        if cancel.wait(POLL_SECONDS):
            _cancel(cancel)
    output = result.get('result') or {}
    urls = output.get('video_urls')
    if not isinstance(urls, list) or not urls or len(urls) > int(opts['count']) or any(not isinstance(u, str) for u in urls):
        raise RuntimeError('火山任务已完成但没有返回有效成片地址；请核对云端任务 ' + task_id)
    out = api.project_dir(project, cfg) / '智能推广' / jid
    out.mkdir(parents=True, exist_ok=True)
    clips = []
    info = output.get('mixvideo_info') or []
    for i, url in enumerate(urls):
        _cancel(cancel)
        _media_url(url)
        checkpoint = f'{project["id"]}:promotion-mediakit:{task_id}:{i}'
        cached = api.cached(jid, checkpoint)
        target = Path(cached[0]) if cached else out / f'云端高光_{i + 1:02d}.mp4'
        if not cached:
            expires = result.get('expires_at')
            if type(expires) in (int, float) and expires <= time.time():
                raise RuntimeError('火山云端成片链接已过期：默认链接自生成起24小时有效且不能续期。请核对控制台任务 ' + task_id + '，未自动重复计费生成')
            api.stage(jid, f'下载并校验云端成片 {i + 1}/{len(urls)}', 65 + 30 * i / len(urls))
            _download_file(url, target, cancel)
            try:
                meta = api.probe(target)
                if not meta.get('audio') or not math.isfinite(meta.get('duration', 0)) or meta['duration'] <= 0:
                    raise RuntimeError('云端成片缺少有效画面时长或音轨')
                # Full decode catches middle-of-file corruption that a duration probe misses.
                api.ff(['-v', 'error', '-xerror', '-i', str(target), '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'], jid)
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            api.checkpoint(jid, checkpoint, [target])
        meta = api.probe(target)
        stat = target.stat()
        item = next((x for x in info if isinstance(x, dict) and x.get('mixvideo_index') == i), {})
        segments = []
        for segment in item.get('clips', []) if isinstance(item.get('clips', []), list) else []:
            if isinstance(segment, dict):
                segments.append({k: copy.deepcopy(segment[k]) for k in ('clip_type', 'score', 'source_video_index', 'source_start_time',
                                'source_end_time', 'cut_start_time', 'cut_end_time', 'tags') if k in segment})
        clip = {'id': f'{jid}-mediakit-{i + 1}', 'path': str(target),
                'title': (options.get('title') or project['name']) + f' · 高光 {i + 1}',
                'description': str(opts.get('direction', '')), 'start': 0, 'seconds': meta['duration'],
                'requestedSeconds': opts['seconds'],
                'sourceKind': 'mediakit', 'engine': 'mediakit', 'remoteTaskId': task_id,
                'segments': segments, 'analysisId': jid, 'cta': str(opts.get('cta', ''))[:20],
                'requestedCta': opts.get('cta', ''), 'requestedTitle': project['name'],
                'bytes': stat.st_size, 'mtimeNs': stat.st_mtime_ns, 'sha256': api.sha256(target), 'createdAt': time.time()}
        with api.LOCK:
            existing = project.setdefault('promotionClips', [])
            previous = next((c for c in existing if c['id'] == clip['id']), None)
            if previous is None:
                existing.append(clip)
            else:
                # A verified checkpoint can expire after a local file is lost.
                # Redownloading the same cloud result must refresh this row.
                clip['createdAt'] = previous.get('createdAt', clip['createdAt'])
                previous.update(clip)
            api.register(project, target, '推广混剪', jid)
            api.save()
        clips.append(clip)
        _persist(api, remote, status='downloading', downloadedCount=len(clips))
    job['result'] = {'clipIds': [c['id'] for c in clips], 'paths': [c['path'] for c in clips], 'remoteTaskId': task_id}
    _persist(api, remote, status='completed_local', downloadedCount=len(clips))
    api.log(f'火山高光智剪完成：已下载并完整解码校验 {len(clips)} 个成片；云端数量和时长由算法按上限及范围生成', job=jid)
