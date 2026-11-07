"""Continue the current verified native downloads through real local production."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import zipfile
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--processing-config',type=Path)
args=parser.parse_args()
processing={}
project_regions={}
if args.processing_config:
    config_path=args.processing_config.resolve()
    if not config_path.is_relative_to((ROOT/'tmp').resolve()):
        raise ValueError('Processing acceptance config must be in the temporary workspace')
    processing=json.loads(config_path.read_text('utf-8'))
    if not isinstance(processing,dict):
        raise ValueError('Processing acceptance settings must be an object')
    project_regions=processing.pop('projectRegions',{})
    if not isinstance(project_regions,dict):
        raise ValueError('Project subtitle regions must be an object')
    allowed={'subtitleMode','subtitleRegion','subtitleRegions','subtitlePreserveTailSeconds','vsrRoot','vsrPython','vsrMode','sttnDevice','lamaDevice','vsrReuseWorker'}
    if set(processing)-allowed:
        raise ValueError('Unsupported processing acceptance setting')
seed=json.loads((ROOT/'tmp/final-hongguo-manager-e2e-latest.json').read_text('utf-8'))
if not seed.get('ok'):raise ValueError('Native collection has not passed')
BASE=Path(seed['base']).resolve();DATA=Path(seed['data']).resolve()
if not BASE.is_relative_to((ROOT/'tmp').resolve()) or not DATA.is_relative_to(BASE):
    raise ValueError('Production acceptance requires disposable isolated data')
manifest=json.loads((ROOT/'engines/guoapp-core/manifest.json').read_text('utf-8'))
with (ROOT/'engines/guoapp-core/duanju_core.dll').open('rb') as stream:
    native_sha=hashlib.file_digest(stream,'sha256').hexdigest()
if native_sha!=manifest['sha256'] or native_sha!=seed['dllSha256']:
    raise ValueError('Native component changed after collection')
os.environ['MANJU_DATA']=str(DATA);os.environ['PYTHONDONTWRITEBYTECODE']='1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s

checks=[];report={'ok':False,'base':str(BASE),'nativeVersion':manifest['version'],'nativeSHA256':manifest['sha256'],
    'collectionReport':seed.get('report'),'checks':checks,'realFFmpeg':True,'externalModelCalls':False,'platformPublished':False,
    'subtitleMode':processing.get('subtitleMode','local'),'subtitleModel':processing.get('vsrMode'),
    'subtitlePreserveTailSeconds':processing.get('subtitlePreserveTailSeconds',0),'visualReviewed':False,
    'costRows':'Synthetic acceptance cost.'}


def check(name,value):
    if not value:raise AssertionError(name)
    checks.append(name);print('PASS '+name,flush=True)


def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def complete(kind,ids):
    result=s.create_job({'kind':kind,'ids':ids});jid=result['id']
    deadline=time.monotonic()+900;last=0
    while time.monotonic()<deadline:
        job=s.JOBS[jid]
        if job['status'] in ('failed','cancelled','interrupted'):
            raise RuntimeError(kind+': '+job.get('error',job.get('stage','')))
        if job['status']=='completed' and job.get('finished'):return job
        if time.monotonic()-last>5:
            print(json.dumps({'job':jid,'kind':kind,'status':job['status'],'progress':job.get('progress'),'stage':job.get('stage')},ensure_ascii=True),flush=True);last=time.monotonic()
        time.sleep(.2)
    s.control_job(jid,'cancel');raise TimeoutError(kind)


def decode(path):
    result=subprocess.run([s.FFMPEG,'-hide_banner','-v','error','-xerror','-err_detect','explode','-i',str(path),
        '-map','0:v:0','-map','0:a:0','-f','null','NUL'],capture_output=True,timeout=300,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError(result.stderr.decode('utf-8','replace')[:1000])


try:
    inputs=seed['videos'];paths=[row.get('path') for row in inputs]
    check('three_current_full_episodes_are_the_collected_inputs',len(paths)==3 and all(Path(path).is_relative_to(BASE) for path in paths))
    original={path:sha(path) for path in paths}
    check('collected_input_hashes_match',all(original[row['path']]==row['sha256'] for row in inputs))
    ids=seed['projectIds'];projects=[s.get_project(pid) for pid in ids]
    check('collection_projects_and_video_identity_remain_available',set(paths)=={v['path'] for project in projects for v in project['videos']})
    base_config=s.validate_config(copy.deepcopy(s.DEFAULT)|{'output':str(BASE/'本地流程成片'),
        'width':720,'height':1280,'segmentSeconds':40,'gpu':True,'parallel':2,
        'subtitleAuto':True,'subtitleMode':'local','autoText':False,'autoAICover':False,
        'autoCover':True,'autoRecords':True,'autoCost':True,'pipelineHighlight':True,
        'highlightCount':1,'highlightRandom':False,'highlightMin':1,'highlightMax':1,'highlightFixed':1,
        'costRows':[{'name':'本地流程验收示例费用','amount':1000}]}|processing)
    s.STATE['config']=base_config
    for project in projects:project['rights']=True
    s.save()
    outputs=[];pipeline_jobs=[]
    for project in projects:
        config=copy.deepcopy(base_config)
        series_id=next(row['seriesId'] for row in inputs if row['projectId']==project['id'])
        if series_id in project_regions:
            config['subtitleRegions']=project_regions[series_id]
        s.STATE['config']=s.validate_config(config);s.save()
        job=complete('pipeline',[project['id']])
        pipeline_jobs.append({'id':job['id'],'projectId':project['id'],'seconds':round(job['finished']-job['started'],3),
            'stages':job['currentCompletedStages'],'encoding':job.get('encoding',{}),
            'localRepairEngine':job.get('localRepairEngine'),'vsrWorker':job.get('vsrWorker'),
            'subtitleSettings':{key:config[key] for key in ['subtitleMode','vsrMode','subtitleRegion','subtitleRegions','subtitlePreserveTailSeconds','sttnDevice','lamaDevice']}})
        check('project_'+project['id']+'_final_videos_belong_to_current_job',project.get('finalJob')==job['id'])
        if config['subtitleMode']=='vsr':
            check('project_'+project['id']+'_uses_selected_neural_engine',job.get('localRepairEngine')==config['vsrMode'] and bool(job.get('vsrWorker')))
        final=project.get('finalVideoPaths',[])
        check('project_'+project['id']+'_has_saved_final_videos',bool(final) and all(Path(path).is_file() for path in final))
        for path in final:
            metadata=s.probe(path);decode(path)
            check('final_'+Path(path).name+'_fully_decodes_with_audio',metadata['audio'] and metadata['duration']>0 and metadata['width']==720 and metadata['height']==1280)
            outputs.append({'projectId':project['id'],'path':path,'sha256':sha(path),**metadata})
        artifacts=[item for item in project['artifacts'] if item.get('job')==job['id']]
        check('project_'+project['id']+'_cover_record_and_cost_exist',all(any(Path(item['path']).name==name and Path(item['path']).is_file() for item in artifacts) for name in ['制作记录.json','成本报告.docx']))
        cover=next(Path(item['path']) for item in artifacts if item.get('kind')=='封面')
        with Image.open(cover) as image:
            check('project_'+project['id']+'_cover_has_expected_size',image.size==(816,1086))
        cost=next(Path(item['path']) for item in artifacts if Path(item['path']).name=='成本报告.docx')
        with zipfile.ZipFile(cost) as archive:check('project_'+project['id']+'_cost_document_is_valid',archive.testzip() is None and 'word/document.xml' in archive.namelist())
    check('all_local_stages_finish_in_one_job',all(row['stages']==['subtitle','video','highlight','cover','records','cost'] for row in pipeline_jobs))
    report.update(outputs=outputs,pipelineJobs=pipeline_jobs,jobId=pipeline_jobs[-1]['id'],
        jobSeconds=round(sum(row['seconds'] for row in pipeline_jobs),3),encoding=pipeline_jobs[-1]['encoding'])
    package=complete('package',ids);archives=[item for project in projects for item in project['artifacts'] if item.get('job')==package['id'] and item['path'].endswith('.zip')]
    check('each_project_exports_its_local_material_package',len(archives)==len(projects))
    for item in archives:
        with zipfile.ZipFile(item['path']) as archive:check('package_'+Path(item['path']).parent.name+'_passes_crc',archive.testzip() is None)
    check('current_downloaded_originals_remain_unchanged',all(sha(path)==digest for path,digest in original.items()))
    check('no_platform_publication_task_is_created',not s.STATE.get('promotionTasks'))
    report.update(ok=True,packages=archives,originalSHA256=original,projectIds=ids)
finally:
    s.shutdown_jobs()
    target=BASE/'collected-production-report.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/collected-production-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'passed':len(checks),'report':str(target)},ensure_ascii=True),flush=True)
