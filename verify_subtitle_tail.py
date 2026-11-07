"""Subtitle tail settings and preview timing with real media and a controlled adapter."""
from pathlib import Path
import copy
import json
import os
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
BASE = Path(tempfile.mkdtemp(prefix='subtitle-tail-', dir=ROOT/'tmp'))
os.environ['MANJU_DATA'] = str(BASE/'data')
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT/'vendor')]
import server as s

checks = []
report = {'ok': False, 'checks': checks, 'base': str(BASE), 'realModel': False}


def check(name, condition):
    assert condition, name
    checks.append(name)
    print('PASS '+name, flush=True)


try:
    legacy = copy.deepcopy(s.DEFAULT)
    legacy.pop('subtitlePreserveTailSeconds')
    check('legacy_config_defaults_to_full_video_repair', s.validate_config(legacy)['subtitlePreserveTailSeconds'] == 0)
    for value in (-1, 31, True, float('nan'), float('inf')):
        try:
            s.validate_config(copy.deepcopy(s.DEFAULT)|{'subtitlePreserveTailSeconds': value})
        except ValueError:
            check('invalid_tail_setting_'+str(value), True)
        else:
            raise AssertionError('Invalid tail setting accepted')
    for mode, engine in [('local', 'lama-box'), ('cloud', 'lama-box'), ('vsr', 'sttn-det')]:
        try:
            s.validate_config(copy.deepcopy(s.DEFAULT)|{'subtitleMode': mode, 'vsrMode': engine, 'subtitlePreserveTailSeconds': 2})
        except ValueError as error:
            check('unsupported_mode_rejected_'+mode+'_'+engine, '片尾保留' in str(error))
        else:
            raise AssertionError('Unsupported tail repair accepted')
    engine = json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
    folder = BASE/'source'
    folder.mkdir()
    original = folder/'01.mp4'
    s.ff(['-f', 'lavfi', '-i', 'testsrc2=size=320x180:rate=10:duration=12',
          '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000', '-shortest',
          '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', str(original)])
    pid = s.scan(str(folder))['projects'][0]['id']
    s.get_project(pid)['rights'] = True
    original_sha = s.sha256(original)
    s.STATE['config'].update(output=str(BASE/'output'), subtitleMode='vsr', vsrMode='sttn-auto',
                             vsrRoot=engine['root'], vsrPython=engine['python'], subtitlePreserveTailSeconds=2)
    requests = []

    def controlled_adapter(runtime, root, request, *args, **kwargs):
        requests.append(copy.deepcopy(request))
        shutil.copy2(request['input'], request['output'])
        return {'reusedProcess': False, 'completedVideos': 1, 'modelLoads': 1}

    def perform(body):
        with patch.object(s, 'ensure_runner', lambda: None):
            job = s.JOBS[s.create_job({'ids': [pid], **body})['id']]
        with patch.object(s.vsr_pool.POOL, 'run', controlled_adapter):
            s.worker(job['id'], job['ids'], job['kind'], job['config'])
        check('job_completed_'+job['id'], job['status'] == 'completed')
        return job

    whole = perform({'kind': 'subtitle'})
    check('whole_episode_passes_tail_setting_to_worker', requests[-1]['preserveTailSeconds'] == 2)
    check('task_snapshot_keeps_original_tail_setting', whole['config']['subtitlePreserveTailSeconds'] == 2)
    for label, start, expected in [('before_tail', 1, 0), ('overlapping_tail', 6.5, 1.5), ('inside_tail', 10.5, 1.5)]:
        job = perform({'kind': 'preview', 'start': start, 'seconds': 5})
        actual = requests[-1]['preserveTailSeconds']
        check('preview_maps_original_time_'+label, abs(actual-expected) < .11)
        check('preview_records_effective_tail_'+label, job['result']['preserveTailSeconds'] == actual)
        check('preview_records_original_tail_setting_'+label, job['result']['configuredPreserveTailSeconds'] == 2)
    check('original_media_unchanged', s.sha256(original) == original_sha)
    report.update(ok=True, requests=requests, previewTimestampMappingVerified=True)
finally:
    s.shutdown_jobs()
    target = BASE/'report.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    (ROOT/'tmp/subtitle-tail-latest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
print(json.dumps({'ok': report['ok'], 'passed': len(checks), 'report': str(target)}, ensure_ascii=True))
