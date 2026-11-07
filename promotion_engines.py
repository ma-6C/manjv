"""Page-scoped promotion engine settings and immutable job configuration.

Only non-secret options are persisted. MediaKit credentials remain in the
adapter's process-local key store and are never included in task snapshots.
"""
from pathlib import Path
import copy
import math
import re

DEFAULTS = {
    'mediakit': {'base': 'https://mediakit.cn-beijing.volces.com', 'cutMode': 'Mixed', 'downloadFolder': ''},
    'dramaclip': {'root': '', 'python': '', 'mode': 'highlight'},
}
ENGINES = {'local', 'mediakit'}


def normalize(value=None):
    if value is None:
        return copy.deepcopy(DEFAULTS)
    if not isinstance(value, dict) or set(value) - set(DEFAULTS):
        raise ValueError('推广引擎设置格式无效')
    result = copy.deepcopy(DEFAULTS)
    for engine, raw in value.items():
        if not isinstance(raw, dict) or set(raw) - set(DEFAULTS[engine]):
            raise ValueError('推广引擎设置只允许地址、路径和剪辑模式，不能保存密钥')
        result[engine].update(raw)
    cloud = result['mediakit']
    if not isinstance(cloud['base'], str) or cloud['base'].rstrip('/') != DEFAULTS['mediakit']['base']:
        raise ValueError('火山 AI MediaKit 请选择官方服务地址')
    cloud['base'] = DEFAULTS['mediakit']['base']
    if cloud['cutMode'] not in ('Mixed', 'Sequential'):
        raise ValueError('云端剪辑模式无效')
    folder = cloud['downloadFolder']
    if not isinstance(folder, str) or len(folder) > 32767 or any(ord(c) < 32 for c in folder):
        raise ValueError('云端成片保存文件夹格式无效')
    folder = folder.strip()
    if folder and not Path(folder).is_absolute():
        raise ValueError('云端成片请选择完整的文件夹路径')
    cloud['downloadFolder'] = folder
    dra = result['dramaclip']
    if dra['mode'] != 'highlight':
        raise ValueError('DramaClip 当前支持原片高光模式')
    for key, label in (('root', 'DramaClip 引擎目录'), ('python', 'DramaClip Python')):
        path = dra[key]
        if not isinstance(path, str) or len(path) > 32767 or any(ord(c) < 32 for c in path):
            raise ValueError(label + '格式无效')
        path = path.strip()
        if path and not Path(path).is_absolute():
            raise ValueError(label + '请选择完整的本地路径，或留空自动检测')
        dra[key] = path
    return result


def snapshot(cfg, engine):
    if engine not in ENGINES:
        raise ValueError('请选择有效的推广引擎')
    options = normalize(cfg.get('promotionEngineSettings'))['dramaclip' if engine == 'local' else engine]
    # The local destination is frozen in the job's output config, not the cloud request.
    options.pop('downloadFolder', None)
    return options


def local_backend(options, kind='promotion_auto'):
    """Freeze the local implementation before queuing; retries keep that route."""
    if kind != 'promotion_auto':
        return {'localBackend': 'native'}
    import promotion_dramaclip
    status = promotion_dramaclip.status(options)
    return {'localBackend': 'dramaclip' if status.get('ready') else 'native',
            'localBackendReason': status.get('message', '')}


def public(cfg):
    import promotion_mediakit
    import promotion_dramaclip
    settings = normalize(cfg.get('promotionEngineSettings'))
    return {'settings': settings,
            'mediakit': {'hasKey': promotion_mediakit.key_status(settings['mediakit']['base'])},
            'dramaclip': promotion_dramaclip.status(settings['dramaclip'])}


def configure(api, body):
    import promotion_mediakit
    if not isinstance(body, dict) or set(body) - {'settings', 'mediakitKey', 'clearMediakitKey'}:
        raise ValueError('推广引擎设置格式无效')
    if 'clearMediakitKey' in body and type(body['clearMediakitKey']) is not bool:
        raise ValueError('清除密钥选项格式无效')
    key = body.get('mediakitKey')
    if 'mediakitKey' in body and (not isinstance(key, str) or len(key) > 4096 or any(ord(c) < 32 or ord(c) == 127 for c in key)):
        raise ValueError('MediaKit API Key 格式无效')
    if body.get('clearMediakitKey') and key:
        raise ValueError('请分别执行保存密钥或清除密钥')
    with api.LOCK:
        current = normalize(api.STATE['config'].get('promotionEngineSettings'))
        raw = body.get('settings', {})
        if not isinstance(raw, dict) or set(raw) - set(DEFAULTS):
            raise ValueError('推广引擎设置格式无效')
        merged = copy.deepcopy(current)
        for name, fields in raw.items():
            if not isinstance(fields, dict):
                raise ValueError('推广引擎设置格式无效')
            merged[name].update(fields)
        clean = normalize(merged)
        folder = clean['mediakit']['downloadFolder']
        if folder and folder != current['mediakit']['downloadFolder']:
            clean['mediakit']['downloadFolder'] = api.writable_storage(folder, '云端成片保存文件夹：')
        cfg = copy.deepcopy(api.STATE['config'])
        cfg['promotionEngineSettings'] = clean
        api.store_config(cfg)
        # Validate everything and commit to disk before changing the memory key.
        if body.get('clearMediakitKey') or 'mediakitKey' in body:
            promotion_mediakit.set_key(clean['mediakit']['base'], '' if body.get('clearMediakitKey') else key)
    return public(cfg)


def preflight(engine, options, sources, kind='promotion_auto'):
    if engine not in ENGINES:
        raise ValueError('请选择有效的推广引擎')
    if engine == 'local':
        return
    if kind != 'promotion_auto':
        raise ValueError('云端与 DramaClip 请使用“开始生成”，分析与成片由所选引擎连续完成')
    import promotion_mediakit
    if not promotion_mediakit.key_status(options['base']):
        raise ValueError('请先在本页设置填写火山 AI MediaKit API Key；普通文字模型密钥不能代替它')
    if not 1 <= len(sources) <= 30:
        raise ValueError('火山云端一次支持1至30个视频，请减少所选集数')
    duration = 0.0
    for v in sources:
        length = v.get('duration', 0)
        if type(length) not in (int, float) or not math.isfinite(length) or length <= 0:
            raise ValueError('云端源视频时长无效，请重新扫描素材')
        duration += length
        if not v.get('audio'):
            raise ValueError('云端源视频缺少音轨：' + v.get('name', '未知视频'))
        if max(v.get('width', 0), v.get('height', 0)) > 1920 or min(v.get('width', 0), v.get('height', 0)) > 1080:
            raise ValueError('火山云端源视频最高支持1080p：' + v.get('name', '未知视频'))
        if v.get('stat', {}).get('bytes', 0) > 5 * 1024 ** 3:
            raise ValueError('火山云端单文件不能超过5GB：' + v.get('name', '未知视频'))
    if duration > 45 * 60:
        raise ValueError('火山云端所选素材总时长不能超过45分钟，请减少集数')


def run(api, project, cfg, jid):
    job = api.JOBS[jid]
    opts = copy.deepcopy(job['options']['studio'])
    engine = opts.get('engine', 'local')
    if engine not in ENGINES:
        raise ValueError('请选择有效的外部推广引擎')
    sources = job['options']['promotionSources']
    import promotion_studio
    promotion_studio.check_sources(sources)
    opts['engineOptions'] = copy.deepcopy(job['options'].get('engineOptions', snapshot(cfg, engine)))
    if engine == 'mediakit':
        import promotion_mediakit as adapter
    else:
        import promotion_dramaclip as adapter
    api.log('推广引擎：' + ('火山 AI MediaKit 云端' if engine == 'mediakit' else '本地智能混剪（融合 DramaClip）') +
            f'；所选源视频 {len(sources)} 集；配置已固定到本任务', job=jid)
    adapter.run(api, project, cfg, jid, opts, sources)


def public_jobs(rows):
    """Do not send remote upload URLs or sidecar auth journals to the browser."""
    for row in rows:
        remote = row.pop('promotionRemote', None)
        if not isinstance(remote, dict):
            remote = {}
        row.pop('promotionDramaClip', None)
        if (row.get('options') or {}).get('studio', {}).get('engine') != 'mediakit':
            continue
        result = row.get('result') or {}
        task_id = remote.get('taskId') or result.get('remoteTaskId')
        status = remote.get('status')
        if not status and task_id and row.get('status') == 'completed':
            status = 'completed_local'
        summary = {}
        if isinstance(task_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,200}', task_id):
            summary['taskId'] = task_id
        if status in ('uploading', 'submitting', 'submission_unknown', 'submitted', 'pending', 'queued',
                      'running', 'processing', 'completed', 'downloading', 'completed_local',
                      'failed', 'cancelled', 'canceled', 'rejected'):
            summary['status'] = status
        count = remote.get('downloadedCount')
        if type(count) is int and 0 <= count <= 6:
            summary['downloadedCount'] = count
        elif isinstance(result.get('paths'), list) and summary.get('status') == 'completed_local':
            summary['downloadedCount'] = len(result['paths'])
        if summary:
            row['mediakitTask'] = summary
    return rows
