"""Encoder quality and bounded GPU-filter diagnostics, with synthetic media only."""
from pathlib import Path
import copy,hashlib,json,os,re,subprocess,sys,tempfile,time

ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT))
import gpu_encoding as g

BASE=Path(tempfile.mkdtemp(prefix='transform-quality-',dir=ROOT/'tmp'))
EXE=next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe'))
checks=[];runs={}

def check(name,value=True):
    assert value,name
    checks.append(name)

def rejects(name,fn):
    try:fn()
    except ValueError:check(name)
    else:raise AssertionError(name)

def value(args,name):return args[args.index(name)+1]

def ff(args,timeout=30):
    result=subprocess.run([str(EXE),'-hide_banner','-loglevel','error','-nostdin','-y',*map(str,args)],capture_output=True,timeout=timeout)
    if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace'))
    return result.stdout

original_cpu=g.CPU_ARGS.copy();original_backends=copy.deepcopy(g.BACKENDS)
profiles=[g.CPU_ARGS]+[args for backend in g.BACKENDS for _,args in backend['profiles']]
for i,args in enumerate(profiles):
    result=g.quality_args(args)
    check(f'balanced_profile_{i}_is_byte_exact',result==args and result is not args)
    result[0]='changed test copy'
    check(f'balanced_profile_{i}_does_not_mutate_base',args[0]=='-c:v')

for quality,preset,crf in [('speed','veryfast','23'),('balanced','fast','21'),('quality','medium','19')]:
    selected=g.quality_args(g.CPU_ARGS,quality)
    check('cpu_'+quality+'_uses_declared_starting_point',value(selected,'-preset')==preset and value(selected,'-crf')==crf)
    for backend in g.BACKENDS:
        candidate=backend['profiles'][0][1];mapped=g.quality_args(candidate,quality)
        check(backend['id']+'_'+quality+'_preserves_codec',value(mapped,'-c:v')==backend['codec'])
        actual=['-i','source.mp4',*mapped,'-pix_fmt','nv12','-bf','0','-frames:v','60','output.mp4']
        fallback=g.cpu_arguments(actual)
        check(backend['id']+'_'+quality+'_fallback_retains_quality',value(fallback,'-preset')==preset and value(fallback,'-crf')==crf)
        check(backend['id']+'_'+quality+'_fallback_keeps_input_output_frames',fallback[1]=='source.mp4' and fallback[-1]=='output.mp4' and value(fallback,'-frames:v')=='60' and value(fallback,'-pix_fmt')=='yuv420p')
        check(backend['id']+'_'+quality+'_fallback_removes_gpu_controls',not any(k in fallback for k in ('-cq','-quality','-qp_i','-qp_p','-global_quality','-look_ahead','-forced_idr','-forced-idr')))

standard=g.PROFILES[0][1];legacy=g.PROFILES[1][1]
check('nvenc_speed_maps_p2',value(g.quality_args(standard,'speed'),'-preset')=='p2')
check('nvenc_quality_maps_p6',value(g.quality_args(standard,'quality'),'-preset')=='p6')
for level in ('speed','quality'):
    mapped=g.quality_args(legacy,level)
    check('nvenc_legacy_'+level+'_keeps_tested_preset',value(mapped,'-preset')=='default' and not any(re.fullmatch(r'p[1-7]',x) for x in mapped))
check('amf_quality_maps_its_own_quality_option',value(g.quality_args(g.BACKENDS[1]['profiles'][0][1],'quality'),'-quality')=='quality')
check('qsv_speed_maps_its_own_preset',value(g.quality_args(g.BACKENDS[2]['profiles'][0][1],'speed'),'-preset')=='veryfast')
explicit=g.cpu_arguments(['-i','source.mp4',*standard,'output.mp4'],quality='quality')
check('explicit_cpu_fallback_quality_is_supported',value(explicit,'-crf')=='19' and value(explicit,'-preset')=='medium')
cpu_twice=g.cpu_arguments(['-i','source.mp4',*g.quality_args(g.CPU_ARGS,'speed'),'output.mp4'])
check('cpu_fallback_does_not_duplicate_quality_options',cpu_twice.count('-preset')==1 and cpu_twice.count('-crf')==1 and value(cpu_twice,'-crf')=='23')
check('base_profiles_remain_unchanged',g.CPU_ARGS==original_cpu and g.BACKENDS==original_backends)
for level in ('',None,True,1,'extreme'):
    rejects('invalid_quality_rejected_'+repr(level),lambda level=level:g.quality_args(g.CPU_ARGS,level))

listed=[]
def list_filters(args):
    listed.append(args)
    return b'Filters:\n .S. scale_cuda V->V Resize\n T.C cropdetect V->V Detect\n ... libvmaf VV->V Quality\n'
caps=g.filter_capabilities('controlled-filter-list',force=True,runner=list_filters)
check('filter_listing_is_not_runtime_success',caps['listed'] and not caps['runtimeTested'] and caps['filters']['scale_cuda'] and not caps['filters']['ssim'])
caps['filters']['scale_cuda']=False
again=g.filter_capabilities('controlled-filter-list',runner=lambda args:(_ for _ in ()).throw(AssertionError('cache miss')))
check('filter_capability_cache_is_detached',again['filters']['scale_cuda'] and len(listed)==1)
not_listed=g.filter_capabilities('controlled-list-timeout',force=True,runner=lambda args:(_ for _ in ()).throw(subprocess.TimeoutExpired('ffmpeg',8)))
check('failed_listing_does_not_imply_filter_absence',not not_listed['listed'] and not not_listed['runtimeTested'] and not_listed['code']=='filter_list_failed')
check('missing_filter_engine_has_clear_status',g.filter_capabilities(None,force=True)['code']=='engine_missing')

chain_calls=[]
def three_frames(args):chain_calls.append(args);return b'frame=3\nprogress=end\n'
chain=g.probe_filter_chain('controlled-filter-chain',320,180,force=True,runner=three_frames)
check('filter_chain_test_is_bounded_and_opt_in',chain['available'] and chain['runtimeTested'] and chain['frames']==3 and chain['autoEnabled'] is False and value(chain_calls[0],'-frames:v')=='3')
check('filter_chain_does_real_dimension_change',(chain['inputWidth'],chain['inputHeight'])!=(chain['width'],chain['height']))
g.probe_filter_chain('controlled-filter-chain',320,180,runner=lambda args:(_ for _ in ()).throw(AssertionError('cache miss')))
check('filter_chain_diagnostic_cached',len(chain_calls)==1)
zero=g.probe_filter_chain('controlled-filter-zero',force=True,runner=lambda args:b'frame=0\nprogress=end\n')
check('zero_filtered_frames_rejected',not zero['available'] and zero['code']=='filter_chain_unavailable')
timed=g.probe_filter_chain('controlled-filter-timeout',force=True,runner=lambda args:(_ for _ in ()).throw(subprocess.TimeoutExpired('ffmpeg',8)))
check('filter_chain_timeout_retains_cpu_path',not timed['available'] and timed['code']=='probe_timeout' and timed['autoEnabled'] is False)
try:g.probe_filter_chain('controlled-filter-cancel',force=True,runner=lambda args:(_ for _ in ()).throw(InterruptedError('stopped')))
except InterruptedError:check('filter_chain_cancel_propagates')
else:raise AssertionError('cancel swallowed')
for dimensions in [(True,180),(320,False),(63,180),(321,180),(4000,180),(float('inf'),180),('invalid',180)]:
    rejects('invalid_diagnostic_dimensions_'+repr(dimensions),lambda dimensions=dimensions:g.probe_filter_chain('never-run',*dimensions,runner=lambda args:(_ for _ in ()).throw(AssertionError('invalid input reached process'))))

# Actual binary enumeration and a tiny CUDA resize diagnostic. Driver failure is
# reported as a diagnostic result; the product's CPU-compatible path stays valid.
actual_caps=g.filter_capabilities(EXE,force=True)
check('actual_installed_filter_list_read',actual_caps['listed'] and actual_caps['filters']['ssim'] and actual_caps['filters']['psnr'])
actual_chain=g.probe_filter_chain(EXE,320,180,force=True)
if actual_chain['available']:check('actual_cuda_three_frame_resize_passed',actual_chain['frames']>=3 and actual_chain['runtimeTested'])
else:check('actual_cuda_unavailable_keeps_cpu_filter_path',actual_chain['code'] in ('filter_chain_unavailable','probe_timeout') and not actual_chain['autoEnabled'])

# Three real CPU quality outputs must keep complete video frames and audio.
source=BASE/'source.mp4'
ff(['-f','lavfi','-i','testsrc2=s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',source])
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
def audio_digest(path):return hashlib.sha256(ff(['-i',path,'-map','0:a:0','-vn','-f','s16le','-'])).hexdigest()
original_audio=audio_digest(source)
for level in g.QUALITY_LEVELS:
    target=BASE/(level+'.mp4');selected=g.quality_args(g.CPU_ARGS,level);started=time.monotonic()
    ff(['-i',source,'-map','0:v:0','-map','0:a:0','-vf','eq=contrast=1.02',*selected,'-c:a','copy','-pix_fmt','yuv420p',target])
    elapsed=time.monotonic()-started
    frames=ff(['-i',target,'-map','0:v:0','-an','-f','framemd5','-']).decode('utf-8')
    count=sum(bool(line and not line.startswith('#')) for line in frames.splitlines())
    check('actual_cpu_'+level+'_all_frames_decode',count==60)
    check('actual_cpu_'+level+'_audio_unchanged',audio_digest(target)==original_audio)
    runs[level]={'seconds':round(elapsed,3),'bytes':target.stat().st_size,'frames':count,'encoderArgs':selected,'audioPcmMatchesSource':True}
check('synthetic_source_unchanged',hashlib.sha256(source.read_bytes()).hexdigest()==source_hash)

hardware=g.probe(EXE,320,180,force=True);hardware_runs={}
if hardware['available']:
    for level in g.QUALITY_LEVELS:
        selected=g.quality_args(hardware['encoderArgs'],level)
        target=BASE/('hardware-'+level+'.mp4')
        command=['-i',str(source),'-map','0:v:0','-map','0:a:0','-vf','eq=contrast=1.02',*selected,'-c:a','copy','-pix_fmt','yuv420p',str(target)]
        command=g.prepare_arguments(command);used=value(command,'-c:v');fallback=False
        try:ff(command)
        except RuntimeError as error:
            if not g.startup_failure(error):raise
            command=g.cpu_arguments(command);used='libx264';fallback=True;ff(command)
        frames=ff(['-i',target,'-map','0:v:0','-an','-f','framemd5','-']).decode('utf-8')
        count=sum(bool(line and not line.startswith('#')) for line in frames.splitlines())
        check('actual_hardware_'+level+'_all_frames_decode',count==60)
        check('actual_hardware_'+level+'_audio_unchanged',audio_digest(target)==original_audio)
        hardware_runs[level]={'videoEncoder':used,'fellBackToCpu':fallback,'frames':count,'bytes':target.stat().st_size,
                              'qualityApplied':level,'encoderArgs':selected}
else:check('unavailable_hardware_is_reported_without_blocking_cpu',hardware.get('code') and all(r['frames']==60 for r in runs.values()))
check('source_unchanged_after_hardware_tests',hashlib.sha256(source.read_bytes()).hexdigest()==source_hash)

report={'passed':len(checks),'checks':checks,'base':str(BASE),'realCPUEncodes':runs,
        'filterCapabilities':actual_caps,'cudaResizeDiagnostic':actual_chain,
        'hardwareProbe':hardware,'realHardwareQualityOutputs':hardware_runs,
        'qualityValuesComparableAcrossBackends':False,'externalModelsCalled':False,'installerBuilt':False,
        'sourceMedia':'newly generated 2-second 320x180 testsrc2 plus sine audio',
        'completeProductGpuFilterPipelineEnabled':False}
(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
(ROOT/'tmp/transform-quality-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'base':str(BASE),'actualCudaResize':actual_chain['available'],'realCpuQualityOutputs':len(runs),'hardwareQualityOutputs':len(hardware_runs)},ensure_ascii=False))
