"""Real filesystem/media regression for configurable output and moved inputs."""
from pathlib import Path
import copy,json,os,shutil,sys,tempfile,threading
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='storage-check-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s
import jianying_projects as j

checks=[];ok=False
def check(label,condition=True):
    assert condition,label
    checks.append(label);print('PASS '+label,flush=True)
def rejects(fn,part):
    try:fn()
    except ValueError as error:return part in str(error)
    return False

def run(command,**kwargs):
    return s.subprocess.check_output(command,stderr=s.subprocess.STDOUT,**kwargs)

try:
    source_root=BASE/'原素材';source_root.mkdir();source=source_root/'第0001集.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=1',
          '-f','lavfi','-i','sine=sample_rate=48000:duration=1','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(source)])
    source_hash=j.sha(source);video=s.video_entries([source])[0]
    p={'id':'fixture','name':'原始剧名','originalName':'原始剧名','intro':'保留已编辑的故事简介。','originalIntro':'原始简介',
       'videos':[video],'source':str(source_root),'cover':'','artifacts':[],'rights':True,'status':'待处理','review':'待准备','notes':'客户备注'}
    s.STATE['projects']=[p];s.JOBS.clear()
    result=s.storage_settings({'output':str(BASE/'指定保存位置'),'jianyingOutput':str(BASE/'独立工程位置')})
    check('selected_output_and_project_folders_are_created_and_persisted',Path(result['config']['output']).is_dir() and Path(result['options']['output']).is_dir() and json.loads((s.DATA/'state.json').read_text('utf-8'))['config']['output']==result['config']['output'])
    check('write_probe_leaves_no_temp_files',not list((BASE/'指定保存位置').glob('.manju-write-*')))
    check('automatic_project_options_preserve_chosen_directory',result['options']['output']==str(BASE/'独立工程位置') and not result['custom'])
    configured=s.STATE['jianyingOptions']['output'];unavailable=BASE/'不再可用的工程位置';unavailable.write_text('preserve','utf-8')
    s.STATE['jianyingOptions']['output']=str(unavailable)
    s.storage_settings({'output':str(BASE/'仅更改去字幕保存位置')})
    check('subtitle_output_change_is_not_blocked_by_unavailable_unrelated_project_folder',s.STATE['config']['output']==str(BASE/'仅更改去字幕保存位置') and s.STATE['jianyingOptions']['output']==str(unavailable) and unavailable.read_text('utf-8')=='preserve')
    s.STATE['jianyingOptions']['output']=configured;s.storage_settings({'output':str(BASE/'指定保存位置')})
    old_cfg=copy.deepcopy(s.STATE['config']);old_opts=copy.deepcopy(s.STATE['jianyingOptions'])
    file_target=BASE/'这不是文件夹.txt';file_target.write_text('keep','utf-8')
    check('file_as_folder_rejected_without_changing_saved_settings',rejects(lambda:s.storage_settings({'output':str(file_target)}),'无法写入') and s.STATE['config']==old_cfg and s.STATE['jianyingOptions']==old_opts and file_target.read_text('utf-8')=='keep')
    with patch.object(s.tempfile,'TemporaryFile',side_effect=PermissionError('fixture denied')):
        check('write_permission_failure_is_visible_and_preserves_settings',rejects(lambda:s.storage_settings({'output':str(BASE/'拒绝写入')}),'无法写入') and s.STATE['config']==old_cfg)
    check('drive_root_is_rejected',rejects(lambda:s.storage_settings({'output':str(BASE.anchor)}),'输出文件夹'))
    with patch.object(s,'save',side_effect=OSError('fixture save failure')):
        try:s.storage_settings({'output':str(BASE/'保存失败'),'jianyingOutput':''})
        except OSError:pass
    check('disk_save_failure_rolls_back_both_settings',s.STATE['config']==old_cfg and s.STATE['jianyingOptions']==old_opts)
    result=s.storage_settings({'output':str(BASE/'指定保存位置'),'jianyingOutput':''})
    check('blank_project_override_uses_output_subfolder',not result['options']['output'] and (BASE/'指定保存位置/剪映工程').is_dir())

    manager=s.evidence_manager()
    from PIL import Image
    screenshot=BASE/'原始截图.png';Image.new('RGB',(64,64),'#6d53bc').save(screenshot);screenshot_hash=j.sha(screenshot)
    imported=manager.import_images(p['id'],{'platform':'jianying','paths':[str(screenshot)],'note':'实际工程来源测试','userConfirmed':True},{'projectId':p['id'],'userConfirmed':True})
    check('new_screenshots_saved_in_selected_folder',Path(imported['items'][0]['path']).is_relative_to(BASE/'指定保存位置/工程图') and j.sha(imported['items'][0]['path'])==screenshot_hash)
    s.storage_settings({'output':str(BASE/'第二保存位置')})
    check('old_screenshots_and_history_remain_accessible',manager.list(p['id'])['items'][0]['path']==imported['items'][0]['path'] and Path(imported['items'][0]['path']).is_file() and j.sha(screenshot)==screenshot_hash)

    moved_root=BASE/'移动后的素材'
    assert source_root.is_relative_to(BASE) and moved_root.is_relative_to(BASE)
    source_root.rename(moved_root)
    check('missing_media_has_actionable_error',rejects(lambda:s.source_snapshot([p['id']]),'重新定位素材'))
    with patch.object(s.licensing,'require'),patch.object(s,'ensure_runner'):
        jid=s.create_job({'kind':'rewrite','ids':[p['id']]})['id']
        check('rewrite_can_be_queued_with_missing_video',s.JOBS[jid]['sourceSnapshot']=={})
        with patch.object(s.ai,'text_generate',return_value={'text':json.dumps({'title':'灵泉新生','synopsis':'家人在艰难岁月里共同守护生活。'},ensure_ascii=False),'model':'fixture','provider':'fixture','seconds':0,'usage':{}}):
            s.worker(jid,[p['id']],'rewrite',s.JOBS[jid]['config'])
        check('rewrite_actually_finishes_and_saves_text_without_video',s.JOBS[jid]['status']=='completed' and p['name']=='灵泉新生' and any(a['kind']=='文案' and Path(a['path']).is_file() for a in p['artifacts']))
        s.JOBS[jid].update(status='failed',sourceSnapshot={'old':'historical snapshot'})
        s.control_job(jid,'resume')
        check('historical_text_job_resume_does_not_require_video',s.JOBS[jid]['status']=='queued')
        s.JOBS[jid]['status']='completed'
    mismatch=BASE/'错误素材';mismatch.mkdir();(mismatch/source.name).write_bytes(b'wrong video')
    prior=copy.deepcopy(p)
    check('wrong_source_folder_rejected_without_partial_record_changes',rejects(lambda:s.relink_project({'id':p['id'],'directory':str(mismatch)}),'大小') and p==prior)
    s.JOBS[jid]['status']='running'
    check('active_project_cannot_be_relinked',rejects(lambda:s.relink_project({'id':p['id'],'directory':str(moved_root)}),'正在处理'))
    s.JOBS[jid]['status']='completed'
    linked=s.relink_project({'id':p['id'],'directory':str(moved_root)})
    check('moved_source_relinked_without_losing_edited_metadata',p['videos'][0]['path']==str(moved_root/source.name) and p['name']==prior['name'] and p['intro']==prior['intro'] and p['notes']==prior['notes'] and p['artifacts']==prior['artifacts'])
    check('relinked_source_is_readable_and_original_bytes_unchanged',s.source_snapshot([p['id']])[p['id']][0]['bytes']==video['bytes'] and j.sha(moved_root/source.name)==source_hash)
    check('historical_job_source_records_not_rewritten',s.JOBS[jid]['sourceSnapshot']=={'old':'historical snapshot'} and linked['paths'][str(source)]==str(moved_root/source.name))

    generated=j.generate(p['videos'][0],{'sourceSHA256':source_hash,'segments':[{'start':0,'end':.5},{'start':.5,'end':1}]},BASE/'原工程',s.FFMPEG,run,threading.Event())
    folder=Path(generated['directory']);generated.update(projectId=p['id'],sourcePath=p['videos'][0]['path'],editorImport={'directory':'old-editor-copy'},editorValidated=True)
    job={'id':'moved-draft','kind':'jianying_project','ids':[p['id']],'status':'completed','created':0,'jianyingResults':[generated],'checkpoints':{}}
    s.JOBS[job['id']]=job;s.checkpoint(job['id'],'fixture:export',[folder/'manju_project.json',folder/'draft_content.json'])
    s.register(p,folder/'draft_content.json','剪映工程',job['id'])
    moved=BASE/'工程新位置'/folder.name;moved.parent.mkdir()
    assert folder.is_relative_to(BASE) and moved.is_relative_to(BASE)
    folder.rename(moved)
    check('missing_draft_has_reconnect_instruction',rejects(lambda:j.check(folder),'重新定位工程'))
    before=copy.deepcopy(generated);manifest=moved/'manju_project.json';raw=manifest.read_bytes();wrong=json.loads(raw);wrong['sourceSHA256']='0'*64;manifest.write_text(json.dumps(wrong),'utf-8')
    check('unrelated_draft_is_rejected_before_mutating_records',rejects(lambda:s.reconnect_editor_result({'jobId':job['id'],'index':0,'directory':str(moved)}),'不匹配') and generated==before)
    manifest.write_bytes(raw)
    attached=s.reconnect_editor_result({'jobId':job['id'],'index':0,'directory':str(moved)})
    check('moved_draft_and_saved_job_paths_are_reconnected',attached['relinked'] and generated['directory']==str(moved) and generated['manifest']==str(manifest) and j.check(moved)['sourceSHA256']==source_hash)
    check('reconnect_updates_registered_exports_and_checkpoints',any(a['path']==str(moved/'draft_content.json') for a in p['artifacts']) and s.cached(job['id'],'fixture:export')==[manifest,moved/'draft_content.json'])
    check('reconnect_requires_new_editor_import_and_does_not_claim_validation','editorImport' not in generated and not generated['editorValidated'] and job['status']=='completed')
    data=json.loads((moved/'draft_content.json').read_text('utf-8'));paths=[x['path'] for group in ('videos','audios') for x in data['materials'][group]]
    check('draft_material_paths_point_to_new_complete_export',paths and all(Path(x).is_file() and Path(x).is_relative_to(moved) for x in paths) and (moved/'draft_content.before-relink.json').is_file())
    check('saved_job_survives_reload_with_new_directory',json.loads((s.DATA/'jobs.json').read_text('utf-8'))[-1]['jianyingResults'][0]['directory']==str(moved))
    ok=True
    print(json.dumps({'ok':True,'checks':len(checks),'base':str(BASE)},ensure_ascii=False))
finally:
    report={'ok':ok,'checks':checks,'base':str(BASE),'providerResponses':'simulated; real filesystem and decoded media'}
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/storage-check-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
