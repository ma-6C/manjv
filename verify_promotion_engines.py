"""Isolated API/queue acceptance; provider calls are explicitly simulated."""
from pathlib import Path
import copy
import http.cookiejar
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
BASE = ROOT/'tmp'/'promotion-engines-acceptance'/time.strftime('%Y%m%d-%H%M%S')
BASE.mkdir(parents=True, exist_ok=True)
os.environ['MANJU_DATA'] = str(BASE/'data')
os.environ['FFMPEG_EXE'] = str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0] = [str(ROOT), str(ROOT/'vendor')]
import server as s
import promotion_engines as engines
import promotion_mediakit as cloud
import promotion_dramaclip as dra
import local_session

host = s.ThreadingHTTPServer(('127.0.0.1', 0), s.Handler)
host.session = local_session.Session()
threading.Thread(target=host.serve_forever, daemon=True).start()
url = 'http://127.0.0.1:' + str(host.server_address[1])
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
client.open(url + '/launch/' + host.session.launch).read()
checks = []


def api(path, body=None, code=200):
    request = urllib.request.Request(url + '/api/' + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json', 'X-Local-Client': '1'})
    try:
        response = client.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    value = json.load(response)
    assert response.status == code, (path, response.status, value)
    return value


try:
    original = copy.deepcopy(s.STATE['config'])
    key = 'TEST-PRIVATE-MEDIAKIT-KEY-DO-NOT-PERSIST'
    with patch.object(dra, 'status', return_value={'ready': True, 'message': 'test sidecar ready'}):
        clean = api('promotion/engines/settings', {'settings': {'mediakit': {'cutMode': 'Sequential'}}, 'mediakitKey': key})
        assert clean['mediakit']['hasKey'] and key not in json.dumps(clean)
        assert clean['settings']['dramaclip'] == engines.DEFAULTS['dramaclip']
        assert s.STATE['config'] == {**original, 'promotionEngineSettings': clean['settings']}
        checks.append('page_settings_preserve_other_feature_settings')
        api('promotion/engines/settings', {'settings': {'mediakit': {'apiKey': key}}}, code=400)
        api('promotion/engines/settings', {'settings': {'mediakit': {'base': 'https://example.invalid'}}}, code=400)
        api('promotion/engines/settings', {'settings': {'mediakit': {'downloadFolder': 'relative/downloads'}}}, code=400)
        api('promotion/engines/settings', {'settings': {'dramaclip': {'python': 'relative/python.exe'}}}, code=400)
        api('promotion/engines/settings', {'mediakitKey': key, 'clearMediakitKey': True}, code=400)
        assert key not in (s.DATA/'state.json').read_text('utf-8')
        checks.append('reject_secret_config_foreign_origins_and_relative_runtimes')
        before_failure=copy.deepcopy(s.STATE['config'])
        with patch.object(s,'store_config',side_effect=OSError('synthetic write failure')):
            api('promotion/engines/settings',{'settings':{'mediakit':{'cutMode':'Mixed'}},'mediakitKey':'REPLACEMENT-KEY'},code=400)
        assert s.STATE['config']==before_failure and key not in cloud.redact(key)
        assert cloud.redact('REPLACEMENT-KEY')=='REPLACEMENT-KEY'
        checks.append('failed_save_keeps_previous_settings_and_memory_key')
        source = BASE/'source'/'合成本地验收'
        source.mkdir(parents=True)
        video = source/'第0001集.mp4'
        s.ff(['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=2','-f','lavfi','-i','sine=duration=2',
              '-c:v','libx264','-c:a','aac','-shortest',str(video)])
        pid = api('scan', {'source': str(source)})['projects'][0]['id']
        api('project', {'id': pid, 'rights': True})
        api('promotion/studio-settings',{'projectId':pid,'settings':{'engine':'dramaclip'}},code=400)
        # Old single-engine forms migrate on the first module-specific save.
        legacy = s.promotion_studio.settings(s.get_project(pid), {'engine':'local','count':3,'seconds':40,'direction':'本地规划'}, [])
        s.get_project(pid)['promotionStudio'] = copy.deepcopy(legacy)
        cloud_form = api('promotion/studio-settings',{'projectId':pid,'settings':{'engine':'mediakit','count':1,'seconds':25,'direction':'云端规划'}})
        assert cloud_form['settingsByEngine']['local'] == legacy
        assert cloud_form['settingsByEngine']['mediakit']['seconds'] == 25
        local_form = api('promotion/studio-settings',{'projectId':pid,'settings':{**legacy,'seconds':45}})
        assert local_form['settingsByEngine']['mediakit'] == cloud_form['settingsByEngine']['mediakit']
        assert local_form['settingsByEngine']['local']['seconds'] == 45
        on_disk = json.loads((s.DATA/'state.json').read_text('utf-8'))
        stored = next(p for p in on_disk['projects'] if p['id']==pid)['promotionStudioByEngine']
        assert stored == local_form['settingsByEngine']
        api('scan', {'source': str(source)})
        assert s.get_project(pid)['promotionStudioByEngine'] == stored
        assert next(p for p in api('state')['projects'] if p['id']==pid)['promotionStudioByEngine'] == stored
        before_bad_form = copy.deepcopy(s.get_project(pid))
        api('promotion/studio-settings',{'projectId':pid,'settings':{'engine':'mediakit','count':99}},code=400)
        assert s.get_project(pid) == before_bad_form
        with patch.object(s, 'save', side_effect=OSError('synthetic form disk failure')):
            api('promotion/studio-settings',{'projectId':pid,'settings':{'engine':'mediakit','count':4,'seconds':35}},code=400)
        assert s.get_project(pid) == before_bad_form
        checks.append('engine_forms_migrate_persist_rescan_and_reject_invalid_without_overwrite')
        cloud_folder=BASE/'客户云端成片'
        api('promotion/engines/settings', {'settings': {'mediakit': {'downloadFolder': str(cloud_folder)}}})
        assert cloud_folder.is_dir()
        with patch.object(s, 'ensure_runner'):
            jid = api('jobs', {'kind': 'promotion_auto', 'ids': [pid], 'studio': {'engine': 'mediakit'}})['id']
            local_id = None
            s.JOBS[jid]['status'] = 'failed'
            local_id = api('jobs', {'kind': 'promotion_auto', 'ids': [pid], 'studio': {'engine': 'local'}})['id']
        assert s.JOBS[local_id]['options']['localBackend'] == 'dramaclip'
        s.get_project(pid)['promotionStudioByEngine']['local']['count'] = 5
        assert s.JOBS[local_id]['options']['studio']['count'] == 2
        checks.append('new_local_combines_dramaclip_with_existing_job_system')
        s.JOBS[local_id]['status'] = 'failed'
        with patch.object(s, 'ensure_runner'):
            s.JOBS[jid]['status'] = 'queued'
            api('jobs/control', {'id':local_id,'action':'resume'}, code=400)
            s.JOBS[jid]['status'] = 'paused'
            api('jobs/control', {'id':local_id,'action':'resume'}, code=400)
            assert s.JOBS[local_id]['status'] == 'failed'
            s.JOBS[jid]['status'] = 'failed'
            api('jobs/control', {'id':local_id,'action':'resume'})
            assert s.JOBS[local_id]['status'] == 'queued'
            s.JOBS[local_id]['status'] = 'failed'
            s.JOBS[jid]['status'] = 'queued'
        checks.append('resume_cannot_bypass_same_project_engine_task_lock')
        api('promotion/engines/settings', {'settings': {'mediakit': {'cutMode': 'Mixed','downloadFolder': ''}, 'dramaclip': {'root': str(BASE/'different-engine')}}})
        assert s.JOBS[jid]['options']['engineOptions']['cutMode'] == 'Sequential'
        assert Path(s.JOBS[jid]['config']['output']) == cloud_folder
        assert s.JOBS[local_id]['config']['output'] == original['output']
        assert s.STATE['config']['output'] == original['output']
        assert s.JOBS[local_id]['options']['engineOptions']['root'] == ''
        checks.append('queued_jobs_keep_immutable_engine_options')
        api('jobs', {'kind': 'promotion_analyse', 'ids': [pid], 'studio': {'engine': 'mediakit'}}, code=400)
        checks.append('cloud_runs_only_as_one_continuous_job')
        calls = []
        def fake_cloud(api_, project, cfg, jid_, opts, sources):
            calls.append(('cloud', opts['engineOptions']['cutMode'], sources[0]['path']))
            dest=api_.project_dir(project,cfg)/'智能推广'/jid_/'云端高光_01.mp4'
            dest.parent.mkdir(parents=True)
            dest.write_bytes(video.read_bytes())
            api_.register(project,dest,'推广混剪',jid_)
            api_.JOBS[jid_]['result'] = {'clipIds': [], 'paths': [str(dest)]}
        def fake_dra(api_, project, cfg, jid_, opts, sources):
            calls.append(('hybrid', opts['engineOptions']['root'], sources[0]['path']))
            api_.JOBS[jid_]['result'] = {'clipIds': [], 'paths': []}
        with patch.object(cloud, 'run', side_effect=fake_cloud), patch.object(dra, 'run', side_effect=fake_dra):
            s.worker(jid, [pid], 'promotion_auto', s.JOBS[jid]['config'])
            s.worker(local_id, [pid], 'promotion_auto', s.JOBS[local_id]['config'])
        assert calls == [('cloud', 'Sequential', str(video)), ('hybrid', '', str(video))], calls
        assert s.JOBS[jid]['status'] == s.JOBS[local_id]['status'] == 'completed'
        saved=Path(s.JOBS[jid]['result']['paths'][0])
        assert saved.is_relative_to(cloud_folder) and saved.is_file()
        with patch.object(s.os,'startfile') as open_folder:
            opened=api('open-output',{'jobId':jid})
            assert Path(opened['path']) == saved.parent
            open_folder.assert_called_once_with(str(saved.parent))
        checks.append('real_worker_dispatches_cloud_and_combined_local_with_snapshots')
        checks.append('cloud_download_path_frozen_for_job_and_used_by_open_output')
        s.JOBS[jid]['promotionRemote'] = {'taskId': 'cloud-123', 'status': 'completed_local', 'downloadedCount': 2,
                                         'signedUrl': 'https://example.invalid/?secret=hidden'}
        s.JOBS[local_id]['promotionDramaClip'] = {'token': 'sidecar-secret', 'projectId': 'dra-123'}
        s.persist_jobs()
        public = api('state')
        assert 'promotionRemote' not in json.dumps(public) and 'sidecar-secret' not in json.dumps(public)
        assert 'secret=hidden' not in json.dumps(public)
        assert next(j for j in public['jobs'] if j['id']==jid)['mediakitTask'] == {
            'taskId': 'cloud-123', 'status': 'completed_local', 'downloadedCount': 2}
        assert 'mediakitTask' not in next(j for j in public['jobs'] if j['id']==local_id)
        assert 'cloud-123' in (s.DATA/'jobs.json').read_text('utf-8')
        assert key not in (s.DATA/'jobs.json').read_text('utf-8')
        assert key not in s.diagnostic_text('HTTP 401 key=' + key)
        checks.append('recovery_journals_stay_on_disk_keys_and_tokens_not_exposed')
        diagnostic=s.telemetry.failure(s.JOBS[jid],RuntimeError('MediaKit HTTP 401: authentication '+key),redact=s.diagnostic_text)
        assert diagnostic['code']=='AUTH' and '本页设置' in diagnostic['nextStep'] and key not in json.dumps(diagnostic)
        unknown=s.telemetry.failure(s.JOBS[jid],RuntimeError('云端提交结果未知'),redact=s.diagnostic_text)
        assert '不要重复提交' in unknown['nextStep']
        checks.append('cloud_errors_name_correct_settings_and_unknown_submission_recovery')
        for endpoint in ('promotion/dispatch', 'promotion/fanout', 'promotion/receipt'):
            api(endpoint, {}, code=410)
        checks.append('removed_publish_endpoints_stay_retired')
        api('promotion/engines/settings', {'clearMediakitKey': True})
        assert not api('promotion/engines')['mediakit']['hasKey']
        with patch.object(s, 'ensure_runner'):
            api('jobs', {'kind':'promotion_auto','ids':[pid],'studio':{'engine':'mediakit'}}, code=400)
        checks.append('missing_cloud_key_fails_before_queue_or_upload')
    with patch.object(dra, 'status', return_value={'ready': False, 'message': 'missing synthetic runtime'}):
        fallback = engines.local_backend(engines.DEFAULTS['dramaclip'])
        assert fallback['localBackend'] == 'native' and 'missing' in fallback['localBackendReason']
    checks.append('missing_optional_local_components_use_explicit_native_compatibility')
    report = {'ok': True, 'checks': checks, 'base': str(BASE), 'providerCalls': 'simulated', 'queueAndHttp': 'real', 'remoteUpload': False}
    (ROOT/'tmp/promotion-engines-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('PROMOTION_ENGINES_ACCEPTANCE_OK', len(checks))
finally:
    cloud.set_key(cloud.DEFAULT_BASE, '')
    s.shutdown_jobs()
    host.shutdown()
    host.server_close()
