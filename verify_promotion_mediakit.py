"""MediaKit contract/recovery acceptance with simulated HTTPS and real FFmpeg.

No external provider request, customer video, API credential, or paid task is
used. Fake HTTPS connections exercise the real JSON/upload/download transports.
"""
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from unittest.mock import patch
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import promotion_mediakit as m

BASE = ROOT/'tmp'/'mediakit-acceptance'/time.strftime('%Y%m%d-%H%M%S')
BASE.mkdir(parents=True, exist_ok=True)
FFMPEG = str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
KEY = 'TEST-ONLY-PRIVATE-MEDIAKIT-KEY'
SIGNATURE = 'TEST-ONLY-SIGNED-MEDIA-SECRET'
checks = []


def ffmpeg(args):
    result = subprocess.run([FFMPEG,'-hide_banner','-loglevel','error','-y',*map(str,args)],
        capture_output=True, timeout=60, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8','replace'))
    return result.stdout


def expect(error_type, fn, contains=''):
    try:
        fn()
    except error_type as error:
        if contains:
            assert contains in str(error), str(error)
        return str(error)
    raise AssertionError('Expected ' + str(error_type))


class Api:
    def __init__(self, name):
        self.name = name
        self.LOCK = threading.RLock()
        self.JOBS = {name: {'cancel':threading.Event(), 'checkpoints':{}}}
        self.project = {'id':'fixture','name':'这是用于验证云端模板标题长度截取的合成剧名不会上传真实素材',
                        'source':str(BASE/'source'),'artifacts':[]}
        self.logs = []
        self.stages = []
    def persist_jobs(self):
        rows = {k:{a:b for a,b in v.items() if a != 'cancel'} for k,v in self.JOBS.items()}
        (BASE/(self.name+'-journal.json')).write_text(json.dumps(rows,ensure_ascii=False),'utf-8')
    def save(self):
        self.persist_jobs()
    def log(self, message, **kwargs):
        self.logs.append(m.redact(message))
    def stage(self, jid, name, progress):
        self.stages.append((name, progress))
    def project_dir(self, project, cfg):
        return BASE/self.name
    def cached(self, jid, key):
        entries = self.JOBS[jid]['checkpoints'].get(key)
        if entries and all(Path(e['path']).is_file() and self.sha256(e['path']) == e['sha256'] for e in entries):
            return [Path(e['path']) for e in entries]
    def checkpoint(self, jid, key, paths):
        self.JOBS[jid]['checkpoints'][key] = [{'path':str(p),'sha256':self.sha256(p)} for p in paths]
        self.persist_jobs()
    def sha256(self, path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def probe(self, path):
        result = subprocess.run([FFMPEG,'-hide_banner','-i',str(path)],capture_output=True,timeout=30,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        text = result.stderr.decode('utf-8','replace')
        match = re.search(r'Duration: (\d+):(\d+):([\d.]+)',text)
        dimensions = re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b',text)
        if not match or not dimensions:
            raise RuntimeError('invalid media output')
        h,minute,second = map(float,match.groups())
        return {'duration':h*3600+minute*60+second,'width':int(dimensions[1]),'height':int(dimensions[2]),'audio':'Audio:' in text}
    def ff(self, args, jid):
        return ffmpeg(args)
    def register(self, project, path, kind, jid):
        project['artifacts'] = [v for v in project['artifacts'] if v['path'] != str(path)]
        project['artifacts'].append({'path':str(path),'kind':kind,'job':jid})


class Response:
    def __init__(self, data, status=200, headers=None):
        self.data = io.BytesIO(data)
        self.status = status
        self.headers = headers or {'Content-Length':str(len(data))}
    def read(self, size=-1):
        return self.data.read(size)
    def getheader(self, name):
        return self.headers.get(name)


class Transport:
    def __init__(self, media):
        self.media = media
        self.calls = []
        self.uploads = []
        self.payload = None
        self.submit_error = None
        self.query_error_once = False
        self.task_failed = False
        self.missing_id = False
        self.bad_media = False
        self.expired = False
        self.download_count = 0
    def connect(self, url):
        p = m._media_url(url)
        return Connection(self, p.hostname), urlunsplit(('', '', p.path or '/', p.query, ''))
    def response(self, host, method, target, data, headers):
        self.calls.append((host, method, target, copy.deepcopy(headers)))
        if host == 'mediakit.cn-beijing.volces.com':
            assert headers.get('Authorization') == 'Bearer '+KEY
            if target.endswith('request-media-upload-url'):
                value = {'success':True,'result':{'file_id':'mediakit://fixture-upload','method':'PUT','upload_headers':[],
                    'upload_url':'https://upload.example.com/video?Authorization='+SIGNATURE}}
            elif target.endswith('generate-highlights-microdrama'):
                self.payload = json.loads(data)
                if self.submit_error:
                    raise self.submit_error
                value = {'success':True,'request_id':'request-fixture'}
                if not self.missing_id:
                    value['task_id'] = 'amk-fixture-task'
            else:
                assert method == 'GET' and target == '/api/v1/tasks/amk-fixture-task'
                if self.query_error_once:
                    self.query_error_once = False
                    raise ConnectionError('simulated query disconnect')
                value = {'success':True,'status':'failed' if self.task_failed else 'completed',
                    'task_id':'amk-fixture-task','result':{
                        'video_urls':['https://media.example.com/final.mp4?auth_key='+SIGNATURE],
                        'mixvideo_info':[{'mixvideo_index':0,'clips':[{'clip_type':'HighlightClip',
                            'source_video_index':0,'source_start_time':0,'source_end_time':2,'score':4}]}]},
                    'expires_at':time.time()-1 if self.expired else time.time()+86400,
                    'error':{'code':'TEST_FAILURE','message':'failure '+KEY+' https://media.example.com/final.mp4?auth_key='+SIGNATURE}}
            return Response(json.dumps(value).encode())
        assert not any(k.lower() == 'authorization' for k in headers)
        assert KEY not in json.dumps(headers)
        assert host == 'media.example.com' and method == 'GET'
        self.download_count += 1
        return Response(b'corrupt-mp4' if self.bad_media else self.media)


class Connection:
    def __init__(self, transport, host):
        self.transport,self.host = transport,host
        self.headers = {}
        self.chunks = []
        self.response = None
    def request(self, method, target, body=None, headers=None):
        self.response = self.transport.response(self.host,method,target,body,headers or {})
    def putrequest(self, method, target):
        assert self.host == 'upload.example.com' and method == 'PUT'
        self.target = target
    def putheader(self, name, value):
        self.headers[name] = value
    def endheaders(self):
        assert not any(k.lower() in ('authorization','cookie') for k in self.headers)
    def send(self, data):
        assert isinstance(data, bytes) and 0 < len(data) <= 256*1024
        self.chunks.append(data)
    def getresponse(self):
        if self.host == 'upload.example.com':
            assert sum(map(len,self.chunks)) == int(self.headers['Content-Length'])
            self.transport.uploads.append({'headers':copy.deepcopy(self.headers),'chunks':len(self.chunks),
                'sha256':hashlib.sha256(b''.join(self.chunks)).hexdigest()})
            return Response(b'',200)
        return self.response
    def close(self):
        pass


source = BASE/'source'/'第0001集.mp4'
source.parent.mkdir(parents=True)
ffmpeg(['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=2','-f','lavfi','-i','sine=duration=2',
    '-c:v','libx264','-c:a','aac','-shortest',source])
probe_api = Api('probe')
stat = source.stat()
sources = [{'path':str(source),'name':source.name,**probe_api.probe(source),
            'stat':{'bytes':stat.st_size,'mtimeNs':stat.st_mtime_ns}}]
original_hash = probe_api.sha256(source)
opts = {'engine':'mediakit','count':2,'seconds':60,'direction':'选取真实台词冲突与悬念',
        'cta':'点击下方入口观看完整剧集保留悬念引导用户查看全集',
        'engineOptions':{'base':m.DEFAULT_BASE,'cutMode':'Sequential'}}
cfg = {'output':str(BASE)}
m.set_key(m.DEFAULT_BASE,KEY)


def run(api, transport, options=None):
    with patch.object(m,'_connection',side_effect=transport.connect):
        m.run(api,api.project,cfg,api.name,options or opts,sources)


try:
    main = Api('full-flow')
    network = Transport(source.read_bytes())
    run(main,network)
    cuts = network.payload['highlight_cuts_param']
    assert cuts['min_duration'] == 55 and cuts['max_duration'] == 60 and cuts['max_number'] == 2 and cuts['cut_mode'] == 'Sequential'
    template = network.payload['edit_param']['template_edit']
    assert template == {'template':'热门短剧1','title':main.project['name'][:22],'hint':opts['cta'][:20]}
    assert network.payload['video_urls'] == ['mediakit://fixture-upload']
    checks.append('official_payload_count_duration_cut_mode_template_and_real_cta')
    clip = main.project['promotionClips'][0]
    assert main.probe(clip['path'])['audio'] and abs(main.probe(clip['path'])['duration']-2) < .2
    assert clip['cta'] == opts['cta'][:20] and clip['requestedCta'] == opts['cta']
    assert clip['sourceKind'] == 'mediakit' and clip['segments'][0]['source_video_index'] == 0
    assert main.JOBS[main.name]['result']['paths'] == [clip['path']]
    assert network.uploads[0]['sha256'] == original_hash
    checks.append('real_media_upload_bytes_download_probe_full_decode_and_registration')
    journal = (BASE/(main.name+'-journal.json')).read_text('utf-8')
    assert KEY not in journal and SIGNATURE not in journal and KEY not in '\n'.join(main.logs)
    assert '前20字' in '\n'.join(main.logs)
    checks.append('keys_signed_urls_never_persist_and_truncation_is_logged')
    previous = len(network.calls)
    run(main,network)
    assert len(network.calls) == previous+1 and network.calls[-1][1] == 'GET'
    assert network.download_count == 1 and len(network.uploads) == 1
    assert len(main.project['promotionClips']) == len(main.project['artifacts']) == 1
    checks.append('resume_queries_existing_task_and_reuses_valid_local_outputs_without_duplicates')
    created = clip['createdAt']
    Path(clip['path']).write_bytes(b'corrupt-local-output')
    run(main, network)
    recovered = main.project['promotionClips'][0]
    assert len(main.project['promotionClips']) == 1 and recovered['createdAt'] == created
    assert recovered['mtimeNs'] == Path(recovered['path']).stat().st_mtime_ns
    assert recovered['bytes'] == Path(recovered['path']).stat().st_size
    assert recovered['sha256'] == main.sha256(recovered['path'])
    assert network.download_count == 2 and len(network.uploads) == 1
    assert sum('generate-highlights-microdrama' in c[2] for c in network.calls) == 1
    checks.append('corrupt_cached_output_redownload_refreshes_library_without_new_paid_task')
    interrupted = Api('query-disconnect')
    t = Transport(source.read_bytes());t.query_error_once = True
    expect(ConnectionError, lambda:run(interrupted,t))
    assert interrupted.JOBS[interrupted.name]['promotionRemote']['taskId'] == 'amk-fixture-task'
    run(interrupted,t)
    assert sum('generate-highlights-microdrama' in c[2] for c in t.calls) == 1 and len(t.uploads) == 1
    checks.append('disconnect_after_submission_resumes_original_task_without_reupload_or_resubmit')
    unknown = Api('submit-unknown')
    t = Transport(source.read_bytes());t.submit_error = TimeoutError('simulated timeout '+KEY)
    message = expect(RuntimeError,lambda:run(unknown,t),'结果未知')
    token = unknown.JOBS[unknown.name]['promotionRemote']['clientToken']
    assert token in message and KEY not in message
    calls = len(t.calls)
    expect(RuntimeError,lambda:run(unknown,t),'未自动重交')
    assert len(t.calls) == calls
    checks.append('unknown_submission_blocks_repeat_billing_and_exposes_only_safe_request_credential')
    no_id = Api('submit-missing-id')
    t = Transport(source.read_bytes());t.missing_id = True
    expect(RuntimeError,lambda:run(no_id,t),'缺少可靠任务 ID')
    expect(RuntimeError,lambda:run(no_id,t),'未自动重交')
    checks.append('successful_submit_without_task_id_is_not_blindly_retried')
    failed = Api('provider-failure')
    t = Transport(source.read_bytes());t.task_failed = True
    message = expect(RuntimeError,lambda:run(failed,t),'TEST_FAILURE')
    assert KEY not in message and SIGNATURE not in message and 'amk-fixture-task' in message
    checks.append('provider_error_keeps_error_code_task_id_and_redacts_credentials')
    corrupt = Api('corrupt-download')
    t = Transport(source.read_bytes());t.bad_media = True
    expect(RuntimeError,lambda:run(corrupt,t),'invalid media output')
    assert not corrupt.JOBS[corrupt.name]['checkpoints'] and not list((BASE/corrupt.name).rglob('*.mp4'))
    t.bad_media = False
    run(corrupt,t)
    assert sum('generate-highlights-microdrama' in c[2] for c in t.calls) == 1
    checks.append('corrupted_download_removed_and_retry_redownloads_same_remote_task')
    expired = Api('expired-result')
    t = Transport(source.read_bytes());t.expired = True
    expect(RuntimeError,lambda:run(expired,t),'不能续期')
    assert t.download_count == 0 and not expired.project.get('promotionClips')
    checks.append('expired_provider_result_does_not_claim_renewal_or_start_new_paid_job')
    canceled = Api('cancelled')
    canceled.JOBS[canceled.name]['cancel'].set()
    t = Transport(source.read_bytes())
    expect(InterruptedError,lambda:run(canceled,t))
    assert not t.calls
    checks.append('cancel_before_start_has_no_network_side_effect')
    big = BASE/'stream.bin';big.write_bytes(b'0123456789abcdef'*(64*1024))
    t = Transport(source.read_bytes())
    with patch.object(m,'_connection',side_effect=t.connect):
        m._upload_file('https://upload.example.com/media?signature='+SIGNATURE,
            m._upload_headers([],big),big,threading.Event())
    assert t.uploads[0]['chunks'] == 4 and t.uploads[0]['sha256'] == probe_api.sha256(big)
    checks.append('upload_streams_bounded_chunks_without_api_authorization')
    for headers in ([{'key':'Authorization','value':'Bearer '+KEY}], [{'key':'Cookie','value':'test'}],
                    [{'key':'X-Test','value':'bad\r\nvalue'}]):
        expect(ValueError,lambda:m._upload_headers(headers,big))
    for url in ('http://example.com/a','https://localhost/a','https://user:pass@example.com/a','https://example.com:444/a'):
        expect(ValueError,lambda:m._media_url(url))
    with patch.object(m.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
        expect(ValueError,lambda:m._PinnedHTTPSConnection('example.com').connect(),'保留网络')
    checks.append('upload_header_and_private_network_guards')
    for mutation in ('count','duration','audio','resolution'):
        rows = copy.deepcopy(sources)
        if mutation == 'count':rows *= 31
        if mutation == 'duration':rows[0]['duration'] = 2701
        if mutation == 'audio':rows[0]['audio'] = False
        if mutation == 'resolution':rows[0]['width']=1921
        expect(ValueError,lambda:m._validate(rows,opts))
    checks.append('provider_limits_fail_before_network')
    changed = copy.deepcopy(sources);changed[0]['stat']['mtimeNs'] -= 1
    expect(ValueError,lambda:m._validate(changed,opts),'修改')
    assert original_hash == probe_api.sha256(source)
    checks.append('source_snapshot_changes_rejected_and_original_media_unchanged')
    m.set_key(m.DEFAULT_BASE,'')
    assert KEY not in m.redact('late in-flight error '+KEY)
    expect(ValueError,lambda:m.run(Api('missing-key'),main.project,cfg,'missing-key',opts,sources),'API Key')
    assert not m.key_status()
    checks.append('cloud_key_required_and_clearable_without_persistence')
    report = {'ok':True,'checks':checks,'base':str(BASE),'https':'simulated_connection_transport',
              'media':'real_ffmpeg_probe_and_full_decode','externalRequests':0,'paidTasks':0,
              'clip':clip['path'],'sourcePreserved':original_hash == probe_api.sha256(source)}
    (ROOT/'tmp/mediakit-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('MEDIAKIT_ACCEPTANCE_OK',len(checks),flush=True)
finally:
    m.set_key(m.DEFAULT_BASE,'')
