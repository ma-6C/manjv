"""Real encoding pass counts, pipeline compatibility and transform API validation."""
from pathlib import Path
from unittest.mock import patch
import copy,json,os,sys,tempfile,time
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='transform-pipeline-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,transform_tools as t,gpu_encoding as g
report={'base':str(BASE),'checks':[],'runs':{},'ok':False}
def check(name,ok=True):
    assert ok,name
    report['checks'].append(name);print('PASS '+name,flush=True)
def rejects(label,fn):
    try:fn()
    except (ValueError,TypeError):check(label)
    else:raise AssertionError(label)
def create(body):
    with patch.object(s,'ensure_runner',lambda:None):return s.JOBS[s.create_job(body)['id']]
def run(job):
    began=time.perf_counter()
    with patch.object(s,'encode_media',wraps=s.encode_media) as encode:
        s.worker(job['id'],job['ids'],job['kind'],job['config'])
    assert job['status']=='completed',job.get('error')
    return encode.call_count,time.perf_counter()-began
try:
    cfg=copy.deepcopy(s.STATE['config'])
    for key in ('speed','brightness','contrast','cropPercent'):
        rejects(key+'_rejects_boolean',lambda key=key:s.validate_config(cfg|{key:True}))
        rejects(key+'_rejects_blank',lambda key=key:s.validate_config(cfg|{key:''}))
    normalized=s.validate_config(cfg|{'highlightMin':'1.5','highlightMax':'2.0','speed':'1.25'})
    check('numeric_strings_normalize_before_comparison',normalized['speed']==1.25 and normalized['highlightMin']==1.5)
    values={k:normalized[k] for k in t.CONFIG_FIELDS}
    saved=s.transform_presets({'action':'save','name':'客户横版','values':values});pid=saved['id']
    check('preset_persists_only_transform_values',saved['presets'][0]['values']['speed']==1.25 and set(saved['presets'][0]['values'])==set(t.CONFIG_FIELDS))
    previous=copy.deepcopy(s.STATE['config'])
    rejects('preset_rejects_secret_and_preserves_config',lambda:s.transform_presets({'action':'save','name':'bad','values':{'apiKey':'no-key'}}))
    check('invalid_preset_is_atomic',s.STATE['config']==previous)
    try:
        with patch.object(s,'save',side_effect=OSError('injected disk failure')):
            s.transform_presets({'action':'save','name':'保存失败测试','values':values})
    except OSError:pass
    else:raise AssertionError('disk failure was swallowed')
    check('save_failure_restores_accepted_in_memory_config',s.STATE['config']==previous)
    s.save()
    with patch.object(s,'persist_jobs',side_effect=OSError('injected task metadata failure')):
        try:s.store_config(s.validate_config(copy.deepcopy(previous)|{'brightness':.08}))
        except OSError:pass
        else:raise AssertionError('late save failure was swallowed')
    check('late_save_failure_restores_config_on_disk',s.STATE['config']==previous and
          json.loads((s.DATA/'state.json').read_text('utf-8'))['config']==previous)
    changed=s.transform_presets({'action':'save','id':pid,'name':'重命名','values':values|{'brightness':.05}})
    check('preset_updates_existing_id',len(changed['presets'])==1 and changed['presets'][0]['id']==pid)
    removed=s.transform_presets({'action':'delete','id':pid})
    check('preset_can_be_removed',removed['presets']==[])
    folder=BASE/'source';folder.mkdir()
    for i,seconds in enumerate((6,4)):
        s.ff(['-f','lavfi','-i',f'testsrc2=size=640x360:rate=30:duration={seconds}',
              '-f','lavfi','-i',f'sine=frequency={440+i*220}:sample_rate=48000:duration={seconds}',
              '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(folder/f'{i+1:03d}.mp4')])
    p=s.scan(str(folder))['projects'][0];p['rights']=True;ids=[p['id']]
    source_hashes={v['path']:s.sha256(v['path']) for v in p['videos']}
    s.STATE['config']=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':640,'height':360,
        'parallel':1,'gpu':False,'regroup':False,'speed':1.25,'transformCropMode':'edges',
        'cropLeft':4,'cropRight':2,'cropTop':3,'cropBottom':1,'brightness':.03,'contrast':1.05,'saturation':1.1,
        'pipelineHighlight':True,'highlightRandom':False,'highlightFixed':.25,'highlightCount':1,'highlightParallel':1,
        'highlightLowResource':False,'highlightTailEnabled':False,'highlightMusic':'','endingText':'',
        'subtitleAuto':False,'autoText':False,'autoCover':False,'autoRecords':False,'autoCost':False})
    rejects('preview_rejects_boolean_video_index',lambda:create({'kind':'transform_preview','ids':ids,'videoIndex':True}))
    rejects('preview_rejects_out_of_range_time',lambda:create({'kind':'transform_preview','ids':ids,'start':20}))
    preview=create({'kind':'transform_preview','ids':ids,'videoIndex':1,'start':0,'seconds':10})
    check('preview_clamps_to_remaining_source',preview['options']['seconds']==4)
    preview.update(status='cancelled')
    for mode in ('legacy','fused'):
        job=create({'kind':'pipeline','ids':ids,'sourceVideoPaths':{p['id']:[v['path'] for v in p['videos']]}})
        if mode=='legacy':job['options'].pop('transformPlanVersion',None)
        count,elapsed=run(job)
        files=list(p['finalVideoPaths'])
        for f in files:s.run_process([s.FFMPEG,'-v','error','-i',f,'-f','null','-'])
        details=[s.probe(f) for f in files]
        check(mode+'_duration_audio_and_output_count',len(files)==2 and all(v['audio'] for v in details)
              and all(abs(v['duration']-wanted)<.15 for v,wanted in zip(details,(6,4))))
        check(mode+'_full_video_decode',True)
        check(mode+'_picture_and_packaging_complete',{'video','highlight'}<=set(job['completedStages']))
        report['runs'][mode]={'encodeCalls':count,'seconds':round(elapsed,3),'encoding':job.get('encoding'),
                              'outputs':files,'duration':[v['duration'] for v in details]}
        if mode=='fused':
            check('fused_render_once_per_source',count==2 and job['encoding']['compositionPasses']==1)
            stamp={f:Path(f).stat().st_mtime_ns for f in files}
            job['checkpoints'].pop(p['id']+':project-done')
            repeat,_=run(job)
            check('resume_reuses_verified_final_outputs',repeat==0 and all(Path(f).stat().st_mtime_ns==v for f,v in stamp.items()))
    check('encoding_calls_halved',report['runs']['legacy']['encodeCalls']==4 and report['runs']['fused']['encodeCalls']==2)
    check('original_media_unchanged',all(s.sha256(f)==h for f,h in source_hashes.items()))
    # Regroup and older task snapshots retain their existing exact-split route.
    s.STATE['config'].update(regroup=True,segmentSeconds=3,pipelineHighlight=False)
    exact=create({'kind':'transcode','ids':ids});count,_=run(exact)
    check('regroup_keeps_existing_stream_copy_plan',exact['encoding']['regroupMode']=='video_copy')
    frames=[]
    for f in p['finalVideoPaths']:
        raw=s.ff(['-i',f,'-map','0:v:0','-f','framemd5','-']).decode()
        frames.append(sum(bool(x and not x.startswith('#')) for x in raw.splitlines()))
    check('exact_split_retains_all_processed_frames',frames==[90,90,60])
    neutral=s.STATE['config']|{'speed':1,'brightness':0,'contrast':1,'saturation':1,
        'transformCropMode':'symmetric','cropPercent':0,'width':640,'height':360}
    graph=s.filters(neutral,p['videos'][0],BASE)
    check('neutral_transform_skips_setpts_eq_and_scale',graph=='fps=30,setsar=1')
    finals={f:Path(f).stat().st_mtime_ns for f in p['finalVideoPaths']}
    run(preview)
    check('preview_does_not_replace_or_modify_final_videos',list(finals)==p['finalVideoPaths'] and
          all(Path(f).stat().st_mtime_ns==stamp for f,stamp in finals.items()))
    check('preview_has_actual_comparison_and_metric',preview['transformPreviewResult']['metrics']['status']=='completed'
          and all(Path(preview['transformPreviewResult'][key]).is_file() for key in ('before','after')))
    # Exercise the product's encoder selector, including selected quality on a
    # real CPU retry, rather than checking argument builders alone.
    for quality in ('speed','balanced','quality'):
        cfg=s.validate_config(neutral|{'gpu':True,'encodeQuality':quality,'pipelineHighlight':False,'regroup':False})
        s.STATE['config']=cfg
        job=create({'kind':'transcode','ids':ids,'sourceVideoPaths':{p['id']:[p['videos'][1]['path']]}})
        with patch.object(g,'probe',return_value={'available':False,'code':'driver_version','detail':'injected incompatible driver'}):
            run(job)
        expected={'speed':'23','balanced':'21','quality':'19'}[quality]
        chosen=job['encoderSelection']['args']
        check(quality+'_product_cpu_fallback_keeps_quality',job['encoding']['quality']==quality and chosen[chosen.index('-crf')+1]==expected)
        check(quality+'_fallback_media_decodes_with_audio',s.probe(p['finalVideoPaths'][0])['audio'])
    report.update(ok=True,passed=len(report['checks']))
finally:
    s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/transform-pipeline-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
