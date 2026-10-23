"""Source-only GPU, CPU fallback and mixed-encoder regressions; real FFmpeg outputs."""
from pathlib import Path
from unittest.mock import patch
import os,sys,tempfile,json,threading,copy,re,subprocess
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='gpu-fallback-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
COMPILED='--compiled' in sys.argv
VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.2'
sys.path[:0]=([str(ROOT/'release'/VERSION/'漫剧工坊/_internal')] if COMPILED else [])+[str(ROOT/'vendor')];sys.dont_write_bytecode=True
if COMPILED:sys.frozen=True
import server as s,gpu_encoding as g,task_progress as tp
if COMPILED:
    import re
    assert all(module.__file__.endswith('.pyd') for module in (s,g))
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    s.licensing.activate(s.DATA,token)
checks=[];runs={}
def check(name,value=True):assert value,name;checks.append(name)
ready={'available':True,'profile':'standard','encoderArgs':g.PROFILES[0][1].copy(),'code':'ready','detail':'test ready'}
unavailable={'available':False,'code':'driver_version','detail':'NVIDIA 驱动与编码接口不兼容'}

real_environment=s.environment(force=True)
check('real_environment_has_classified_result_and_adapter_fields','code' in real_environment['gpu'] and 'adapters' in real_environment['gpu'])
calls=[]
def compatibility(args):
    calls.append(args)
    if args[args.index('-preset')+1]=='p4':raise RuntimeError('[h264_nvenc] Unable to parse option value p4')
    return b'frame=3\nprogress=end\n'
r=g.probe('fake-profile',force=True,runner=compatibility)
check('older_preset_uses_tested_compatibility_profile',r['available'] and r['profile']=='compatibility' and len(calls)==2)
calls=[]
def old_driver(args):calls.append(args);raise RuntimeError('[h264_nvenc] Driver does not support the required nvenc API version')
r=g.probe('fake-driver',force=True,runner=old_driver)
check('driver_incompatibility_is_specific_and_bounded',not r['available'] and r['code']=='driver_version' and len(calls)==len(g.BACKENDS))
r2=g.probe('fake-driver',runner=lambda a:(_ for _ in ()).throw(AssertionError('cache should be used')))
check('recent_environment_probe_is_cached',r2['code']=='driver_version')
r=g.probe('fake-driver',force=True,runner=lambda a:b'frame=3\nprogress=end\n')
check('manual_refresh_retests_previously_failed_gpu',r['available'])
r=g.probe('fake-zero',force=True,runner=lambda a:b'frame=0\nprogress=end\n')
check('exit_zero_without_encoded_frames_not_accepted',not r['available'])
try:g.probe('fake-cancel',force=True,runner=lambda a:(_ for _ in ()).throw(InterruptedError('cancelled')))
except InterruptedError:check('cancelled_probe_propagates_without_cpu_retry')
else:raise AssertionError('cancelled probe swallowed')
check('disk_and_input_errors_are_not_gpu_startup_failures',not g.startup_failure('No space left on device') and not g.startup_failure('Invalid data found when processing input'))
args=['-i','original.mp4',*g.PROFILES[0][1],'-bf','0','-frames:v','42','out.mp4'];cpu=g.cpu_arguments(args)
check('cpu_retry_preserves_source_target_and_frame_plan',cpu[1]=='original.mp4' and cpu[-1]=='out.mp4' and cpu[cpu.index('-frames:v')+1]=='42' and '-cq' not in cpu and 'p4' not in cpu)
for backend_id in ('amf','qsv'):
    backend=next(b for b in g.BACKENDS if b['id']==backend_id);attempted=[]
    def select_backend(args):
        codec=args[args.index('-c:v')+1];attempted.append(codec)
        if codec!=backend['codec']:raise RuntimeError('Unknown encoder '+codec)
        assert args[args.index('-pix_fmt')+1]=='nv12'
        return b'frame=3\nprogress=end\n'
    result=g.probe('fake-'+backend_id,force=True,runner=select_backend)
    check(backend_id+'_selected_when_previous_backend_unavailable',result['available'] and result['backend']==backend_id and result['encoderArgs'][1]==backend['codec'])

source=BASE/'source';source.mkdir()
for i,d in enumerate((1.2,1.4)):
    s.ff(['-f','lavfi','-i',f'testsrc2=s=320x180:r=30:d={d}','-f','lavfi','-i',f'sine=frequency={440+i*220}:duration={d}','-c:v','libx264','-c:a','aac','-shortest',str(source/f'{i+1}.mp4')])
p=s.scan(str(source))['projects'][0];before={v['path']:s.sha256(v['path']) for v in p['videos']}
cfg=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':320,'height':180,'parallel':1,'gpu':True,'segmentSeconds':1,'regroup':True,'autoText':False,'autoCover':False,'autoRecords':False,'subtitleAuto':False,'speed':1,'pipelineHighlight':False})
def execute(label):
    jid=s.uuid.uuid4().hex[:12];j={'id':jid,'kind':'transcode','ids':[p['id']],'options':{'encodingPlanVersion':2},'config':copy.deepcopy(cfg),'sourceSnapshot':s.source_snapshot([p['id']]),'cancel':threading.Event(),'processes':set(),'checkpoints':{},'completedStages':[],'status':'queued'}
    s.JOBS[jid]=j
    with patch.object(s.shutil,'rmtree',lambda path:None):s.worker(jid,[p['id']],'transcode',cfg)
    assert j['status']=='completed',j.get('error')
    files=s.get_project(p['id'])['finalVideoPaths'];counts=[]
    for f in files:
        raw=s.ff(['-i',f,'-map','0:v:0','-f','framemd5','-']).decode()
        counts.append(sum(bool(line and not line.startswith('#')) for line in raw.splitlines()))
    assert counts==[30,30,18],counts
    assert all(s.probe(f)['audio'] for f in files)
    runs[label]={'status':j['status'],'encoding':j['encoding'],'framesPerOutput':counts,'outputsHaveAudio':True}
    return j
if real_environment['gpu']['available']:
    j=execute('actual_nvenc')
    check('real_nvenc_outputs_valid_frames_and_audio',j['encoding']['videoEncoder']=='h264_nvenc' and not j.get('gpuFallback'))
    cfg.update(width=1080,height=1920)
    j=execute('actual_vertical_1080p_nvenc')
    files=s.get_project(p['id'])['finalVideoPaths']
    check('real_vertical_1080p_gpu_outputs_valid',not j.get('gpuFallback') and all((s.probe(f)['width'],s.probe(f)['height'])==(1080,1920) for f in files))
    cfg.update(width=320,height=180)
with patch.object(g,'probe',return_value=unavailable):j=execute('probe_failure_cpu')
check('unavailable_gpu_runs_real_cpu_outputs',j['encoding']['videoEncoder']=='libx264' and j['config']['gpu'] and j['encoding']['fallbackCode']=='driver_version')
check('probe_cpu_fallback_can_keep_video_copy',j['encoding']['regroupMode']=='video_copy')
real_ff=s.ff;attempts=[];observed_encoders=[]
def fail_start(args,job=None):
    if '-c:v' in args and args[args.index('-c:v')+1]=='h264_nvenc':attempts.append(args);raise RuntimeError('[h264_nvenc] OpenEncodeSessionEx failed: out of memory (10)')
    result=real_ff(args,job)
    if job:observed_encoders.extend(row.get('encoder') for row in s.JOBS[job].get('telemetry',{}).get('rows',[]))
    return result
with patch.object(g,'probe',return_value=ready),patch.object(s,'ff',fail_start):j=execute('runtime_failure_cpu')
check('runtime_startup_failure_retries_cpu_once_and_stays_cpu',len(attempts)==1 and j['gpuFallback']['runtime'] and j['encoding']['videoEncoder']=='libx264')
check('actual_progress_reports_cpu_after_fallback','CPU · libx264' in observed_encoders)
summary=tp.report(j)
check('diagnostic_records_safe_fallback_reason',summary['encoding']['fallbackCode']=='encoder_busy' and str(BASE) not in json.dumps(summary,ensure_ascii=False))
for backend_id in ('amf','qsv'):
    backend=next(b for b in g.BACKENDS if b['id']==backend_id)
    candidate={'available':True,'profile':'standard','encoderArgs':backend['profiles'][0][1].copy(),'code':'ready','detail':'injected hardware startup path'}
    attempts=[]
    def fail_other_hardware(args,job=None):
        if '-c:v' in args and args[args.index('-c:v')+1]==backend['codec']:
            attempts.append(args)
            message='AMF failed to initialise on given DX11 device' if backend_id=='amf' else 'Error initializing a MFX session: unsupported (-3)'
            raise RuntimeError('['+backend['codec']+'] '+message)
        return real_ff(args,job)
    with patch.object(g,'probe',return_value=candidate),patch.object(s,'ff',fail_other_hardware):j=execute(backend_id+'_startup_cpu_fallback')
    check(backend_id+'_startup_failure_uses_real_cpu_outputs',len(attempts)==1 and j['encoding']['videoEncoder']=='libx264' and j['gpuFallback']['runtime'])
if real_environment['gpu']['available']:
    attempts=[]
    def fail_second(args,job=None):
        if '-c:v' in args and args[args.index('-c:v')+1]=='h264_nvenc':
            attempts.append(args)
            if len(attempts)==2:raise RuntimeError('[h264_nvenc] OpenEncodeSessionEx failed: out of memory (10)')
        return real_ff(args,job)
    with patch.object(g,'probe',return_value=ready),patch.object(s,'ff',fail_second):j=execute('mixed_gpu_cpu')
    values={v.get('videoEncoder') for k,v in j['checkpoints'].items() if ':encode-v2:' in k}
    check('mixed_gpu_cpu_sources_are_normalized_before_merge',values=={'h264_nvenc','libx264'} and j['encoding']['regroupMode']=='reencode_fallback')
check('original_files_are_unchanged',all(s.sha256(path)==digest for path,digest in before.items()))
report={'version':VERSION,'sourceOnly':not COMPILED,'installerBuilt':False,'compiled':COMPILED,'passed':len(checks),'checks':checks,'environment':{k:v for k,v in real_environment.items() if k!='data'},'runs':runs,'base':str(BASE),'faultInjectionUsed':True}
(ROOT/('tmp/gpu-fallback-compiled-report.json' if COMPILED else 'tmp/gpu-fallback-source-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
