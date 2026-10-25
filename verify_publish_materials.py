"""Real filesystem acceptance for local submission packages (no network)."""
from pathlib import Path
import base64
import copy
import json
import os
import struct
import sys
import tempfile
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'vendor'))
import publish_materials as m


def main():
    (ROOT / 'tmp').mkdir(exist_ok=True)
    base = Path(tempfile.mkdtemp(prefix='publish-materials-', dir=ROOT / 'tmp')).resolve()
    drama = base / '总资料' / '真实测试剧'
    drama.mkdir(parents=True)
    def chunk(kind, payload):
        return struct.pack('!I', len(payload)) + kind + payload + struct.pack('!I', zlib.crc32(kind + payload))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\xff\xff\xff')) + chunk(b'IEND', b'')
    checks = []

    def check(name, okay):
        if not okay:
            raise AssertionError(name)
        checks.append(name)

    def rejected(call):
        try:
            call()
        except ValueError:
            return True
        return False

    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return str(path)

    v2 = write(drama / '分集' / '第2集.mp4', b'filesystem fixture video two')
    v10 = write(drama / '分集' / '第10集.mp4', b'filesystem fixture video ten')
    write(drama / '详细简介.txt', '实际测试简介，资料由测试生成。'.encode('utf-8-sig'))
    write(drama / '总集数.txt', b'2')
    write(drama / '制作成本.txt', '1.5万元'.encode())
    write(drama / '制作方.txt', '测试工作室'.encode())
    cover = write(drama / '封面.png', png)
    proof = write(drama / '工程记录' / '真实记录.png', png)
    story = [write(drama / 'fenjing' / f'源帧_{i}.png', png) for i in range(4)]
    cost_image = write(drama / 'zhengming' / '实际成本比例.png', png)
    report = write(drama / '成本报告.csv', '项目,金额\n制作,15000\n'.encode('utf-8-sig'))
    # Known material subdirectories must not become separate drama entries.
    write(drama / '工程记录' / '误放样片.mp4', b'ignored nested video')
    rows = m.discover(base / '总资料')
    check('总目录只识别一部剧，不把分集及工程记录当独立剧目', len(rows) == 1 and rows[0]['folder'] == str(drama))
    check('直接选择单剧目录仍只得到一部', len(m.discover(drama)) == 1)
    plan = m.inspect_folder(drama)
    check('成本文本万元明确转换为元', plan['fields']['totalCostYuan'] == 15000)
    check('已有视频按自然集数排序', [x['name'] for x in plan['files']['videos']] == ['第2集.mp4', '第10集.mp4'])
    check('历史目录不能默认为已授权', not plan['ready'] and not plan['fields']['rightsConfirmed'])
    write(drama / '已经发布成功.txt', b'old marker')
    marked = m.inspect_folder(drama, overrides={'rightsConfirmed': True})
    check('旧成功标记不被当作平台成功且不跳过', not marked['platformSubmitted'] and any('历史成功标记' in s for s in marked['warnings']))
    check('完整资料经本人授权后本地检测通过', marked['ready'])
    internal = {'id': 'internal', 'name': '内部项目', 'intro': '实际简介', 'rights': True,
                'videos': [{'path': v2}], 'publishVideos': [], 'cover': cover,
                'artifacts': [{'kind': '分轨工程图', 'path': proof}]}
    opts = {'producer': '测试工作室', 'totalCostYuan': 1000, 'proofImages': [proof],
            'storyboardImages': story, 'costImages': [cost_image], 'costReportPaths': [report]}
    internal_plan = m.inspect(internal, {}, opts)
    check('原始源视频不会冒充正片成品', not internal_plan['files']['videos'] and not internal_plan['ready'])
    implicit = m.inspect({k: v for k, v in internal.items() if k != 'publishVideos'}, {}, {})
    check('分轨仿真图不会自动当剪映工程证明', not implicit['files']['proofImages'])
    missing = m.inspect_folder(drama, overrides={'rightsConfirmed': True, 'coverPath': str(drama / '不存在.png')})
    check('指定缺失附件导致失败，不静默回退另一封面', not missing['ready'] and missing['files']['cover'] is None)
    empty = write(drama / 'empty.png', b'')
    empty_plan = m.inspect_folder(drama, overrides={'rightsConfirmed': True, 'coverPath': empty})
    check('空图片被拒绝', not empty_plan['ready'] and any('文件为空' in x for x in empty_plan['errors']))
    disguised = write(drama / '伪装.png', b'not an image')
    disguised_plan = m.inspect_folder(drama, overrides={'rightsConfirmed': True, 'coverPath': disguised})
    check('仅改扩展名的假图片无法通过检查', not disguised_plan['ready'] and disguised_plan['files']['cover'] is None)
    sensitive = write(base / '.ssh' / 'account.png', png)
    bad = m.inspect_folder(drama, overrides={'rightsConfirmed': True, 'proofImages': [sensitive]})
    check('拒绝密钥或系统目录伪装图片', not bad['ready'] and any('账号资料' in x for x in bad['errors']))
    bad_type = m.inspect_folder(drama, overrides={'rightsConfirmed': True, 'costReportPaths': [cover]})
    check('附件类型必须匹配用途', not bad_type['ready'])
    bad_count = m.inspect_folder(drama, overrides={'rightsConfirmed': True, 'episodeCount': 5, 'trialEpisodes': 7})
    check('集数与试看范围均核对', not bad_count['ready'] and len([c for c in bad_count['checks'] if c['key'] in ('episodeCount', 'trialEpisodes') and c['status'] == 'missing']) == 2)
    probe_calls = []
    def probe(path):
        probe_calls.append(path)
        return {'duration': 2.0, 'width': 640, 'height': 360}
    m.inspect_folder(drama, overrides={'rightsConfirmed': True}, probe=probe)
    m.inspect_folder(drama, overrides={'rightsConfirmed': True}, probe=probe)
    check('重复检测复用按路径与文件stat缓存的视频探测', len(probe_calls) == 2)
    Path(v2).write_bytes(b'changed fixture video')
    m.inspect_folder(drama, overrides={'rightsConfirmed': True}, probe=probe)
    check('视频变化使对应探测缓存失效', len(probe_calls) == 3)
    Path(v2).write_bytes(b'filesystem fixture video two')
    stamped = dict(internal)
    stamped['publishVideos'] = [{'path': v2, 'bytes': Path(v2).stat().st_size, 'mtimeNs': Path(v2).stat().st_mtime_ns,
                                'duration': 3, 'width': 320, 'height': 240}]
    before_calls = len(probe_calls)
    preknown = m.inspect(stamped, {}, opts, probe=probe)
    check('带相同stat的可信媒体元信息直接复用', len(probe_calls) == before_calls and preknown['files']['videos'][0]['duration'] == 3)
    marked = m.inspect_folder(drama, overrides={'rightsConfirmed': True})
    source_files = [Path(f['path']) for group in marked['files'].values() for f in ([group] if isinstance(group, dict) else group or [])]
    original_hashes = {str(p): m.digest(p) for p in source_files}
    destination = base / '独立导出'
    destination.mkdir()
    exported = m.export_packet(marked, destination)
    manifest = json.loads(Path(exported['manifest']).read_text('utf-8'))
    check('实际复制包文件哈希逐一一致', all(m.digest(Path(exported['directory']) / f['name']) == f['sha256'] for f in manifest['files']))
    check('导出未改源文件', all(m.digest(p) == h for p, h in original_hashes.items()))
    check('导出不创建成功标记或平台通过声明', not (Path(exported['directory']) / '已经发布成功.txt').exists() and not manifest['platformSubmitted'] and not manifest['platformApproved'])
    another = m.export_packet(marked, destination)
    check('重复导出创建独立目录不覆盖', another['directory'] != exported['directory'] and Path(exported['manifest']).is_file())
    reimported = m.inspect_folder(exported['directory'], overrides={'rightsConfirmed': True})
    check('本软件资料包可按相对清单重新识别完整附件', reimported['ready'] and len(reimported['files']['proofImages']) == 1)
    corrupted = json.loads(Path(another['manifest']).read_text('utf-8'))
    corrupted['files'][0]['name'] = '../越界.mp4'
    Path(another['manifest']).write_text(json.dumps(corrupted), 'utf-8')
    check('拒绝资料包清单路径越界', rejected(lambda: m.inspect_folder(another['directory'])))
    check('拒绝导出到附件源目录内', rejected(lambda: m.export_packet(marked, drama / '分集')))
    tampered = copy.deepcopy(marked)
    tampered['fields']['title'] = '被修改'
    check('检测快照发生修改必须重新检查', rejected(lambda: m.export_packet(tampered, destination)))
    Path(proof).write_bytes(png + b'changed')
    check('检测后附件变化被拒绝且清理未完成包', rejected(lambda: m.export_packet(marked, destination)) and len(list(destination.iterdir())) == 2)
    Path(proof).write_bytes(png)
    current = m.inspect_folder(drama, overrides={'rightsConfirmed': True})
    with patch.object(m.shutil, 'disk_usage', return_value=m.shutil.disk_usage(destination)._replace(free=1)):
        check('空间不足在复制前报错', rejected(lambda: m.export_packet(current, destination)))
    cancelled = [False]
    ticks = []
    def progress(done, total, name):
        ticks.append((done, total, name))
        cancelled[0] = True
    interrupted = False
    try:
        m.export_packet(current, destination, cancel=lambda: cancelled[0], progress=progress)
    except InterruptedError:
        interrupted = True
    check('导出提供真实字节进度并支持取消及清理', interrupted and ticks and ticks[0][0] > 0 and len(list(destination.iterdir())) == 2)
    output = {'passed': len(checks), 'checks': checks, 'base': str(base),
              'scope': 'filesystem-and-policy; fixture videos intentionally not media-decoded',
              'packet': exported['directory'], 'platformSubmitted': False}
    (base / 'report.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), 'utf-8')
    (ROOT / 'tmp/publish-materials-latest.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), 'utf-8')
    print(json.dumps({'passed': len(checks), 'report': str(base / 'report.json')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
