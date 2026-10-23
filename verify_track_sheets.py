"""Real FFmpeg/PNG acceptance for the batch track-sheet workflow, no network."""
from pathlib import Path
import argparse,copy,hashlib,json,os,re,shutil,sys,tempfile,threading,time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--compiled',action='store_true');p.add_argument('--version',default='v0.8.3');args=p.parse_args()
BASE=Path(tempfile.mkdtemp(prefix='track-sheets-acceptance-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')));sys.dont_write_bytecode=True
sys.path[:0]=([str(ROOT/'release'/args.version/'漫剧工坊/_internal')] if args.compiled else [])+[str(ROOT/'vendor')]
import server as s,track_sheets as t
from PIL import Image,ImageChops
if args.compiled:
    assert s.__file__.endswith('.pyd') and t.__file__.endswith('.pyd');sys.frozen=True
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0);s.licensing.activate(s.DATA,token)
checks=[]
def check(name,value=True):assert value,name;checks.append(name);print(name,flush=True)
def rejected(name,fn):
    try:fn()
    except (ValueError,RuntimeError,OSError):check(name)
    else:raise AssertionError(name)
run=lambda a,observe=None,timeout=None:s.run_process(a,observe=observe,timeout=timeout)
source=BASE/'sources';source.mkdir();video=source/'第1集.mp4'
s.ff(['-f','lavfi','-i','color=red:s=480x270:r=25:d=3','-f','lavfi','-i','color=blue:s=480x270:r=25:d=3','-f','lavfi','-i','color=green:s=480x270:r=25:d=3','-f','lavfi','-i','sine=frequency=440:duration=9','-filter_complex','[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]','-map','[v]','-map','3:a','-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(video)])
v={'path':str(video),**s.probe(video)};before=s.sha256(video);event=threading.Event();cache=BASE/'cache';opts=t.options({'device':'cpu','width':1920,'maxSegment':3})
outputs=[]
for n in t.TRACKS:
    result=t.generate(v,{**opts,'tracks':n},cache,s.FFMPEG,run,event);outputs.append(result)
    with Image.open(result['path']) as image:assert image.width==1920 and image.height>600;image.verify()
    record=json.loads(Path(result['manifest']).read_text('utf-8'));assert record['tracks']==n and record['sourceSHA256']==before and record['imageSHA256']==s.sha256(result['path'])
check('all_five_layouts_produce_valid_png_and_source_bound_manifests')
check('changing_track_layout_reuses_analysis',not outputs[0]['cacheHit'] and all(r['cacheHit'] for r in outputs[1:]))
analysis=json.loads(next(cache.glob('*/analysis.json')).read_text('utf-8'))
check('known_scene_changes_detected',any(abs(x['start']-3)<.1 for x in analysis['segments']) and any(abs(x['start']-6)<.1 for x in analysis['segments']))
check('sample_times_are_actual_source_pts',analysis['frames'][0]['time']==0 and abs(analysis['frames'][1]['time']-.76)<.01)
check('original_audio_waveform_is_measured',len(analysis['waveform'])>100 and max(analysis['waveform'])>0)
fast=t.generate(v,{**opts,'tracks':8,'fastPng':True},cache,s.FFMPEG,run,event)
small=t.generate(v,{**opts,'tracks':8,'fastPng':False},cache,s.FFMPEG,run,event)
with Image.open(fast['path']) as a,Image.open(small['path']) as b:check('fast_and_normal_png_have_identical_pixels',ImageChops.difference(a.convert('RGB'),b.convert('RGB')).getbbox() is None)
check('fast_png_is_larger_on_test_frames',Path(fast['path']).stat().st_size>Path(small['path']).stat().st_size)
check('repeated_generation_preserves_previous_png',fast['path']!=small['path'] and Path(fast['path']).is_file())
changed=t.generate(v,{**opts,'threshold':30},cache,s.FFMPEG,run,event);check('changed_analysis_settings_recompute',not changed['cacheHit'])
fresh=t.generate(v,{**opts,'reuse':False},cache,s.FFMPEG,run,event);check('cache_can_be_explicitly_disabled',not fresh['cacheHit'])
key=next(p for p in cache.glob('*/analysis.json') if json.loads(p.read_text('utf-8'))['analysisOptions']['threshold']==24)
data=json.loads(key.read_text('utf-8'));frame=key.parent/data['frames'][0]['file'];frame.write_bytes(b'corrupted-cache')
fixed=t.generate(v,opts,cache,s.FFMPEG,run,event);check('damaged_frame_cache_is_rebuilt',not fixed['cacheHit'])
no_gpu=lambda a,observe=None,timeout=None:(_ for _ in ()).throw(RuntimeError('synthetic hardware failure')) if '-hwaccel' in a else run(a,observe,timeout)
fallback=t.generate(v,{**opts,'device':'gpu','reuse':False},cache,s.FFMPEG,no_gpu,event)
check('unsupported_gpu_falls_back_to_real_cpu_output',fallback['device']['backend']=='cpu' and fallback['device']['fallback'] and Path(fallback['path']).is_file())
real_gpu=t.generate(v,{**opts,'device':'auto','reuse':False},cache,s.FFMPEG,run,event)
check('automatic_device_probe_always_produces_verified_output',Path(real_gpu['path']).is_file())
check('source_video_hash_unchanged',s.sha256(video)==before)

for name,value in [('tracks',4),('tracks',True),('width',12000),('sampleInterval',0),('threshold',float('nan')),('fastPng','yes'),('namePrefix','../escape'),('startNumber',0)]:
    rejected('invalid_'+name+'_'+str(value)+'_rejected',lambda name=name,value=value:t.options({name:value}))
for name in ('第2集.mp4','第3集.mp4'):shutil.copy2(video,source/name)
imported=s.import_track_files([str(source/name) for name in ('第1集.mp4','第2集.mp4','第3集.mp4')]);pid=imported['videos'][0]['projectId'];p0=s.get_project(pid)
check('selected_files_import_into_one_material_project',len(p0['videos'])==3)
s.import_track_files([str(video)]);check('reimport_preserves_other_materials',len(s.get_project(pid)['videos'])==3)
bad=source/'坏视频.mp4';bad.write_bytes(b'not a video');state_before=copy.deepcopy(s.STATE['projects'])
rejected('invalid_media_import_rejected',lambda:s.import_track_files([str(video),str(bad)]));check('invalid_import_is_atomic',s.STATE['projects']==state_before)
rejected('more_than_thirty_import_files_rejected',lambda:s.import_track_files([str(video)]*31))
paths=[str(source/name) for name in ('第3集.mp4','第1集.mp4','第2集.mp4')]
body={'kind':'track_sheet','ids':[pid],'sourceVideoPaths':{pid:paths},'trackOrder':paths,'trackSheet':{**opts,'output':str(BASE/'batch-output')}}
plan=s.track_plan(body);check('preflight_reports_exact_selected_outputs',plan['count']==3 and plan['files'][0]['name']=='第3集.mp4')
rejected('foreign_selection_rejected',lambda:s.track_plan({**body,'sourceVideoPaths':{pid:[str(bad)]}}))
rejected('single_mode_requires_one_video',lambda:s.track_plan({**body,'sheetMode':'single'}))
rejected('duplicate_processing_order_rejected',lambda:s.track_plan({**body,'trackOrder':[paths[0]]*3}))
with patch.object(s,'ensure_runner'):
    job_id=s.create_job(body)['id']
original_generate=t.generate;failed_once=[False]
def fail_middle(video,*a,**kw):
    if Path(video['path']).name=='第1集.mp4' and not failed_once[0]:failed_once[0]=True;raise OSError('isolated one-file write failure')
    return original_generate(video,*a,**kw)
with patch.object(t,'generate',side_effect=fail_middle):s.worker(job_id,[pid],'track_sheet',s.JOBS[job_id]['config'])
j=s.JOBS[job_id];check('single_file_failure_does_not_abandon_later_selected_files',j['status']=='failed' and len(j['trackResults'])==2 and len(j['trackErrors'])==1)
saved={r['path']:Path(r['path']).stat().st_mtime_ns for r in j['trackResults']}
with patch.object(s,'ensure_runner'):s.control_job(job_id,'resume')
s.worker(job_id,[pid],'track_sheet',j['config'])
check('retry_completes_only_missing_outputs',j['status']=='completed' and len(j['trackResults'])==3 and all(Path(p).stat().st_mtime_ns==mtime for p,mtime in saved.items()))
check('original_files_preserved_after_batch',all(s.sha256(path)==before for path in paths))
check('generated_files_registered_for_protected_preview',all(s.allowed_file(row['path']).is_file() for row in j['trackResults']))
check('batch_results_and_checkpoints_persisted',any(x['id']==job_id and len(x.get('trackResults',[]))==3 for x in json.loads((s.DATA/'jobs.json').read_text('utf-8'))))

cancel=threading.Event();cancel.set()
try:t.generate(v,opts,BASE/'cancel-cache',s.FFMPEG,run,cancel)
except InterruptedError:check('cancelled_work_does_not_start_decode')
else:raise AssertionError('cancel ignored')
silent=source/'无音轨.mp4';s.ff(['-f','lavfi','-i','testsrc2=s=270x480:r=25:d=2','-an','-c:v','libx264','-preset','ultrafast',str(silent)])
silent_result=t.generate({'path':str(silent),**s.probe(silent)},opts,cache,s.FFMPEG,run,event)
check('portrait_video_without_audio_generates_real_video_only_lanes',json.loads(Path(silent_result['manifest']).read_text('utf-8'))['audio'] is False)
named=t.options({**opts,'naming':'episode','namePrefix':'验收剧','startNumber':5,'digits':3})
check('output_naming_preview_matches_export_name',t.filename(v,named,2)=='验收剧_第007集_8轨.png')
report={'version':args.version,'compiled':args.compiled,'passed':len(checks),'checks':checks,'base':str(BASE),'gpuResult':real_gpu['device'],'hardwareFailureInjected':True,'network':False,'sourceVideoPreserved':True,'outputExamples':outputs}
(ROOT/('tmp/track-sheets-compiled-report.json' if args.compiled else 'tmp/track-sheets-source-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'compiled':args.compiled,'base':str(BASE),'gpu':real_gpu['device']},ensure_ascii=True),flush=True)
s.shutdown_jobs()
