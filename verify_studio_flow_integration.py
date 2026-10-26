"""Real-media flow acceptance, isolated from user projects and platform writes."""
from pathlib import Path
import copy,json,os,re,sys,tempfile,time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='studio-flow-real-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')];sys.dont_write_bytecode=True
import server as s

checks=[]
def check(name,value=True):
    assert value,name
    checks.append(name);print('PASS '+name,flush=True)
def rejected(name,work):
    try:work()
    except ValueError:check(name)
    else:raise AssertionError(name)
def wait_flow(manager,fid,target=None,timeout=80):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        manager.tick();f=next(f for f in manager.public()['flows'] if f['id']==fid)
        if f['status']=='failed':raise AssertionError(f['message'])
        if (target and f['currentStage']==target) or (not target and f['status']=='completed'):return f
        time.sleep(.08)
    raise AssertionError('flow timeout '+str(f))

token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
s.licensing.activate(s.DATA,token)
source=BASE/'source';source.mkdir()
for i in range(2):
    s.ff(['-f','lavfi','-i',f'testsrc2=size=320x180:rate=15:duration={1.3+i*.2}',
          '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-shortest',
          '-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source/f'{i+1:02}.mp4')])
pid=s.scan(str(source))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True
paths=[v['path'] for v in p['videos']];hashes={x:s.sha256(x) for x in paths}
s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,segmentSeconds=1,parallel=1,
    gpu=False,regroup=False,subtitleAuto=False,autoText=False,autoCover=False,autoRecords=False,autoCost=False,pipelineHighlight=False)
s.STATE['jianyingOptions']={'output':str(BASE/'projects'),'splitScenes':False,'draftRoot':str(BASE/'drafts'),'executable':''}
manager=s.flow_manager();manager._stop.set() # deterministic ticks, real existing job runner still operates
body={'projectIds':[pid],'sourceVideoPaths':{pid:[paths[1]]},'options':{'withJianying':False,'withEvidence':False,'withExport':False,'withPublish':False}}
try:
    flow=manager.start(body);fid=flow['id']
    check('public_flow_hides_frozen_config','config' not in flow and 'sourceSnapshot' not in flow)
    raw=next(f for f in s.STATE['studioFlows']['flows'] if f['id']==fid)
    s.STATE['config']['segmentSeconds']=7
    check('running_flow_uses_frozen_config',raw['config']['segmentSeconds']==1)
    rejected('duplicate_flow_does_not_repeat_production',lambda:manager.start(body))
    rejected('standalone_cannot_replace_active_flow_outputs',lambda:s.create_job({'kind':'transcode','ids':[pid]}))
    manager._stop.clear()
    completed=wait_flow(manager,fid)
    job=s.JOBS[completed['stages'][0]['ref']['id']]
    check('real_media_pipeline_automatically_completes',completed['status']=='completed' and job['status']=='completed')
    check('exact_selected_episode_preserved',job['options']['sourceVideoPaths']=={pid:[paths[1]]})
    outputs=completed['stages'][0]['result']['videos'][pid]
    check('produced_output_readable_with_audio',len(outputs)==1 and s.probe(outputs[0]['path'])['audio'])
    check('disabled_stages_are_explicitly_skipped',all(x['status']=='skipped' for x in completed['stages'][1:]))
    before=len(s.JOBS)
    for _ in range(4):manager.tick()
    check('completed_flow_poll_never_creates_another_job',len(s.JOBS)==before)

    s.STATE['config']['segmentSeconds']=1
    with patch('jianying_automation.open_registered_project',return_value={'status':'waiting_action','projectOpened':False,'message':'controlled test: native app not opened'}):
        flow=manager.start({'projectIds':[pid],'sourceVideoPaths':{pid:[paths[1],paths[0]]},'options':{'withJianying':True,'withEvidence':True,'withExport':False,'withPublish':False}})
        fid=flow['id'];evidence=wait_flow(manager,fid,'evidence')
        end=time.monotonic()+10
        while time.monotonic()<end:
            manager.tick();evidence=next(f for f in manager.public()['flows'] if f['id']==fid)
            if evidence['status']=='waiting_action':break
            time.sleep(.05)
    check('real_production_automatically_hands_off_to_jianying',evidence['stages'][2]['status']=='completed')
    jy=s.JOBS[evidence['stages'][2]['ref']['ids'][0]]
    check('all_selected_finals_get_real_editable_drafts',len(jy['jianyingResults'])==2 and all(s.jianying_projects.check(r['directory']) for r in jy['jianyingResults']))
    imported=[r['editorImport'] for r in jy['jianyingResults']]
    check('drafts_automatically_copied_into_isolated_editor_root',all(Path(r['directory']).parent==BASE/'drafts' for r in imported))
    check('no_copy_is_mislabeled_editor_accepted',all(r['editorValidated'] is False for r in imported))
    check('screenshot_gate_does_not_fabricate_proof',evidence['reason']=='evidence' and not evidence['stages'][4]['result']['proofImages'])
    jid=evidence['stages'][0]['ref']['id'];stat={v['path']:Path(v['path']).stat().st_mtime_ns for v in evidence['stages'][0]['result']['videos'][pid]};count=len(s.JOBS)
    for _ in range(4):manager.tick()
    check('evidence_wait_preserves_video_and_job_count',len(s.JOBS)==count and all(Path(x).stat().st_mtime_ns==t for x,t in stat.items()))
    paused=manager.control(fid,'pause');check('whole_flow_pause_is_explicit',paused['status']=='paused')
    resumed=manager.control(fid,'resume');check('resume_keeps_real_completed_stages',resumed['stages'][0]['status']=='completed' and len(s.JOBS)==count)
    row=jy['jianyingResults'][0];folders=len(list((BASE/'drafts').iterdir()))
    repeat=s.jianying_projects.install_to_editor(row['directory'],s.STATE['jianyingOptions'],operation_id=fid+'-'+jy['id']+'-0')
    check('stable_import_operation_reuses_same_copy',repeat['reused'] and repeat['directory']==row['editorImport']['directory'] and len(list((BASE/'drafts').iterdir()))==folders)
    manager.control(fid,'cancel');check('cancel_retains_completed_files',all(Path(x).is_file() for x in stat))
    check('source_media_bytes_unchanged',all(s.sha256(x)==h for x,h in hashes.items()))
    check('no_external_model_or_publish_calls',not s.STATE.get('publishWorkspace',{}).get('tasks') and all(not j.get('accountIds') for j in s.JOBS.values()))
    report={'passed':len(checks),'checks':checks,'base':str(BASE),'projectId':pid,'jobId':jy['id'],'realMedia':True,
            'nativeEditorOpened':False,'platformSubmitted':False,'packaged':False}
    (ROOT/'tmp/studio-flow-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/studio-flow-preview-seed.json').write_text(json.dumps({'base':str(BASE),'projectId':pid,'jobId':jy['id']},ensure_ascii=False),'utf-8')
    print(json.dumps({'passed':len(checks),'base':str(BASE)},ensure_ascii=False))
finally:s.shutdown_jobs()
