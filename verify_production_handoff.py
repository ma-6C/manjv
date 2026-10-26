"""Real local media coverage for continuous production and completed-video handoff."""
from pathlib import Path
import argparse,copy,json,os,re,sys,tempfile,time,threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--compiled',action='store_true');parser.add_argument('--version',default='v0.8.6');args=parser.parse_args()
BASE=Path(tempfile.mkdtemp(prefix='production-handoff-',dir=ROOT/'tmp'));DIST=ROOT/'release'/args.version/'漫剧工坊'
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next(((DIST/'_internal' if args.compiled else ROOT/'vendor')/'imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=([str(DIST/'_internal')] if args.compiled else [str(ROOT)])+[str(ROOT/'vendor')]
if args.compiled:sys.frozen=True
import server as s
if args.compiled:
    assert s.__file__.endswith('.pyd');s.licensing.verify_distribution(DIST)
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    assert s.licensing.activate(s.DATA,token)['valid']

checks=[]
def check(name,value=True):
    assert value,name
    checks.append(name);print('PASS '+name,flush=True)
def rejected(name,action):
    try:action()
    except ValueError:check(name)
    else:raise AssertionError(name)
def create(kind='pipeline',**options):
    with patch.object(s,'ensure_runner',lambda:None):result=s.create_job({'kind':kind,'ids':[pid],**options})
    return s.JOBS[result['id']]
def run(job):s.worker(job['id'],job['ids'],job['kind'],job['config']);return job

source=BASE/'source';source.mkdir()
for index in range(3):
    s.ff(['-f','lavfi','-i',f'testsrc2=size=320x180:rate=30:duration={1.1+index*.1}','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source/f'{index+1:02}.mp4')])
pid=s.scan(str(source))['projects'][0]['id'];project=s.get_project(pid);project['rights']=True
paths=[v['path'] for v in project['videos']];source_hashes={p:s.sha256(p) for p in paths}
s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,segmentSeconds=1,parallel=1,gpu=False,
    regroup=True,subtitleAuto=True,subtitleMode='local',autoText=False,autoCover=True,autoAICover=False,autoRecords=True,autoCost=True,
    pipelineHighlight=True,highlightCount=1,highlightFixed=.1,highlightMin=.1,highlightMax=.1,highlightRandom=False)
s.STATE['config']['costRows']=[{'name':'合成验收费用','amount':1}]
events=[];real_stage=s.stage
def stage(jid,label,progress):events.append((jid,label));return real_stage(jid,label,progress)
with patch.object(s,'stage',stage):pipeline=run(create())
check('full_pipeline_finishes_all_enabled_steps',pipeline['status']=='completed')
check('real_order_subtitle_video_highlight_cover_records_cost',pipeline['currentCompletedStages']==['subtitle','video','highlight','cover','records','cost'])
check('full_pipeline_has_no_external_publish_or_model_calls',not pipeline.get('accountIds') and 'text' not in pipeline['completedStages'])
check('real_subtitle_outputs_exist',sum(a['job']==pipeline['id'] and a['kind']=='字幕处理' for a in project['artifacts'])==3)
final=s.final_videos(project)
check('final_outputs_are_packaged_videos_with_audio',bool(final) and all(a['kind']=='高光视频' and s.probe(a['path'])['audio'] for a in final))
check('cover_and_cost_are_really_written',any(a['job']==pipeline['id'] and a['kind']=='封面' for a in project['artifacts']) and any(a['job']==pipeline['id'] and a['kind']=='成本报告' for a in project['artifacts']))
records_path=next(a['path'] for a in project['artifacts'] if a['job']==pipeline['id'] and Path(a['path']).name=='制作记录.json')
record=json.loads(Path(records_path).read_text('utf-8'))
check('processing_record_references_actual_final_files',{v['file'] for v in record['outputs']}=={v['path'] for v in final} and all(v['sha256']==s.sha256(v['file']) for v in record['outputs']) and record['officialScreenshot'] is False)
check('single_task_plan_does_not_show_followup_steps',len(s.production_plan('transcode',s.STATE['config']))==1)
with patch.dict(s.STATE['config'],costRows=[{'name':'空白成本','amount':0}]):rejected('empty_cost_is_blocked_before_pipeline_submission',lambda:create())
plan=s.public_state()['jobs'][-1]['workflowPlan'];saved_plan=copy.deepcopy(plan)
s.STATE['config']['autoCost']=False
check('task_plan_uses_immutable_task_configuration',s.public_state()['jobs'][-1]['workflowPlan']==saved_plan)
s.STATE['config']['autoCost']=True

selected=[paths[2],paths[0]]
parent=run(create('transcode',sourceVideoPaths={pid:selected}))
check('standalone_merge_remains_single_step',parent['status']=='completed' and parent['completedStages']==['video'])
originals=[Path(path) for path in project['finalVideoPaths']]
stats={str(path):(path.stat().st_mtime_ns,s.sha256(path)) for path in originals}
s.STATE['config'].update(subtitleMode='vsr',vsrRoot='',vsrPython='')
child=create(continueFromJob=parent['id'])
check('continuation_preserves_selected_scope_and_order',child['options']['sourceVideoPaths']=={pid:selected})
check('continuation_omits_subtitle_before_video',not any('subtitle' in step[2] for step in s.production_plan('pipeline',child['config'],True)))
count=len(s.JOBS);same=create(continueFromJob=parent['id'])
check('double_submit_reuses_same_continuation',same['id']==child['id'] and len(s.JOBS)==count)
real_records=s.records
with patch.object(s,'transcode',side_effect=AssertionError('Unexpected repeat encoding')),patch.object(s,'repair_subtitles',side_effect=AssertionError('Unexpected repeat subtitles')),patch.object(s,'records',side_effect=RuntimeError('controlled record failure')):
    run(child)
check('followup_failure_preserves_completed_video_stage',child['status']=='failed' and 'video' in child['completedStages'] and s.cached(child['id'],f'{pid}:video') is not None)
packaged={str(a['path']):(Path(a['path']).stat().st_mtime_ns,s.sha256(a['path'])) for a in s.final_videos(project)}
with patch.object(s,'ensure_runner',lambda:None):s.control_job(child['id'],'resume')
with patch.object(s,'transcode',side_effect=AssertionError('Unexpected repeat encoding')),patch.object(s,'repair_subtitles',side_effect=AssertionError('Unexpected repeat subtitles')):run(child)
check('retry_finishes_followups_without_encoding_or_subtitles',child['status']=='completed' and child['currentCompletedStages']==['video','highlight','cover','records','cost'])
check('completed_highlights_not_reencoded_on_retry',all(Path(p).stat().st_mtime_ns==v[0] and s.sha256(p)==v[1] for p,v in packaged.items()))
check('original_merged_files_hash_and_mtime_unchanged',all(Path(p).stat().st_mtime_ns==v[0] and s.sha256(p)==v[1] for p,v in stats.items()))
check('continuation_does_not_register_a_second_merge',not any(a['job']==child['id'] and a['kind']=='视频' for a in project['artifacts']))
rejected('wrong_parent_kind_rejected',lambda:create(continueFromJob=pipeline['id']))
rejected('foreign_source_selection_rejected',lambda:create(continueFromJob=parent['id'],sourceVideoPaths={pid:[paths[1]]}))
rejected('invalid_parent_identifier_rejected',lambda:create(continueFromJob=[] or {'bad':True}))
rejected('empty_parent_identifier_rejected',lambda:create(continueFromJob=''))
rejected('array_parent_identifier_rejected',lambda:create(continueFromJob=[]))
rejected('continuation_cannot_be_used_with_standalone_kind',lambda:create('transcode',continueFromJob=parent['id']))
hidden=originals[0].with_suffix('.verify-backup')
originals[0].rename(hidden)
try:
    rejected('missing_completed_output_blocks_continuation',lambda:create(continueFromJob=parent['id']))
    rejected('worker_rechecks_output_before_use',lambda:s.continued_video_files(child['options'],pid))
finally:hidden.rename(originals[0])
stat=originals[0].stat();os.utime(originals[0],ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000000))
try:rejected('changed_completed_output_blocks_continuation',lambda:create(continueFromJob=parent['id']))
finally:os.utime(originals[0],ns=(stat.st_atime_ns,stat.st_mtime_ns))
s.STATE['config'].update(autoText=False,pipelineHighlight=False,autoCover=False,autoRecords=False,autoCost=False)
rejected('empty_followup_plan_is_rejected',lambda:create(continueFromJob=parent['id']))
s.STATE['config'].update(autoText=True)
jobs_before=len(s.JOBS)
rejected('missing_ai_key_is_blocked_before_pipeline_submission',lambda:create())
check('preflight_error_does_not_create_a_partial_job',len(s.JOBS)==jobs_before)
check('source_files_preserved',all(s.sha256(p)==value for p,value in source_hashes.items()))
s.STATE['config'].update(autoText=False,subtitleAuto=False,subtitleMode='local',autoRecords=True,autoCover=True,autoCost=False,pipelineHighlight=False)
ui_parent=run(create('transcode',sourceVideoPaths={pid:selected}));assert ui_parent['status']=='completed'
s.save()
report={'version':args.version,'sourceOnly':not args.compiled,'compiled':args.compiled,'installerBuilt':False,'passed':len(checks),'checks':checks,'base':str(BASE),'projectId':pid,'uiParentId':ui_parent['id'],'realFFmpeg':True,'externalApisTested':False,'events':[label for _,label in events]}
report_name='production-handoff-core-compiled-'+args.version+'.json' if args.compiled else 'production-handoff-core.json'
(ROOT/'tmp'/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'base':str(BASE),'realFFmpeg':True},ensure_ascii=True),flush=True)
s.shutdown_jobs()
