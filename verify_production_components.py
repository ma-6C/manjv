"""Real media checks for editable drafts and highlight composition, isolated from user data."""
from pathlib import Path
import os,sys,tempfile,json,copy,threading,shutil,math,array
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='production-components-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,jianying_projects as jy
report={'base':str(BASE),'ok':False,'checks':[]}
def check(name,value=True):assert value,name;report['checks'].append(name);print('PASS '+name,flush=True)
def create(kind,pid,**opts):
    with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':kind,'ids':[pid],**opts})['id']
    return s.JOBS[jid]
def run(j):s.worker(j['id'],j['ids'],j['kind'],j['config']);print('JOB',j['kind'],j['status'],j.get('stage'),flush=True);return j
def audio_rms(path,start,duration=.35):
    # Binary subprocess preserves PCM samples for actual audio measurements.
    import subprocess
    result=subprocess.run([s.FFMPEG,'-v','error','-ss',str(start),'-i',str(path),'-t',str(duration),'-vn','-ac','1','-ar','8000','-f','s16le','-'],capture_output=True,check=True)
    samples=array.array('h',result.stdout);return math.sqrt(sum(x*x for x in samples)/max(1,len(samples)))
try:
    folder=BASE/'source';folder.mkdir();source=folder/'第001集.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=30:duration=2','-f','lavfi','-i','anullsrc=channel_layout=stereo:sample_rate=48000','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source)])
    source.with_suffix('.srt').write_text('1\n00:00:00,100 --> 00:00:01,700\n真实字幕测试\n','utf-8')
    second=folder/'第002集.mp4';shutil.copy2(source,second)
    pid=s.scan(str(folder))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True;hashes={v['path']:s.sha256(v['path']) for v in p['videos']}
    s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,speed=1,brightness=0,contrast=1,saturation=1,cropPercent=0,markAI=False,gpu=False)
    job=run(create('jianying_project',pid,sourceVideoPaths={pid:[str(source)]},trackOrder=[str(source)],jianying={'output':str(BASE/'drafts'),'splitScenes':False}))
    check('real_draft_job_completed',job['status']=='completed')
    row=job['jianyingResults'][0];project=Path(row['directory']);data=json.loads(Path(row['path']).read_text('utf-8'));manifest=jy.check(project)
    check('video_audio_and_srt_are_real_tracks',{t['type'] for t in data['tracks']}=={'video','audio','text'})
    check('actual_video_ranges_cover_complete_timeline',sum(x['duration'] for x in manifest['ranges'])==manifest['durationUs'] and manifest['ranges'][0]['start']==0)
    check('resources_are_copied_and_hashed',len(manifest['assets'])==3 and all((project/a['relative']).is_file() for a in manifest['assets']))
    check('native_editor_validation_is_explicitly_pending',row['editorValidated'] is False)
    check('independent_audio_video_not_double_mixed',data['tracks'][0]['segments'][0]['volume']==0)
    # Public library can deserialize the generated content, independent of our manifest writer.
    import pyJianYingDraft as draft
    loaded=draft.DraftFolder(str(project.parent)).load_template(project.name)
    check('upstream_library_reads_back_generated_draft',loaded.duration==data['duration'])
    moved=BASE/'moved-draft';shutil.copytree(project,moved);jy.relocate(moved);moved_data=json.loads((moved/'draft_content.json').read_text('utf-8'))
    check('moved_draft_relinks_to_its_own_resources',all(Path(m['path']).is_relative_to(moved) for g in ('videos','audios') for m in moved_data['materials'][g] if m.get('path')))
    tamper=moved/'Resources/video.mp4';tamper.write_bytes(tamper.read_bytes()+b'x')
    try:jy.check(moved)
    except ValueError:check('modified_resource_is_rejected')
    else:raise AssertionError('modified asset accepted')
    event=threading.Event();event.set()
    try:jy.generate(p['videos'][0],{'sourceSHA256':hashes[str(source)],'segments':[{'start':0,'end':2}]},BASE/'cancelled',s.FFMPEG,lambda *a,**k:None,event)
    except InterruptedError:check('cancelled_export_does_not_report_completed')
    else:raise AssertionError('cancel ignored')
    job2=run(create('jianying_project',pid,sourceVideoPaths={pid:[str(source),str(second)]},trackOrder=[str(second),str(source)],jianying={'output':str(BASE/'drafts'),'splitScenes':True}))
    check('batch_scene_export_preserves_selected_order',job2['status']=='completed' and [r['sourcePath'] for r in job2['jianyingResults']]==[str(second),str(source)])
    check('no_existing_draft_is_overwritten',Path(row['path']).is_file() and len(list((BASE/'drafts').iterdir()))==3)
    tail=BASE/'templates';tail.mkdir();s.ff(['-f','lavfi','-i','color=red:size=320x180:rate=30:duration=1','-c:v','libx264',str(tail/'片尾.mp4')])
    music=BASE/'music.wav';s.ff(['-f','lavfi','-i','sine=frequency=900:sample_rate=48000:duration=0.5',str(music)])
    s.STATE['config'].update(highlightCount=2,highlightParallel=2,highlightRandom=False,highlightFixed=1,highlightTailEnabled=True,highlightTailDirectory=str(tail),highlightTailChoice='片尾.mp4',highlightMusic=str(music),highlightLowResource=False,endingText='测试结束')
    h=run(create('highlight',pid,sourceVideoPaths={pid:[str(source)]}));outputs=[a['path'] for a in p['artifacts'] if a['job']==h['id'] and a['kind']=='高光视频']
    check('selected_source_only_and_parallel_copies_complete',h['status']=='completed' and len(outputs)==2)
    check('tail_then_freeze_has_expected_six_second_duration',all(abs(s.probe(x)['duration']-6)<.15 for x in outputs))
    for path in outputs:s.run_process([s.FFMPEG,'-v','error','-i',path,'-f','null','-'])
    check('highlight_outputs_fully_decode')
    rms_before=audio_rms(outputs[0],1);rms_tail=audio_rms(outputs[0],2.3);rms_freeze=audio_rms(outputs[0],4)
    check('music_only_plays_after_original_and_tail',rms_before<10 and rms_tail<10 and rms_freeze>100)
    # Last tail frame must be red; freeze must preserve that same final frame.
    import subprocess
    from PIL import Image
    frame=BASE/'freeze.png';s.ff(['-ss','4','-i',outputs[0],'-frames:v','1',str(frame)])
    pixel=Image.open(frame).getpixel((20,20));check('freeze_uses_tail_last_frame',pixel[0]>150 and pixel[1]<50)
    s.STATE['config'].update(highlightCount=1,highlightRandom=True,highlightMin=.1,highlightMax=.2,highlightTailEnabled=False,highlightMusic='',highlightLowResource=True,gpu=True)
    with patch.object(s,'encoder',wraps=s.encoder) as choose:
        h2=run(create('highlight',pid,sourceVideoPaths={pid:[str(second)]}))
        check('low_resource_forces_cpu_without_changing_saved_gpu',h2['status']=='completed' and all(c.args[0]['gpu'] is False for c in choose.call_args_list) and s.STATE['config']['gpu'])
    plan=next(iter(h2['highlightPlan'].values()));check('random_ratio_stays_in_requested_range',.1<=plan['ratio']<=.2)
    before=dict(plan);run(h2);check('resume_retains_random_plan',next(iter(h2['highlightPlan'].values()))==before)
    check('all_original_sources_unchanged',all(s.sha256(path)==digest for path,digest in hashes.items()))
    report.update(ok=True,projectId=pid,jianyingJob=job2['id'],highlightJob=h['id'],draft=row,highlightOutputs=outputs,musicRMS={'source':rms_before,'tail':rms_tail,'freeze':rms_freeze},nativeEditorTested=False)
finally:
    s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/production-components-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'base':str(BASE)},ensure_ascii=False))
