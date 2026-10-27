"""Isolated real process failures, worker diagnostics and credential-safe reports."""
from pathlib import Path
from unittest.mock import patch
import copy,json,os,sys,tempfile,threading
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='task-diagnostics-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,task_progress as t
checks=[]
def check(name,ok):
    assert ok,name
    checks.append(name);print('PASS '+name,flush=True)
def fails(args,**kw):
    try:s.run_process(args,**kw)
    except t.ProcessFailure as e:return e
    raise AssertionError('expected process failure')

source=BASE/'source';source.mkdir();video=source/'第002集.mp4'
s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=1','-f','lavfi','-i','sine=frequency=440:duration=1',
      '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(video)])
original=s.sha256(video)
p=s.scan(str(source))['projects'][0]
s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':320,'height':180,'gpu':False,'regroup':False,'autoRecords':False})
with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':'transcode','ids':[p['id']]})['id']
with patch.object(s,'filters',lambda *args:'no_such_diagnostic_filter'):s.worker(jid,[p['id']],'transcode',s.JOBS[jid]['config'])
j=s.JOBS[jid];d=j['diagnostic']
check('real_ffmpeg_filter_failure_reaches_worker',j['status']=='failed' and d['code']=='FILTER' and d['exitCode']!=0)
check('failure_keeps_actual_stage_video_and_tool',d['stage']!='任务失败' and d['video']==video.name and 'ffmpeg' in d['tool'])
check('actual_error_and_next_step_are_available','no_such_diagnostic_filter' in d['reason'] and '参数' in d['nextStep'])
check('traceback_retained_for_local_details','ProcessFailure' in d['traceback'])
entry=s.STATE['logs'][-1]
check('structured_error_log_has_task_and_media_context',entry['job']==jid and entry['video']==video.name and entry['diagnostic']['code']=='FILTER')
export=s.log_export([entry])
check('text_export_contains_details_not_just_generic_status',video.name in export and '退出码' in export and 'no_such_diagnostic_filter' in export)
check('diagnostics_survive_saved_task_restart',next(row for row in json.loads((s.DATA/'jobs.json').read_text('utf-8')) if row['id']==jid)['diagnostic']['code']=='FILTER')
check('source_hash_unchanged',s.sha256(video)==original)
e=fails([sys.executable,'-c',"print('RuntimeError: stdout-only failure');raise SystemExit(9)"])
check('stdout_only_process_error_is_not_lost','stdout-only failure' in str(e) and e.exit_code==9)
e=fails([sys.executable,'-c',"import sys;sys.stderr.write('CRITICAL ERROR: early cause\\n'+'filler line\\n'*9000);sys.exit(4)"],observe=lambda line:None)
check('error_before_large_output_tail_is_preserved','early cause' in e.details)
e=fails([sys.executable,'-c','import time;time.sleep(5)'],timeout=.15,observe=lambda line:None)
check('observed_process_timeout_terminates_without_pipe_race',e.timed_out and t.failure({},e)['code']=='PROCESS_TIMEOUT' and '超时' in t.failure({},e)['reason'])
parallel={'id':'parallel','telemetry':{'rows':[]}}
t.begin(parallel,'编码','第001集.mp4',5);t.begin(parallel,'编码','第002集.mp4',5)
e=t.ProcessFailure('ffmpeg.exe',1,'Invalid argument');e.video='第002集.mp4'
check('parallel_failure_uses_failed_process_video',t.failure(parallel,e)['video']=='第002集.mp4')
old=t.job_failure({'status':'failed','stage':'任务失败','error':'unknown old failure','finished':1700000000})
check('legacy_diagnostics_do_not_invent_time_or_exception_type',old['exceptionType']=='未记录（历史任务）' and old['time']==t.time.strftime('%Y-%m-%d %H:%M:%S',t.time.localtime(1700000000)))
check('encoder_invalid_argument_is_not_misreported_as_crop_error',t.failure({},RuntimeError('h264_nvenc: Invalid argument'))['code']=='ENCODER')
for raw,code in [('PermissionError: access is denied','PERMISSION'),('CUDA out of memory','MEMORY'),('No module named helper','DEPENDENCY'),('No space left on device','DISK_SPACE'),('HTTP Error 401: Unauthorized','AUTH')]:
    check('classify_'+code,t.failure({},RuntimeError(raw))['code']==code)
secret='test-session-secret-value';s.SECRETS['apiKey']=secret
protected=s.diagnostic_text('Authorization: Bearer bearer-private-value\napi_key="query-private-value"\nhttps://example.invalid/?token=private-value&x=2 '+secret)
check('session_bearer_query_and_json_credentials_redacted',all(x not in protected for x in ['bearer-private-value','query-private-value','token=private-value',secret]))
private=j|{'diagnostic':copy.deepcopy(j['diagnostic'])};private['diagnostic']['reason']='failed C:/Users/private/path';private['diagnostic']['details']=secret
report=json.dumps(t.report(private),ensure_ascii=False)
check('summary_has_error_context_but_no_stack_secrets_or_full_paths','no_such_diagnostic_filter' not in report and 'private/path' not in report and secret not in report and 'traceback' not in report and 'FILTER' in report)
with patch.object(s,'filters',lambda *args:'null'):s.worker(jid,[p['id']],'transcode',s.JOBS[jid]['config'])
check('successful_retry_clears_stale_error_and_diagnostic',j['status']=='completed' and not j.get('diagnostic') and not j.get('error'))
result={'ok':True,'passed':len(checks),'checks':checks,'base':str(BASE),'failedJobId':jid}
(ROOT/'tmp/task-diagnostics-latest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
