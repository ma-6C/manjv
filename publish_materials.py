"""Local drama submission inventory. No platform requests or approval claims.

The completeness policy below is an editable preparation plan, not a declaration
of the platform's current rules. Only explicitly selected files enter a packet.
"""
from __future__ import annotations
import copy
from collections import OrderedDict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import threading
import uuid
import zipfile

VERSION = 1
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.webp'}
VIDEO_EXT = {'.mp4', '.mov', '.mkv', '.m4v', '.webm', '.avi', '.ts'}
REPORT_EXT = {'.pdf', '.docx', '.csv'}
MAX_ATTACHMENTS = 2000
MAX_SMALL_TEXT = 100_000
_PROBE_CACHE = OrderedDict()
_PROBE_LOCK = threading.Lock()
MATERIAL_DIRS = {'分集', '工程记录', '工程图', '分轨工程图', '剪映工程', 'jy', 'fenjing', 'zhengming',
                 'yiquchong', 'qiepian', '切片', '封面', '源帧', '上传回执', '提审资料', '成本报告',
                 '版权证明', '分镜', '分镜截图', '正片', 'videos', 'proof', 'storyboards', 'cost', 'copyright'}
TEXT_NAMES = {'synopsis': ('详细简介.txt', '简介.txt'), 'episodeCount': ('总集数.txt',),
              'totalCostYuan': ('制作成本.txt',), 'producer': ('制作方.txt',)}


def natural(value):
    return [int(v) if v.isdigit() else v.casefold() for v in re.split(r'(\d+)', str(value))]


def _cancel(cancel):
    if cancel and cancel():
        raise InterruptedError('资料导出已停止')


def digest(path, cancel=None):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            _cancel(cancel)
            h.update(chunk)
    return h.hexdigest()


def _text(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_SMALL_TEXT:
        return ''
    raw = path.read_bytes()
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding).strip()
        except UnicodeError:
            continue
    return ''


def _sensitive(path):
    names = {p.casefold() for p in path.parts}
    forbidden = {'.ssh', '.aws', '.codex', '.git', 'windows', 'program files', 'program files (x86)',
                 'upload-cookies', 'cookies', 'browser-profiles', 'accounts'}
    if names & forbidden:
        return True
    lowered = path.name.casefold()
    return lowered in {'state.json', 'jobs.json', 'accounts.json', '.env', 'license.bin'} or any(
        x in lowered for x in ('cookie', 'issuer-key', 'private_key', '密钥', '授权码'))


def _file(value, extensions, *, maximum):
    raw = value.get('path', '') if isinstance(value, dict) else value
    if not isinstance(raw, (str, os.PathLike)) or not str(raw).strip():
        raise ValueError('附件路径为空')
    original = Path(raw).expanduser()
    if not original.is_absolute():
        raise ValueError('附件必须使用本机绝对路径')
    path = original.resolve()
    if _sensitive(path) or _sensitive(original):
        raise ValueError('该路径可能包含系统或账号资料，不能作为提审附件')
    if path.suffix.lower() not in extensions:
        raise ValueError('附件格式不支持：' + path.name)
    if not path.is_file():
        raise ValueError('文件不存在：' + path.name)
    st = path.stat()
    if not 0 < st.st_size <= maximum:
        raise ValueError('文件为空或超过本地附件大小限制：' + path.name)
    item = {'path': str(path), 'name': path.name, 'bytes': st.st_size, 'mtimeNs': st.st_mtime_ns}
    if path.suffix.lower() in IMAGE_EXT:
        try:
            from PIL import Image
            with Image.open(path) as image:
                if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 100_000_000:
                    raise ValueError('图片格式或尺寸不支持')
                item.update(width=image.width, height=image.height)
                image.verify()
        except (ImportError, OSError, SyntaxError, ValueError) as error:
            raise ValueError('图片无法验证：' + path.name) from error
    elif path.suffix.lower() == '.docx':
        try:
            with zipfile.ZipFile(path) as archive:
                if not {'[Content_Types].xml', 'word/document.xml'}.issubset(archive.namelist()):
                    raise ValueError('不是有效的Word文档')
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            raise ValueError('Word报告无法读取：' + path.name) from error
    elif path.suffix.lower() == '.pdf':
        with path.open('rb') as stream:
            if not stream.read(8).startswith(b'%PDF-'):
                raise ValueError('PDF报告文件头无效：' + path.name)
    elif path.suffix.lower() == '.csv':
        with path.open('rb') as stream:
            if b'\x00' in stream.read(4096):
                raise ValueError('CSV报告包含异常二进制内容：' + path.name)
    return item


def _list(values, extensions, maximum, problems, label, probe=None):
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ATTACHMENTS:
        problems.append(label + '附件清单无效或数量过多')
        return []
    files, seen = [], set()
    for value in values:
        try:
            item = _file(value, extensions, maximum=maximum)
            identity = os.path.normcase(item['path'])
            if identity in seen:
                continue
            if probe:
                cache_key = (id(probe), identity, item['bytes'], item['mtimeNs'])
                with _PROBE_LOCK:
                    metadata = _PROBE_CACHE.get(cache_key)
                    if metadata is not None:
                        _PROBE_CACHE.move_to_end(cache_key)
                if metadata is None:
                    known = value if isinstance(value, dict) else {}
                    same_stamp = known.get('mtimeNs') == item['mtimeNs'] or (
                        isinstance(known.get('mtime'), (float, int)) and abs(known['mtime'] - Path(item['path']).stat().st_mtime) < .000001)
                    if same_stamp and known.get('bytes') == item['bytes'] and float(known.get('duration', 0)) > 0:
                        metadata = {k: known[k] for k in ('duration', 'width', 'height', 'fps', 'codec', 'audio') if k in known}
                    else:
                        metadata = probe(item['path'])
                    if isinstance(metadata, dict) and float(metadata.get('duration', 0)) > 0:
                        with _PROBE_LOCK:
                            _PROBE_CACHE[cache_key] = copy.deepcopy(metadata)
                            while len(_PROBE_CACHE) > 4096:
                                _PROBE_CACHE.popitem(last=False)
                if not isinstance(metadata, dict) or not float(metadata.get('duration', 0)) > 0:
                    raise ValueError('视频无法读取或时长为0：' + item['name'])
                item.update({k: metadata[k] for k in ('duration', 'width', 'height', 'fps', 'codec', 'audio') if k in metadata})
            seen.add(identity)
            files.append(item)
        except (OSError, ValueError, TypeError, RuntimeError, subprocess.TimeoutExpired) as error:
            problems.append(label + '：' + str(error))
    return sorted(files, key=lambda f: natural(f['name']))


def _positive(value, maximum, integer=False):
    try:
        if isinstance(value, bool):
            return None
        number = float(value)
        if not math.isfinite(number) or not 0 < number <= maximum or (integer and not number.is_integer()):
            return None
        return int(number) if integer else round(number, 2)
    except (ValueError, TypeError, OverflowError):
        return None


def _small_string(value, maximum):
    return value.strip()[:maximum] if isinstance(value, str) else ''


def _paths_from_artifacts(project, kinds, extensions):
    return [a['path'] for a in project.get('artifacts', []) if isinstance(a, dict)
            and a.get('kind') in kinds and isinstance(a.get('path'), str)
            and Path(a['path']).suffix.lower() in extensions]


def _official_proof_images(project, selected, problems, warnings):
    """Use only server-registered, confirmed official-window captures.

    ``project.artifacts`` comes from the local server registry, never from a
    packet manifest or a client's selected filename. This validates provenance
    and current image bytes, not copyright or platform acceptance.
    """
    kinds = {'剪映工程截图': 'jianying', '即梦工程截图': 'jimeng'}
    artifacts = [a for a in project.get('artifacts', []) if isinstance(a, dict)
                 and a.get('kind') in kinds and isinstance(a.get('path'), str)]
    automatic = selected is None
    values = [a['path'] for a in artifacts] if automatic else selected
    if not isinstance(values, (list, tuple)) or len(values) > MAX_ATTACHMENTS:
        problems.append('工程证明图附件清单无效或数量过多')
        return []
    registered = {}
    for artifact in artifacts:
        try:
            identity = os.path.normcase(str(Path(artifact['path']).expanduser().resolve()))
            registered.setdefault(identity, []).append(artifact)
        except (OSError, ValueError):
            continue
    files, seen = [], set()
    for value in values:
        try:
            item = _file(value, IMAGE_EXT, maximum=100 * 1024**2)
            identity = os.path.normcase(item['path'])
            if identity in seen:
                continue
            provenance = None
            for artifact in registered.get(identity, []):
                evidence = artifact.get('officialEvidence')
                if not isinstance(evidence, dict):
                    continue
                stamp = evidence.get('sha256')
                if (evidence.get('source') == 'window_capture'
                        and evidence.get('platform') == kinds[artifact['kind']]
                        and evidence.get('appVerified') is True
                        and evidence.get('projectConfirmedByUser') is True
                        and isinstance(stamp, str)
                        and re.fullmatch(r'[a-fA-F0-9]{64}', stamp)):
                    actual = digest(item['path'])
                    if actual == stamp.lower():
                        provenance = {key: evidence[key] for key in (
                            'source', 'platform', 'appVerified', 'sha256', 'projectConfirmedByUser')}
                        provenance['sha256'] = actual
                        break
            if provenance is None:
                raise ValueError('未登记为已核验官方窗口截图，请从工程页采集：' + item['name'])
            item['officialEvidence'] = provenance
            files.append(item)
            seen.add(identity)
        except (OSError, ValueError, TypeError) as error:
            (warnings if automatic else problems).append('工程证明图：' + str(error))
    return sorted(files, key=lambda f: natural(f['name']))


def inspect(project, config=None, overrides=None, probe=None):
    """Inspect real selected artifacts; readiness means local completeness only."""
    config, overrides = config or {}, overrides or {}
    if not isinstance(project, dict) or not isinstance(config, dict) or not isinstance(overrides, dict):
        raise ValueError('提审资料配置无效')
    fields = {
        'title': _small_string(overrides.get('title', project.get('name', '')), 100),
        'synopsis': _small_string(overrides.get('synopsis', project.get('intro', '')), 20000),
        'producer': _small_string(overrides.get('producer', ''), 200),
        'trialEpisodes': _positive(overrides.get('trialEpisodes', 1), 10000, True),
        'dramaType': overrides.get('dramaType', 'animation'),
        'episodeCount': _positive(overrides.get('episodeCount', len(project.get('publishVideos', []))), 10000, True),
        'totalCostYuan': _positive(overrides.get('totalCostYuan'), 1e12),
        'rightsConfirmed': overrides.get('rightsConfirmed', project.get('rights', False)) is True,
    }
    errors, warnings = [], []
    if fields['dramaType'] not in ('animation', 'digital'):
        errors.append('剧目类型无效，请选择漫剧或数字真人')
    files = {}
    # Sources are never silently substituted for final outputs.
    video_candidates = project.get('publishVideos', _paths_from_artifacts(project, {'视频'}, VIDEO_EXT))
    files['videos'] = _list(video_candidates, VIDEO_EXT, 100 * 1024**3, errors, '正片', probe)
    fields['episodeCount'] = _positive(overrides.get('episodeCount', len(files['videos'])), 10000, True)
    cover = overrides.get('coverPath', '')
    if not cover:
        covers = _paths_from_artifacts(project, {'封面'}, IMAGE_EXT)
        cover = covers[-1] if covers else project.get('cover', '')
    files['cover'] = None
    if cover:
        try:
            files['cover'] = _file(cover, IMAGE_EXT, maximum=100 * 1024**2)
        except (OSError, ValueError, TypeError) as error:
            errors.append('封面：' + str(error))
    files['proofImages'] = _official_proof_images(project, overrides.get('proofImages'), errors, warnings)
    mappings = {
        'storyboardImages': ({'源帧', '分镜截图', '分镜'}, IMAGE_EXT, '分镜截图'),
        'costImages': ({'成本报告图片', '成本比例图'}, IMAGE_EXT, '成本报告图片'),
        'copyrightImages': ({'版权证明', '授权证明'}, IMAGE_EXT, '授权证明附件'),
        'costReportPaths': ({'成本报告'}, REPORT_EXT, '成本报告文档'),
    }
    for key, (kinds, extensions, label) in mappings.items():
        values = overrides.get(key, _paths_from_artifacts(project, kinds, extensions))
        files['costReports' if key == 'costReportPaths' else key] = _list(values, extensions, 100 * 1024**2, errors, label)
    checks = []

    def check(key, label, okay, message, *, warn=False, paths=None, action=None):
        status = 'ready' if okay else 'warning' if warn else 'missing'
        checks.append({'key': key, 'label': label, 'status': status, 'message': message,
                       'paths': paths or [], 'action': action or key})
        if not okay:
            (warnings if warn else errors).append(label + '：' + message)

    check('title', '剧名', bool(fields['title']), fields['title'] or '请填写剧名')
    check('synopsis', '详细简介', bool(fields['synopsis']), '已填写' if fields['synopsis'] else '请填写实际剧情简介')
    check('producer', '制作方', bool(fields['producer']), fields['producer'] or '请填写制作方名称')
    count = fields['episodeCount']
    count_ok = bool(count) and count == len(files['videos'])
    check('episodeCount', '总集数', count_ok, f'填写 {count or 0} 集，检测到 {len(files["videos"])} 个正片文件' if not count_ok else f'{count} 集，与正片数量一致')
    trial = fields['trialEpisodes']
    trial_ok = bool(trial) and bool(count) and trial <= count
    check('trialEpisodes', '试看集数', trial_ok, f'{trial} 集' if trial_ok else '请输入不超过总集数的正整数')
    check('totalCostYuan', '制作成本', bool(fields['totalCostYuan']), f'{fields["totalCostYuan"]:,.2f} 元' if fields['totalCostYuan'] else '请填写经核实的实际制作成本（元）')
    check('cover', '封面', bool(files['cover']), '已找到本地封面' if files['cover'] else '请选择封面图片', paths=[files['cover']['path']] if files['cover'] else [])
    check('proofImages', '官方工程截图', bool(files['proofImages']), f'{len(files["proofImages"])} 张，已核对官方窗口来源、本人关联确认及图片哈希；平台适用性需另行核对' if files['proofImages'] else '未登记为已核验官方窗口截图，请从工程页采集剪映或即梦实际界面', paths=[a['path'] for a in files['proofImages']])
    check('costReports', '成本报告文档', bool(files['costReports']), f'{len(files["costReports"])} 份' if files['costReports'] else '请先生成或补充成本报告文档', paths=[a['path'] for a in files['costReports']])
    check('costImages', '成本报告图片', bool(files['costImages']), f'{len(files["costImages"])} 张' if files['costImages'] else '请补充实际成本报告或比例表图片；Word/CSV未自动当作图片', paths=[a['path'] for a in files['costImages']])
    storyboard_min = _positive(config.get('publishStoryboardMin', 4), 100, True) or 4
    check('storyboardImages', '分镜截图', len(files['storyboardImages']) >= storyboard_min,
          f'{len(files["storyboardImages"])} 张；本地准备方案要求至少 {storyboard_min} 张，实际要求以后台为准', paths=[a['path'] for a in files['storyboardImages']])
    check('rightsConfirmed', '素材授权确认', fields['rightsConfirmed'], '已由使用者确认制作与发布授权' if fields['rightsConfirmed'] else '请本人确认具有制作与发布所需授权')
    check('copyrightImages', '授权证明附件', bool(files['copyrightImages']), f'{len(files["copyrightImages"])} 张' if files['copyrightImages'] else '尚未添加；如后台要求，请补充真实授权证明', warn=True, paths=[a['path'] for a in files['copyrightImages']])
    check('videos', '正片文件', bool(files['videos']), f'{len(files["videos"])} 个，按文件名自然排序' if files['videos'] else '未找到明确成片；源视频不会自动视为已完成正片', paths=[a['path'] for a in files['videos']])
    if files['proofImages']:
        warnings.append('官方窗口截图来源及文件完整性核验不代表版权、完整制作过程或平台审核认可')
    if any(a.get('kind') in {'工程记录', '分轨工程图', '待核对工程截图'} for a in project.get('artifacts', []) if isinstance(a, dict)):
        warnings.append('历史拼接制作记录、分轨布局图及手动导入图片不计入已核验官方工程截图')
    if fields['dramaType'] == 'digital':
        warnings.append('数字真人的演员、肖像及其他后台必填资料需在官方页面逐项核对')
    plan = {'version': VERSION, 'projectId': str(project.get('id', '')), 'title': fields['title'],
            'folder': str(project.get('source', project.get('path', ''))), 'fields': fields,
            'files': files, 'checks': checks, 'errors': list(dict.fromkeys(errors)),
            'warnings': list(dict.fromkeys(warnings)), 'ready': not errors, 'inspectedAt': time.time(),
            'scope': 'local-completeness', 'platformSubmitted': False, 'platformApproved': False}
    plan['fingerprint'] = _fingerprint(plan)
    return plan


def _fingerprint(plan):
    return hashlib.sha256(json.dumps({'version': VERSION, 'fields': plan['fields'], 'files': plan['files']},
                                     ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _metadata(folder):
    result = {}
    for key, names in TEXT_NAMES.items():
        for name in names:
            text = _text(folder / name)
            if text:
                if key == 'episodeCount':
                    match = re.fullmatch(r'\s*(\d+)\s*集?\s*', text)
                    result[key] = int(match.group(1)) if match else text
                elif key == 'totalCostYuan':
                    match = re.fullmatch(r'\s*([\d,.]+)\s*(元|万元|万)?\s*', text)
                    if match:
                        try:
                            result[key] = float(match.group(1).replace(',', '')) * (10000 if match.group(2) in ('万', '万元') else 1)
                        except ValueError:
                            result[key] = text
                    else:
                        result[key] = text
                else:
                    result[key] = text
                break
    for name in ('提审清单.json', '剧集信息.json', 'manifest.json'):
        raw = _text(folder / name)
        if not raw:
            continue
        try:
            manifest = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(manifest, dict):
            continue
        fields = manifest.get('fields', manifest)
        if isinstance(fields, dict):
            for key in ('title', 'synopsis', 'producer', 'episodeCount', 'trialEpisodes', 'totalCostYuan', 'dramaType'):
                if key in fields:
                    result.setdefault(key, fields[key])
        break
    return result


def _known_files(folder, names, extensions):
    found = []
    for name in names:
        directory = folder / name
        if directory.is_dir() and not directory.is_symlink():
            # Bound traversal: production jobs commonly add one job subdirectory.
            found.extend(p for p in directory.glob('*') if p.is_file() and p.suffix.lower() in extensions)
            found.extend(p for p in directory.glob('*/*') if p.is_file() and p.suffix.lower() in extensions)
    return sorted(set(found), key=natural)[:MAX_ATTACHMENTS]


def _packet_inventory(root):
    raw = _text(root / 'manifest.json')
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    if not isinstance(value, dict) or value.get('format') != 'ManjuSubmissionPacket' or value.get('version') != VERSION:
        return {}
    groups = {'videos', 'cover', 'proofImages', 'storyboardImages', 'costImages', 'copyrightImages', 'costReports'}
    entries = value.get('files', [])
    if not isinstance(entries, list) or len(entries) > MAX_ATTACHMENTS:
        raise ValueError('资料包清单条目无效或数量过多')
    found = {group: [] for group in groups}
    for item in entries:
        if not isinstance(item, dict) or item.get('group') not in groups or not isinstance(item.get('name'), str):
            raise ValueError('资料包清单存在无效附件条目')
        relative = Path(item['name'])
        path = (root / relative).resolve()
        if relative.is_absolute() or not path.is_relative_to(root) or len(relative.parts) > 4:
            raise ValueError('资料包清单包含越界附件路径')
        found[item['group']].append(str(path))
    return found


def inspect_folder(folder, config=None, overrides=None, probe=None):
    root = Path(folder).expanduser().resolve()
    if not root.is_dir() or _sensitive(root):
        raise ValueError('请选择可读取的剧目资料文件夹')
    metadata = _metadata(root)
    videos = _known_files(root, ('yiquchong', '正片', '分集', 'videos'), VIDEO_EXT)
    videos += [p for p in root.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    artifacts = []
    groups = [('待核对工程截图', ('jy', '工程记录', 'proof'), IMAGE_EXT),
              ('源帧', ('fenjing', '分镜', '分镜截图', 'storyboards'), IMAGE_EXT),
              ('成本报告图片', ('zhengming', '成本报告', 'cost'), IMAGE_EXT),
              ('成本报告', ('成本报告', 'cost'), REPORT_EXT),
              ('版权证明', ('版权证明', 'copyright'), IMAGE_EXT)]
    for kind, names, extensions in groups:
        artifacts += [{'kind': kind, 'path': str(p)} for p in _known_files(root, names, extensions)]
    artifacts += [{'kind': '成本报告', 'path': str(p)} for p in root.iterdir() if p.is_file() and p.suffix.lower() in REPORT_EXT and '成本' in p.name]
    cover = next((root / n for n in ('封面.jpg', '封面图.jpg', '封面.png', '封面图.png', 'cover.jpg', 'cover.png') if (root / n).is_file()), None)
    project = {'id': hashlib.sha256(str(root).casefold().encode()).hexdigest()[:16], 'name': metadata.get('title', root.name),
               'source': str(root), 'intro': metadata.get('synopsis', ''), 'cover': str(cover) if cover else '',
               'rights': False, 'publishVideos': [str(p) for p in videos], 'artifacts': artifacts}
    packet = _packet_inventory(root)
    if packet:
        project['publishVideos'] = packet['videos']
        metadata['coverPath'] = next(iter(packet['cover']), '')
        for key in ('proofImages', 'storyboardImages', 'costImages', 'copyrightImages'):
            metadata[key] = packet[key]
        metadata['costReportPaths'] = packet['costReports']
    # A local success marker is not a platform receipt and does not confer rights.
    plan = inspect(project, config, metadata | (overrides or {}), probe)
    if packet:
        plan['warnings'].append('已按本软件资料包清单重新检查文件；导出清单本身不是平台提交或授权凭证')
        plan['warnings'].append('资料包内的截图来源声明不会继承为本机已核验记录；请在工程页重新采集并确认')
    if (root / '已经发布成功.txt').exists():
        plan['warnings'].append('目录含历史成功标记；本次未据此判断已提交或跳过，需核对账号及平台回执')
    return plan


def discover(root):
    """Find drama roots, never turn known material subfolders into dramas."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir() or _sensitive(root):
        raise ValueError('剧目总文件夹不存在或不可读取')

    def candidate(folder):
        metadata = _metadata(folder)
        direct_videos = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXT]
        nested = _known_files(folder, ('yiquchong', '正片', '分集', 'videos'), VIDEO_EXT)
        if not metadata and not direct_videos and not nested:
            return None
        return {'folder': str(folder), 'title': metadata.get('title', folder.name),
                'hasMetadata': bool(metadata), 'videoCount': len(set(direct_videos + nested)),
                'warning': '仅识别资料位置；尚未核对内容、授权或平台提交结果'}

    own = candidate(root)
    # Metadata marks a drama root even if its videos have not been generated yet.
    if own and (own['hasMetadata'] or root.name.casefold() not in MATERIAL_DIRS):
        children = [p for p in root.iterdir() if p.is_dir() and p.name.casefold() not in MATERIAL_DIRS and not p.is_symlink()]
        child_rows = [row for p in sorted(children, key=natural)[:500] if (row := candidate(p))]
        return [own] if own['hasMetadata'] or not child_rows else child_rows
    rows = []
    for folder in sorted(root.iterdir(), key=natural):
        if not folder.is_dir() or folder.is_symlink() or folder.name.casefold() in MATERIAL_DIRS or folder.name.startswith('.'):
            continue
        row = candidate(folder)
        if row:
            rows.append(row)
        if len(rows) >= 500:
            break
    return rows


def export_packet(plan, destination, *, cancel=None, progress=None):
    """Copy a validated snapshot to a fresh folder; never mark it published."""
    if not isinstance(plan, dict) or plan.get('version') != VERSION or plan.get('fingerprint') != _fingerprint(plan):
        raise ValueError('资料清单已变化，请重新检查')
    if not plan.get('ready') or plan.get('errors'):
        raise ValueError('资料尚有缺项，请补齐并重新检查后导出')
    parent = Path(destination).expanduser().resolve()
    if _sensitive(parent) or not parent.is_dir():
        raise ValueError('请选择已存在的独立导出文件夹')
    source_folders = [Path(f['path']).parent for group in plan['files'].values() for f in ([group] if isinstance(group, dict) else group or [])]
    if any(parent == p or parent.is_relative_to(p) for p in source_folders):
        raise ValueError('导出目录不能放在本次附件所在目录内，请选择独立目录')
    source_root = Path(plan.get('folder', '')).resolve() if plan.get('folder') else None
    if source_root and (parent == source_root or parent.is_relative_to(source_root)):
        raise ValueError('导出目录不能位于本剧源资料目录内，请选择独立目录')
    total_bytes = sum(f['bytes'] for group in plan['files'].values() for f in ([group] if isinstance(group, dict) else group or []))
    if shutil.disk_usage(parent).free < total_bytes + max(16 * 1024**2, total_bytes // 20):
        raise ValueError('导出磁盘空间不足，需保留资料总大小及校验余量')
    _cancel(cancel)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', plan['title']).strip('. ')[:70] or '剧目'
    directory = parent / (title + '_提审资料_' + time.strftime('%Y%m%d-%H%M%S') + '_' + uuid.uuid4().hex[:6])
    directory.mkdir()
    manifest = {'format': 'ManjuSubmissionPacket', 'version': VERSION, 'scope': 'prepared-only',
                'projectId': plan.get('projectId'), 'fields': copy.deepcopy(plan['fields']),
                'fingerprint': plan['fingerprint'], 'createdAt': time.time(), 'files': [],
                'platformSubmitted': False, 'platformApproved': False,
                'note': '本地资料准备结果；未执行官方发布或审核。图片真实性由提交人核对。'}
    try:
        done_bytes = 0
        for group, values in plan['files'].items():
            items = [values] if isinstance(values, dict) else values or []
            for index, item in enumerate(items, 1):
                _cancel(cancel)
                source = Path(item['path'])
                extensions = VIDEO_EXT if group == 'videos' else REPORT_EXT if group == 'costReports' else IMAGE_EXT
                current = _file(str(source), extensions, maximum=100 * 1024**3 if group == 'videos' else 100 * 1024**2)
                if (current['bytes'], current['mtimeNs']) != (item['bytes'], item['mtimeNs']):
                    raise ValueError('附件已被修改，请重新检查：' + item['name'])
                target = directory / group / f'{index:03d}_{source.name}'
                target.parent.mkdir(exist_ok=True)
                # Hash while streaming the copy: avoid extra full source reads
                # for large seasons, while checking the destination separately.
                content = hashlib.sha256()
                with source.open('rb') as src, target.open('xb') as dst:
                    for chunk in iter(lambda: src.read(4 * 1024**2), b''):
                        _cancel(cancel)
                        dst.write(chunk)
                        content.update(chunk)
                        done_bytes += len(chunk)
                        if progress:
                            progress(done_bytes, total_bytes, source.name)
                after = source.stat()
                before = content.hexdigest()
                if (after.st_size, after.st_mtime_ns) != (item['bytes'], item['mtimeNs']) or digest(target, cancel) != before:
                    raise ValueError('复制校验失败或源文件变化：' + source.name)
                shutil.copystat(source, target)
                entry = {'group': group, 'name': target.relative_to(directory).as_posix(),
                         'bytes': current['bytes'], 'sha256': before}
                if group == 'proofImages':
                    evidence = item.get('officialEvidence')
                    if not isinstance(evidence, dict) or evidence.get('sha256') != before:
                        raise ValueError('官方截图来源与文件不一致，请从工程页重新采集')
                    entry['officialEvidence'] = copy.deepcopy(evidence)
                    entry['provenanceTrust'] = 'revalidate-against-local-registry-on-import'
                manifest['files'].append(entry)
        path = directory / 'manifest.json'
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), 'utf-8')
        (directory / '提交前核对.txt').write_text('本目录为本地资料准备包，未执行平台提交。\n请在官方后台核对剧名、集数、制作方、成本、授权与附件，再由本人确认提交。\n资料齐全不代表审核通过。\n', 'utf-8-sig')
        return {'directory': str(directory), 'manifest': str(path), 'path': str(path),
                'fingerprint': plan['fingerprint'], 'count': len(manifest['files']), 'files': manifest['files'],
                'platformSubmitted': False}
    except Exception:
        # This is a newly-created directory checked to remain under the destination.
        if directory.resolve().is_relative_to(parent):
            shutil.rmtree(directory)
        raise
