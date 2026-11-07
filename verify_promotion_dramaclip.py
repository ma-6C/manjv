"""Real pinned DramaClip RPC/planning + local encoding, controlled LLM/SRT input.

No customer video, key, account, real LLM endpoint or publishing is used.
"""
from pathlib import Path
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'tmp' / ('dramaclip-acceptance-' + time.strftime('%Y%m%d-%H%M%S'))
BASE.mkdir(parents=True)
os.environ['MANJU_DATA'] = str(BASE / 'data')
sys.path[:0] = [str(ROOT), str(ROOT / 'vendor')]
import server as server
import promotion_dramaclip as dra
import promotion_studio as studio

checks = []


def controlled_model(_cfg, system, user, _tokens=1024):
    if 'scene_index' in system:
        raw = json.loads(user)
        text = [{'scene_index': item['scene_index'], 'score': 85, 'reason': '合成测试的完整对白冲突'} for item in raw]
    elif '主导题材' in system:
        text = {'genre': '悬疑'}
    elif 'angles' in system:
        text = {'angles': [{'name': '证据与真相', 'reason': '两集完整对白串成合成故事线', 'episode_numbers': [1, 2]}]}
    else: raise AssertionError('Unexpected controlled LLM request: ' + system[:180])
    return {'text': json.dumps(text, ensure_ascii=False), 'model': 'LOCAL-CONTROLLED-NO-REMOTE'}


def main():
    ready = dra.status()
    assert ready['ready'], ready
    checks.append('prepared_runtime_requires_actual_import_and_rpc_marker')
    cancel = threading.Event()
    with dra.Sidecar({}, BASE / 'read-only-probe', cancel) as sidecar:
        ping = sidecar.call('system.ping')
        assert ping['protocol_version'] == 1
    checks.append('real_sidecar_token_handshake_and_upstream_rpc_ping')
    source = BASE / '合成输入'; source.mkdir()
    sources = []
    for i, color in enumerate(('red', 'blue')):
        video = source / f'第{i + 1}集.mp4'
        server.ff(['-f', 'lavfi', '-i', f'color=c={color}:s=320x180:r=30:d=6', '-f', 'lavfi', '-i',
                   f'sine=frequency={440 + i * 220}:duration=6', '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(video)])
        video.with_suffix('.srt').write_text('1\n00:00:00,000 --> 00:00:03,000\n你终于带来了证据。\n\n2\n00:00:03,000 --> 00:00:05,900\n真相究竟是什么？\n', 'utf-8')
        sources.append(server.probe(video) | {'path': str(video), 'name': video.name,
                       'stat': studio.snapshot(video), 'subtitleStat': studio.snapshot(video.with_suffix('.srt'))})
    before = {row['path']: server.sha256(row['path']) for row in sources}
    jid = 'synthetic-dramaclip-job'
    project = {'id': 'synthetic-dramaclip-project', 'name': '合成验收剧', 'videos': sources}
    opts = {'count': 1, 'seconds': 10, 'direction': '只依据合成台词', 'cta': '', 'engineOptions': {}}
    events = []; checkpoints = {}
    api = SimpleNamespace(JOBS={jid: {'cancel': cancel}}, STATE={'jianyingOptions': {}},
        LOCK=threading.RLock(), FONT='',
        project_dir=lambda _p, _cfg: BASE / 'output',
        stage=lambda _j, text, percent: events.append({'stage': text, 'percent': percent}),
        log=lambda text, **_kw: events.append({'log': text}), persist_jobs=lambda: None,
        diagnostic_text=server.diagnostic_text, save=lambda: None,
        ff=lambda args, _job: server.ff(args), probe=server.probe,
        sha256=server.sha256, register=lambda *_args: None,
        checkpoint=lambda _j, key, paths: checkpoints.update({key: [str(p) for p in paths]}),
        cached=lambda _j, key: checkpoints.get(key),
        run_process=lambda args, _job, **kwargs: server.run_process(args, **kwargs))
    with patch.object(studio.ai_providers, 'text_generate', side_effect=controlled_model):
        dra.run(api, project, {}, jid, opts, sources)
    result = api.JOBS[jid]['result']; state = api.JOBS[jid]['promotionDramaClip']
    assert state['projectId'] and len(state['episodeIds']) == 2 and len(state['episodeAnalysis']) == 2
    assert state['planTaskId'] and len(state['planIds']) == 1
    assert state['llmRequests'] >= 5, state
    checks.append('real_upstream_semantic_scoring_cross_episode_selection_and_raw_clip_plan')
    assert len(result['paths']) == 1
    clip = project['promotionClips'][0]
    meta = server.probe(clip['path'])
    assert 5 <= meta['duration'] <= 10.5 and meta['width'] == 320 and meta['height'] == 180 and meta['audio'], meta
    assert len({x['source'] for x in clip['segments']}) == 2, clip
    checks.append('existing_ffmpeg_renderer_validates_actual_cross_episode_audio_video')
    # Retrying a completed job must reuse the upstream ids and encoded files.
    with patch.object(studio.ai_providers, 'text_generate', side_effect=AssertionError('Unexpected repeat model call')):
        dra.run(api, project, {}, jid, opts, sources)
    assert len(project['promotionClips']) == 1 and state['planIds'] == api.JOBS[jid]['result']['planIds']
    checks.append('retry_reuses_persisted_analysis_plan_ids_and_verified_render_checkpoints')
    db = Path(state['dataDir']) / 'data.db'
    import sqlite3
    with sqlite3.connect(db) as conn:
        secrets = conn.execute("SELECT key,value FROM settings WHERE key IN ('llm.api_key','llm.base_url','llm.model')").fetchall()
    assert all(not value for _key, value in secrets), secrets
    checks.append('llm_customer_key_and_transient_proxy_credential_are_not_persisted_in_sidecar_db')
    # Simulate a process dying after analysis, during planning. Upstream sweeps
    # pending/running tasks to failed at startup rather than rescheduling them.
    resumed_jid = 'synthetic-interrupted-planning'
    resumed_dir = BASE / 'output' / '智能推广' / resumed_jid / 'DramaClip数据'
    shutil.copytree(Path(state['dataDir']), resumed_dir)
    with sqlite3.connect(resumed_dir / 'data.db') as conn:
        conn.execute('DELETE FROM narration_plans WHERE batch_id=?', (state['planTaskId'],))
        conn.execute("UPDATE jobs SET status='running',error=NULL WHERE id=?", (state['planTaskId'],))
    resumed_state = copy.deepcopy(state); resumed_state.pop('analysis')
    api.JOBS[resumed_jid] = {'cancel': threading.Event(), 'promotionDramaClip': resumed_state}
    calls = []
    def planning_only(cfg, system, user, tokens):
        assert 'scene_index' not in system and '主导题材' not in system, 'Completed analysis should be reused'
        calls.append('plan')
        return controlled_model(cfg, system, user, tokens)
    with patch.object(studio.ai_providers, 'text_generate', side_effect=planning_only):
        dra.run(api, project, {}, resumed_jid, opts, sources)
    assert calls and resumed_state['planTaskId'] != state['planTaskId']
    assert resumed_state['planAttempts'][-1]['taskId'] == state['planTaskId']
    assert resumed_state['episodeIds'] == state['episodeIds']
    assert len(project['promotionClips']) == 2
    checks.append('interrupted_plan_restarts_only_planning_and_preserves_completed_episode_analysis')
    # Provider details are retained in the parent and suppressed from sidecar.
    failed_jid = 'synthetic-provider-error'
    api.JOBS[failed_jid] = {'cancel': threading.Event()}
    with patch.object(studio.ai_providers, 'text_generate', side_effect=ValueError('HTTP 401: Invalid API key; model=controlled')):
        try: dra.run(api, project, {}, failed_jid, opts, sources)
        except RuntimeError as exc: assert 'HTTP 401' in str(exc), str(exc)
        else: raise AssertionError('Provider failure should stop the real engine')
    assert len(project['promotionClips']) == 2
    checks.append('provider_failure_exposes_original_http_diagnostic_and_never_creates_fallback_clip')
    assert before == {row['path']: server.sha256(row['path']) for row in sources}
    checks.append('source_media_unchanged')
    report = {'ok': True, 'checks': checks, 'base': str(BASE), 'clip': clip['path'], 'meta': meta,
              'commit': dra.COMMIT, 'llm': 'controlled local responses', 'asr': 'real same-name SRT input',
              'planning': 'real pinned DramaClip sidecar RPC', 'encoding': 'real FFmpeg', 'events': events}
    target = ROOT / 'tmp' / 'promotion-dramaclip-acceptance.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print('DRAMACLIP_ACCEPTANCE_OK', len(checks), str(target))


if __name__ == '__main__': main()
