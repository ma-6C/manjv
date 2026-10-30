"""One action: configured editing, import and genuine editor capture per episode."""
from pathlib import Path
import hashlib
import threading
import time

import jianying_ai
import jianying_automation
import jianying_projects
import jianying_materials

_BATCH_LOCK=threading.Lock()
PATH_OPTIONS=('output','executable','draftRoot','aiPython','aiModelRoot','materialLibrary')


def automatic_options(preferences,config):
    """A product preset, independent of historical manual editing switches."""
    opts=jianying_projects.options({key:preferences.get(key,'auto' if key=='cudaLibraries' else '') for key in PATH_OPTIONS+('cudaLibraries',)})
    opts.update(mouseOpen=True,registerIndex=True,timelineMode='detailed',splitScenes=True,
                shotSeconds=10,
                editProfile='cinema',cameraMotion=True,colorAdjust=True,cutMaterials=True,
                speedPattern='original',transition='dissolve',filterStyle='cinema',filterIntensity=25,
                audioMode='separate',captionMode='auto',aiDevice='auto',aiFailure='stop',addBgm=False,duckMusic=True)
    base=Path(__file__).resolve().parent
    if opts['executable'] and not jianying_projects._verified_editor(opts['executable']):opts['executable']=''
    for key in ('draftRoot','aiModelRoot','materialLibrary'):
        if opts[key] and not Path(opts[key]).is_dir():opts[key]=''
    if not opts['materialLibrary']:
        candidates=[base/'engines/jianying-draft/materials']
        if config.get('vsrRoot'):candidates.append(Path(config['vsrRoot'])/'models/jianying/materials')
        opts['materialLibrary']=next((str(p.resolve()) for p in candidates if p.is_dir()),'')
    opts['materialLibrary']=jianying_materials.resolve_material_dir(opts['materialLibrary'])
    opts=jianying_ai.runtime_options(opts,config)
    return jianying_projects.options(opts)


def _image_valid(item):
    if not isinstance(item,dict) or item.get('source')!='window_capture':return False
    evidence=item.get('officialEvidence') or {}
    metadata=evidence.get('metadata',{})
    if evidence.get('appVerified') is not True or not (metadata.get('projectTitleVerified') is True or metadata.get('projectIdentityVerified') is True):return False
    path=Path(item.get('path',''))
    return path.is_file() and jianying_projects.sha(path)==evidence.get('sha256')


def _generate(s,job,video,index,opts,cfg,key,old):
    jid=job['id'];total=len(job['options']['jianyingVideos'])
    if old and _complete_result(old,video,opts) and s.cached(jid,key) is not None:
        try:jianying_projects.check(old['directory']);return old
        except (OSError,ValueError):pass
    video.setdefault('jianyingCutSeed',hashlib.sha256((jid+'\0'+video['path']).encode()).hexdigest())
    s.persist_jobs()
    progress={'phase':None,'last':0,'tid':None}
    labels={'copy':'复制素材','audio':'准备音轨','draft':'保存草稿','decode':'识别镜头','hash':'核对素材',
            'cache':'读取已有分析','assets':'安排声音素材','timeline':'建立剪辑轨道','captions':'建立字幕',
            'fragments':'生成独立镜头','separate':'分离人声与背景声','asr':'识别字幕','cpu_fallback':'正在改用 CPU','cuda_fallback':'正在切换 GPU 运行库','materials':'按时长识别剪映声音素材'}
    def notify(phase,value,length):
        if job['cancel'].is_set():raise InterruptedError('工程图已暂停')
        if phase=='ai_log':
            _ai_log(s,job,video,value)
            return
        if phase=='cut_plan':
            job['jianyingEpisodes'][str(index)]['cutPlan']=value;s.persist_jobs()
            s.log(video['name']+' · 切片计划：'+str(value['count'])+' 段，实际 '+str(value['actualMinSeconds'])+'～'+str(value['actualMaxSeconds'])+
                  ' 秒；'+('随机时长，尽量贴近场景边界；重试沿用相同切点' if value['mode']=='random' else '保留场景分段')+
                  ('；原视频不足2秒，保留完整短片' if value['shortSource'] else ''),job=jid)
            return
        if phase=='backend':return
        now=time.monotonic()
        if progress['phase']==phase and now-progress['last']<.5 and value!=length:return
        changed=progress['phase']!=phase
        if changed:
            if progress['tid']:s.telemetry.finish(job,progress['tid'])
            unit='bytes' if phase in ('copy','hash','assets') else 'seconds' if phase=='asr' else 'clips' if phase in ('timeline','fragments') else 'files' if phase=='materials' else 'frames'
            progress['tid']=s.telemetry.begin(job,'工程图 · '+labels.get(phase,phase),video['name'],length or 0,unit)
        progress.update(phase=phase,last=now)
        if isinstance(value,(int,float)) and isinstance(length,(int,float)):s.telemetry.advance(job,progress['tid'],value,length)
        entry=job['jianyingEpisodes'][str(index)]
        with s.LOCK:entry.update(step=labels.get(phase,'建立工程'));s.persist_jobs()
        if changed:s.stage(jid,f'{index+1}/{total} · {video["name"]} · '+entry['step'],(index+.75)/total*90)
    run=lambda args,observe=None,timeout=None:s.run_process(args,jid,observe=observe,timeout=timeout)
    try:
        jianying_materials.prepare(video,opts,job,job['cancel'],notify)
        s.persist_jobs()
        if opts['splitScenes']:
            analysis,_,_=s.track_sheets.analyze(video,s.track_sheets.options(s.STATE.get('trackSheetOptions',{})),s.DATA/'track-sheet-cache',s.FFMPEG,run,job['cancel'],notify)
        else:analysis={'sourceSHA256':s.track_sheets.source_hash(Path(video['path']),job['cancel'],notify),'segments':[{'start':0,'end':video['duration']}]}
        result=jianying_projects.generate(video,analysis,Path(opts['output'] or str(Path(cfg['output'])/'剪映工程')),
                    s.FFMPEG,run,job['cancel'],notify,opts=jianying_ai.runtime_options(opts,cfg))
        result.update(projectId=video['projectId'],sourcePath=video['path'])
        s.log(video['name']+' · 草稿和素材校验完成：独立视频 '+str(result['library']['videos'])+' 个，音频 '+str(result['library']['audios'])+
              ' 个，可编辑字幕 '+str(result['timeline'].get('captionSegments',0))+' 条\n工程目录：'+result['directory'],job=jid)
        for warning in result.get('warnings',[]):s.log(warning,level='warning',job=jid)
        with s.LOCK:
            project=s.get_project(video['projectId'])
            s.register(project,Path(result['path']),'剪映真实工程',jid);s.register(project,Path(result['manifest']),'剪映工程清单',jid)
            rows=job['jianyingResults'];rows[:]=[r for r in rows if r['sourcePath']!=video['path']];rows.append(result)
            s.checkpoint(jid,key,[p for p in Path(result['directory']).rglob('*') if p.is_file()]);s.persist_jobs()
        return result
    finally:
        if progress['tid']:s.telemetry.finish(job,progress['tid'])


def run(s,cfg,jid):
    job=s.JOBS[jid];opts=jianying_projects.options(job['options'].get('jianying',{}));videos=job['options']['jianyingVideos']
    auto=job['options'].get('autoDiagram',False);rows=job.setdefault('jianyingResults',[]);failures=[]
    if job['options'].get('automatic'):
        opts['aiFailure']='stop';opts=jianying_ai.runtime_options(opts,cfg)
        job['options']['jianying']=opts;s.persist_jobs()
    entries=job.setdefault('jianyingEpisodes',{});event=job['cancel']
    if auto and not _BATCH_LOCK.acquire(blocking=False):raise ValueError('已有工程图批次正在使用剪映，请等当前批次结束后继续')
    try:
        for index,video in enumerate(videos):
            entry=entries.setdefault(str(index),{'sourcePath':video['path'],'name':video['name'],
                'projectId':video['projectId'],'projectName':s.get_project(video['projectId'])['name'],'status':'queued','step':'等待处理'})
            old=next((r for r in rows if r.get('sourcePath')==video['path']),None)
            if auto and old and _complete_result(old,video,opts) and _image_valid(old.get('diagram')):
                entry.update(status='completed',step='工程图已保存',error='');continue
            if auto and old and old.get('diagram'):
                with s.LOCK:old.pop('diagram',None);s.persist_jobs()
            if event.is_set():raise InterruptedError('工程图已暂停，已完成图片保留')
            stat=Path(video['path']).stat()
            if video['inputStat']!={'bytes':stat.st_size,'mtime':stat.st_mtime_ns}:raise ValueError(video['name']+' 源素材已变化，请重新选择')
            owner=job.get('jianyingDesktopOwner')
            if auto and owner and (not old or owner['directory']!=old.get('editorImport',{}).get('directory')):
                entry.update(status='running',step='正在切换到下一集')
                s.persist_jobs()
                try:jianying_automation.close_completed_project(owner,event)
                except InterruptedError:
                    entry.update(status='paused',step='已暂停，等待继续');s.persist_jobs();raise
                except Exception as exc:
                    entry.update(status='waiting_action',error=str(exc));s.persist_jobs();raise
                with s.LOCK:job.pop('jianyingDesktopOwner',None);s.persist_jobs()
            entry.update(status='running',step='自动建立工程',error='');s.persist_jobs()
            key='jianying:'+hashlib.sha256(video['path'].encode()).hexdigest()[:20]
            result=old;capture_started=False
            try:
                result=_generate(s,job,video,index,opts,cfg,key,old)
                if auto:
                    capture_started=True
                    def phase(message):
                        if event.is_set():raise InterruptedError('工程图已暂停')
                        with s.LOCK:entry.update(step=message);s.persist_jobs()
                        s.stage(jid,f'{index+1}/{len(videos)} · {video["name"]} · '+message,index/len(videos)*90)
                    phase('正在导入剪映工程')
                    imported=result.get('editorImport')
                    if not imported:
                        imported=jianying_projects.install_to_editor(result['directory'],opts,operation_id=jid+'-'+str(index))
                        with s.LOCK:result['editorImport']=imported;s.persist_jobs()
                    body={'projectId':video['projectId'],'jobId':jid,'index':rows.index(result)}
                    association=s.evidence_association(body)
                    captured=s.evidence_manager().auto_capture(video['projectId'],body,association,imported,opts,
                        wait=True,cancel_event=event,progress=phase)
                    if event.is_set():raise InterruptedError('工程图已暂停')
                    if captured['status']!='completed':
                        entry.update(status='waiting_action' if captured['status']=='waiting_action' else 'failed',error=captured['message'])
                        raise ValueError(captured['message'])
                    with s.LOCK:
                        result['diagram']=captured['item'];job['jianyingDesktopOwner']=imported
                        s.checkpoint(jid,key+':diagram',[Path(captured['item']['path'])]);s.persist_jobs()
                    s.log(video['name']+' · 官方工程图已保存\n图片：'+captured['item']['path']+
                          '\nSHA256：'+captured['item']['officialEvidence']['sha256'],job=jid)
                entry.update(status='completed',step='工程图已保存' if auto else '草稿已生成',error='');s.persist_jobs()
            except InterruptedError:
                entry.update(status='paused',step='已暂停，等待继续');s.persist_jobs();raise
            except Exception as exc:
                exc.video=video['name'];failures.append(exc)
                entry.update(status='waiting_action' if entry.get('status')=='waiting_action' else 'failed',error=str(exc)[:2000]);s.persist_jobs()
                # An editor gate cannot be resolved by blindly sending the next
                # project's mouse actions. Keep all completed checkpoints.
                if entry['status']=='waiting_action' or capture_started:raise
                s.log(video['name']+' · '+entry['step']+'失败：'+str(exc),level='error',job=jid)
            s.telemetry.batch(job,'jianying_projects','自动工程图' if auto else '剪映工程',len(videos),index+1)
        failed=[v for v in entries.values() if v['status']!='completed']
        job['result']={'completed':sum(v['status']=='completed' for v in entries.values()),'failed':len(failed),
            'degraded':sum(bool(r.get('timeline',{}).get('degraded')) for r in rows),
            'files':[r['diagram']['path'] for r in rows if _image_valid(r.get('diagram'))] if auto else [r['path'] for r in rows],
            'editorValidated':False}
        if failed:
            message=f'本批已完成 {len(videos)-len(failed)} / {len(videos)} 集；失败 {len(failed)} 集。'
            if failures:
                cause=failures[-1]
                error=jianying_ai.AIWorkerError(message+'\n'+str(cause),getattr(cause,'details',str(cause)))
                error.video=getattr(cause,'video','');error.stage=getattr(cause,'stage','建立工程');raise error from cause
            raise ValueError(message+'可重试未完成部分')
        if 'jianying_project' not in job['completedStages']:job['completedStages'].append('jianying_project')
    finally:
        if auto:_BATCH_LOCK.release()


def _complete_result(result,video,opts):
    if result.get('library',{}).get('version')!=1:return False
    try:jianying_projects.jianying_timeline.validate_complete(video,opts,result.get('timeline',{}))
    except ValueError:return False
    return True


def _ai_log(s,job,video,event):
    label={'separate':'人声分离','asr':'字幕识别'}.get(event['action'],event['action'])
    providers={'torch':'PyTorch 自带库','nvidia':'NVIDIA 独立包','cpu':'CPU'}
    device='GPU' if event['device']=='cuda' else 'CPU'
    prefix=' · '.join(x for x in (video.get('projectName',''),video['name'],label,'第 '+str(event['attempt'])+' 次') if x)
    info={'video':video['name'],'stage':label,**event}
    if event['event']=='started':
        s.log(prefix+'：开始使用 '+device+' / '+providers.get(event['provider'],event['provider']),job=job['id'])
    elif event['event']=='completed':
        libraries=event.get('libraries',{});actual=providers.get(libraries.get('provider'),event['provider'])
        versions='；'.join(k+' '+v for k,v in libraries.get('versions',{}).items())
        paths='；'.join(k+'='+v for k,v in libraries.get('loaded',{}).items())
        result='输出 '+str(event['frames'])+' 个音频采样帧' if event.get('frames') is not None else '识别 '+str(event.get('captions',0))+' 条字幕'
        s.log(prefix+'：完成，实际使用 '+device+' / '+actual+'，耗时 '+str(event['elapsedSeconds'])+' 秒；'+result+
              ('\n版本：'+versions if versions else '')+('\n实际 DLL：'+paths if paths else ''),job=job['id'])
    else:
        error=jianying_ai.AIWorkerError(event['error'],event.get('traceback') or event['error']);error.video=video['name'];error.stage=label
        diagnostic=s.telemetry.failure(job,error,redact=s.diagnostic_text,trace=event.get('traceback',''))
        diagnostic['stage']=label
        diagnostic['project']=video.get('projectName','')
        retry=event.get('retry')
        if retry:diagnostic['nextStep']='本次尝试失败，软件正自动改用 '+('GPU / ' if retry['device']=='cuda' else '')+providers[retry['provider']]+'。'+diagnostic['nextStep']
        info.update(code=diagnostic['code'],nextStep=diagnostic['nextStep'])
        s.log(prefix+'：'+device+' / '+providers[event['provider']]+' 失败\n'+event['error'],
              level='warning' if retry else 'error',job=job['id'],diagnostic=diagnostic)
    with s.LOCK:
        rows=job.setdefault('jianyingAI',[]);rows.append(info);del rows[:-1000];s.persist_jobs()
