"""Validated picture transforms and real, bounded comparison previews.

The quality number compares the final encode against the same intentional
transform before encoding. It is not a content originality or platform score.
"""
from pathlib import Path
import copy
import hashlib
import json
import math
import re

NUMBER_LIMITS = {
    'brightness': (-.2, .2), 'contrast': (.8, 1.3),
    'saturation': (0, 2), 'speed': (.5, 2), 'cropPercent': (0, 15),
    'cropLeft': (0, 30), 'cropRight': (0, 30),
    'cropTop': (0, 30), 'cropBottom': (0, 30),
}
DEFAULTS = {'brightness': 0., 'contrast': 1., 'saturation': 1., 'speed': 1.,
            'cropPercent': 0., 'cropLeft': 0., 'cropRight': 0., 'cropTop': 0.,
            'cropBottom': 0., 'transformCropMode': 'symmetric', 'encodeQuality': 'balanced'}
CONFIG_FIELDS = tuple(DEFAULTS)
DEFAULTS['transformPresets'] = []


def _number(value, low, high, key):
    if isinstance(value, bool) or value is None or isinstance(value, str) and not value.strip():
        raise ValueError(key + '请填写有效数字')
    if not isinstance(value, (int, float, str)):
        raise ValueError(key + '请填写有效数字')
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(key + '请填写有效数字') from None
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f'{key}须在 {low} 至 {high} 之间')
    return result


def validate(cfg):
    """Normalize transform fields in place without consuming unknown settings."""
    if not isinstance(cfg, dict):
        raise ValueError('画面参数格式无效')
    for key, default in DEFAULTS.items():
        cfg.setdefault(key, copy.deepcopy(default))
    for key, (low, high) in NUMBER_LIMITS.items():
        cfg[key] = _number(cfg[key], low, high, key)
    if cfg['transformCropMode'] not in ('symmetric', 'edges'):
        raise ValueError('裁切方式请选择对称或四边裁切')
    if cfg['encodeQuality'] not in ('speed', 'balanced', 'quality'):
        raise ValueError('画质档位请选择速度优先、平衡或画质优先')
    if cfg['cropLeft'] + cfg['cropRight'] > 50 or cfg['cropTop'] + cfg['cropBottom'] > 50:
        raise ValueError('相对两边裁切合计不能超过50%，请保留主要画面')
    return cfg


def validate_presets(rows):
    """Named values only: presets cannot carry paths, credentials or jobs."""
    if not isinstance(rows, list) or len(rows) > 30:
        raise ValueError('画面方案最多保存30条')
    result = []; seen = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'id', 'name', 'values'}:
            raise ValueError('画面方案只允许编号、名称和画面参数')
        pid, name, values = row['id'], row['name'], row['values']
        if not isinstance(pid, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', pid) or pid in seen:
            raise ValueError('画面方案编号无效或重复')
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 40 or any(ord(c) < 32 or ord(c) == 127 for c in name):
            raise ValueError('画面方案名称请填写1至40个字符')
        if not isinstance(values, dict) or not values or any(k not in CONFIG_FIELDS for k in values):
            raise ValueError('画面方案中含有不支持的参数')
        normalized = validate(copy.deepcopy(DEFAULTS) | values)
        result.append({'id': pid, 'name': name.strip(), 'values': {key: normalized[key] for key in CONFIG_FIELDS}})
        seen.add(pid)
    return result


def values(cfg):
    normalized = validate(copy.deepcopy(cfg))
    selected = {key: normalized[key] for key in CONFIG_FIELDS}
    selected.update({key: cfg.get(key) for key in ('width', 'height', 'markAI', 'markPosition', 'gpu')})
    return selected


def fingerprint(cfg):
    return hashlib.sha256(json.dumps(values(cfg), sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def crop_geometry(cfg, info):
    """The exact even-pixel crop used by FFmpeg, also suitable for an overlay."""
    values = validate(copy.deepcopy(cfg))
    source_width, source_height = int(info['width']), int(info['height'])
    if source_width < 4 or source_height < 4:
        raise ValueError('源视频尺寸过小，不能裁切')
    mode = values['transformCropMode']
    if mode == 'symmetric':
        edges = {side: values['cropPercent'] for side in ('left', 'right', 'top', 'bottom')}
    else:
        edges = {side: values['crop' + side.title()] for side in ('left', 'right', 'top', 'bottom')}
    even = lambda value: int(math.floor(value / 2)) * 2
    active = any(edges.values())
    width = even(source_width * (1 - (edges['left'] + edges['right']) / 100)) if active else source_width
    height = even(source_height * (1 - (edges['top'] + edges['bottom']) / 100)) if active else source_height
    x = even((source_width - width) / 2 if mode == 'symmetric' else source_width * edges['left'] / 100) if active else 0
    y = even((source_height - height) / 2 if mode == 'symmetric' else source_height * edges['top'] / 100) if active else 0
    if min(width, height) < 2 or x + width > source_width or y + height > source_height:
        raise ValueError('裁切区域超出源视频')
    return {'mode': mode, 'x': x, 'y': y, 'width': width, 'height': height,
            'sourceWidth': source_width, 'sourceHeight': source_height, 'edges': edges,
            'retainedPercent': round(width * height / (source_width * source_height) * 100, 2),
            'filter': f'crop={width}:{height}:{x}:{y}' if active else ''}


def crop_filter(cfg, info):
    return crop_geometry(cfg, info)['filter']


def summary(cfg, info, seconds=None):
    values = validate(copy.deepcopy(cfg))
    duration = float(info.get('duration', 0) if seconds is None else seconds)
    return {'sourceWidth': int(info['width']), 'sourceHeight': int(info['height']),
            'outputWidth': int(cfg['width']), 'outputHeight': int(cfg['height']),
            'fps': 30, 'sourceSeconds': round(duration, 6),
            'outputSeconds': round(duration / values['speed'], 6), 'speed': values['speed'],
            'crop': crop_geometry(values, info), 'quality': values['encodeQuality'],
            'pictureProcessing': 'CPU滤镜', 'encodingRequested': 'GPU编码，按实际检测回退' if cfg.get('gpu') else 'CPU编码'}


def _stat(path):
    stat = Path(path).stat()
    return {'bytes': stat.st_size, 'mtimeNs': stat.st_mtime_ns}


def _validate_output(api, path, seconds, audio, jid):
    info = api.probe(path)
    if abs(info['duration'] - seconds) > max(.15, seconds * .01) or audio and not info.get('audio'):
        raise ValueError('画面试处理时长或音轨核验未通过，请查看任务日志')
    api.run_process([api.FFMPEG, '-hide_banner', '-v', 'error', '-i', str(path), '-f', 'null', '-'], jid, timeout=30)
    return info


def _metric(api, source, after, cfg, info, start, output_seconds, out, jid):
    """SSIM compares codec loss, holding the intentional transform constant."""
    stats = out / 'ssim-frames.txt'
    stats.unlink(missing_ok=True)
    graph = (f'[0:v]{api.filters(cfg, info, out)},format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[ref];'
             '[1:v]format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[dist];'
             '[dist][ref]ssim=stats_file=ssim-frames.txt:shortest=1:repeatlast=0[metric]')
    try:
        api.run_process([api.FFMPEG, '-hide_banner', '-v', 'error', '-nostdin', '-ss', str(start),
                         '-i', str(source), '-i', str(after), '-filter_complex_threads', '1',
                         '-filter_complex', graph, '-map', '[metric]', '-an', '-t', str(output_seconds),
                         '-f', 'null', '-'], jid, timeout=30, cwd=out)
        scores = [float(x) for x in re.findall(r'\bAll:([0-9.]+)', stats.read_text('utf-8'))]
        if not scores or any(not math.isfinite(x) for x in scores):
            raise ValueError('未收到有效画质帧指标')
        return {'status': 'completed', 'ssim': round(sum(scores) / len(scores), 6),
                'frames': len(scores), 'reference': '同一有意变换、最终编码前的参考画面',
                'purpose': '编码损失检查', 'platformScore': False,
                'note': '已对齐变速、裁切和调色；不是原片相似度或平台去重通过率。'}
    except (RuntimeError, OSError, ValueError):
        if api.JOBS[jid]['cancel'].is_set():
            raise InterruptedError('试处理已停止') from None
        return {'status': 'unavailable', 'purpose': '编码损失检查', 'platformScore': False,
                'note': '画质检测未完成；试处理视频已保留，可重新试处理。'}


def render_preview(api, p, cfg, jid):
    """Render a real source/result pair; no AI or full-series job is invoked."""
    cfg = validate(copy.deepcopy(cfg)); job = api.JOBS[jid]; options = job['options']
    video = p['videos'][options['videoIndex']]; source = Path(video['path'])
    original_stat = _stat(source)
    start, seconds = float(options['start']), float(options['seconds'])
    if not math.isfinite(start) or not math.isfinite(seconds) or start < 0 or not .05 <= seconds <= 10.001:
        raise ValueError('画面试处理时间范围无效')
    if start + seconds > float(video['duration']) + .05:
        raise ValueError('试处理范围超出源视频')
    if job['cancel'].is_set():
        raise InterruptedError('试处理已停止')
    out = api.project_dir(p, cfg) / '画面试处理' / jid
    out.mkdir(parents=True, exist_ok=True)
    before, after = out / '处理前.mp4', out / '处理后.mp4'
    result_fingerprint = fingerprint(cfg)
    old = job.get('transformPreviewResult')
    # Checkpoints belong to an exact source version, range and parameter set.
    # A retry may otherwise retain one side from an earlier comparison.
    identity = hashlib.sha256(json.dumps({'config': result_fingerprint, 'source': str(source.resolve()),
                              'stat': original_stat, 'start': start, 'seconds': seconds},
                             sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:24]
    before_key, after_key = p['id'] + ':transform-before:' + identity, p['id'] + ':transform-after:' + identity
    if old and old.get('cacheIdentity') == identity and api.cached(jid, before_key) and api.cached(jid, after_key):
        return old
    clean = cfg | {'speed': 1., 'cropPercent': 0., 'transformCropMode': 'symmetric',
                   'cropLeft': 0., 'cropRight': 0., 'cropTop': 0., 'cropBottom': 0.,
                   'brightness': 0., 'contrast': 1., 'saturation': 1., 'markAI': False}
    output_seconds = seconds / cfg['speed']
    for key, target, variant, label, progress in (
            (before_key, before, clean, '生成处理前参照', 10),
            (after_key, after, cfg, '生成实际变换结果', 45)):
        if api.cached(jid, key):
            continue
        api.stage(jid, label, progress)
        args = ['-ss', str(start), '-i', str(source)]
        if not video.get('audio'):
            args += ['-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000']
        duration = seconds / variant['speed']
        af = (f'atempo={variant["speed"]},' if variant['speed'] != 1 else '') + 'aresample=48000,apad'
        encoding = ['-c:v', 'libx264', '-preset', 'fast', '-crf', '18'] if target == before else api.encoder(cfg, jid)
        args += ['-map', '0:v:0', '-map', '0:a:0' if video.get('audio') else '1:a:0',
                 '-vf', api.filters(variant, video, out), '-af', af, *encoding, '-pix_fmt', 'yuv420p',
                 '-c:a', 'aac', '-ac', '2', '-ar', '48000', '-b:a', '128k', '-t', str(duration),
                 '-threads', '2', '-movflags', '+faststart', str(target)]
        if target == before:
            api.ff(args, jid)
        else:
            api.encode_media(args, jid)
        actual = _validate_output(api, target, duration, bool(video.get('audio')), jid)
        if actual['width'] != int(cfg['width']) or actual['height'] != int(cfg['height']):
            raise ValueError('试处理画幅与正式输出设置不一致')
        if _stat(source) != original_stat:
            raise ValueError('源视频在试处理过程中发生变化，请重新选择素材')
        api.register(p, target, '画面试处理参照' if target == before else '画面试处理结果', jid)
        api.checkpoint(jid, key, [target])
    api.stage(jid, '检查最终编码画质', 85)
    metrics = _metric(api, source, after, cfg, video, start, output_seconds, out, jid)
    if job['cancel'].is_set():
        raise InterruptedError('试处理已停止')
    if _stat(source) != original_stat:
        raise ValueError('源视频在试处理过程中发生变化，请重新选择素材')
    result = {'before': str(before), 'after': str(after), 'videoIndex': options['videoIndex'],
              'start': start, 'seconds': seconds, 'outputSeconds': round(output_seconds, 6),
              'speed': cfg['speed'], 'configFingerprint': result_fingerprint, 'cacheIdentity': identity,
              'configValues': values(cfg), 'sourcePath': str(source),
              'summary': summary(cfg, video, seconds), 'metrics': metrics,
              'sourceStat': original_stat, 'sourceUnchanged': True}
    job['transformPreviewResult'] = result
    job['result'] = result
    api.persist_jobs()
    return result
