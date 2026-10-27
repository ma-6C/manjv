"""Connect saved flow stages to the existing real jobs and publishing workspace.

This adapter owns no substitute renderers or synthetic editor evidence. Every
completed stage references an existing job, registered artifact, or saved task.
"""
from __future__ import annotations
import copy
from pathlib import Path
import threading
import time
import traceback
import task_progress as telemetry


class Adapter:
    def __init__(self, service):
        self.s = service
        self.stop = threading.Event()
        self.threads = set()
        self.events = {}
        self.last_poll = {}
        with service.LOCK:
            tasks = service.STATE.setdefault('studioFlowTasks', [])
            for task in tasks:
                if task['status'] in ('queued', 'running'):
                    task.update(status='interrupted', message='上次交接中断，恢复后核对已完成项')

    def prepare(self, body):
        s = self.s
        ids = body.get('projectIds', body.get('ids', []))
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise ValueError('请先选择剧目和本地视频')
        with s.LOCK:
            config = s.validate_config(copy.deepcopy(s.STATE['config']))
            paths = body.get('sourceVideoPaths')
            if paths is None:
                paths = {pid: [v['path'] for v in s.get_project(pid)['videos']] for pid in ids}
            options = {'withJianying': True, 'withEvidence': True, 'withExport': True,
                       'withPublish': False, 'reviewRequired': False, 'accountId': ''}
            supplied = body.get('options', {})
            if not isinstance(supplied, dict) or set(supplied) - set(options):
                raise ValueError('流程选项无效')
            options.update(supplied)
            if not isinstance(options['accountId'], str):
                raise ValueError('请选择有效的视频号账号')
            if options['withPublish']:
                s.publish_workspace()._account(options['accountId'])
            plan = s.job_preflight({'kind': 'pipeline', 'ids': ids, 'sourceVideoPaths': paths}, config=config)
            if not plan['ok']:
                raise ValueError('；'.join(plan['errors']))
            if any(j['status'] in ('queued', 'running', 'pausing', 'paused', 'interrupted')
                   and set(ids).intersection(j['ids']) and j['kind'] in ('pipeline', 'transcode', 'subtitle', 'highlight')
                   for j in s.JOBS.values()):
                raise ValueError('所选剧目已有未结束的制作任务，请先完成或停止原任务')
            return {'projectIds': ids, 'sourceVideoPaths': paths, 'config': config, 'options': options,
                    'sourceSnapshot': s.source_snapshot(ids, paths),
                    'projectNames': {pid: s.get_project(pid)['name'] for pid in ids},
                    'jianyingOptions': copy.deepcopy(s.STATE.get('jianyingOptions', {})),
                    'selectionCount': plan['count'], 'productionPlan': plan['workflowPlan']}

    @staticmethod
    def _stage(flow, key):
        return next(x for x in flow['stages'] if x['key'] == key)

    def _job_ids(self, flow):
        ref = self._stage(flow, 'jianying').get('ref', {})
        return ref.get('ids', []) or ([ref['id']] if ref.get('id') else [])

    def _outputs(self, flow):
        result = self._stage(flow, 'production').get('result', {})
        outputs = result.get('videos', {})
        for pid in flow['projectIds']:
            p = self.s.get_project(pid)
            if p.get('finalJob') != result.get('jobId') or p.get('finalVideoPaths') != [v['path'] for v in outputs.get(pid, [])]:
                raise ValueError('当前成品已被其他任务替换，请核对原流程成品，不能自动使用另一版本')
            for v in outputs.get(pid, []):
                st = Path(v['path']).stat()
                if st.st_size != v['bytes'] or st.st_mtime_ns != v['mtime']:
                    raise ValueError('流程成品发生变化，请核对后重新开始')
        return outputs

    def _jobs(self, ids, *, production=False, flow=None):
        s = self.s
        jobs = [s.JOBS.get(jid) for jid in ids]
        if not jobs or any(j is None for j in jobs):
            return dict(status='failed', message='流程对应的任务记录已丢失，请核对本机数据')
        for j in jobs:
            if j['status'] in ('failed', 'cancelled'):
                return dict(status='failed', message=j.get('error') or j.get('stage') or '任务未完成')
            if j['status'] in ('interrupted', 'paused', 'pausing'):
                return dict(status='waiting_action', reason='interrupted', message='原制作任务已暂停，恢复后从已完成检查点接着处理')
        if all(j['status'] == 'completed' for j in jobs):
            if production:
                j = jobs[0]; outputs = {}
                for pid in flow['projectIds']:
                    p = s.get_project(pid)
                    if p.get('finalJob') != j['id']:
                        raise ValueError('制作完成记录与当前成品不一致')
                    outputs[pid] = []
                    for v in s.final_videos(p):
                        st = Path(v['path']).stat()
                        outputs[pid].append({'path': v['path'], 'bytes': st.st_size, 'mtime': st.st_mtime_ns})
                    if not outputs[pid]:raise ValueError('制作任务没有可交接的成品')
                return dict(status='completed', result={'jobId': j['id'], 'videos': outputs}, message='所选视频制作完成，正在交接成品')
            return dict(status='completed', result={'jobIds': ids}, message='剪映可编辑工程已生成，正在导入草稿目录')
        return dict(status='running', progress=sum(j.get('progress', 0) for j in jobs)/len(jobs),
                    message=next((j.get('stage', '正在制作') for j in jobs if j['status'] != 'completed'), '正在制作'))

    def _task(self, operation, work):
        s = self.s
        with s.LOCK:
            task = next((t for t in s.STATE['studioFlowTasks'] if t['id'] == operation), None)
            if task and task['status'] != 'interrupted':return self._task_result(task)
            if task is None:
                task = {'id': operation, 'createdAt': time.time(), 'result': {}}
                s.STATE['studioFlowTasks'].append(task)
            task.update(status='running', reason='', message='正在交接到下一步')
            task.pop('finishedAt', None)
            s.save()
        def run():
            try:
                value = work()
                with s.LOCK:
                    task.update(value, finishedAt=time.time());s.save()
            except InterruptedError as e:
                with s.LOCK:
                    task.update(status='interrupted', message=str(e), finishedAt=time.time());s.save()
            except Exception as e:
                with s.LOCK:
                    redact=getattr(s,'diagnostic_text',s.ai.redact)
                    diagnostic=telemetry.failure({'stage':'交接到剪映'},e,redact=redact,trace=traceback.format_exc())
                    task.update(status='failed', message=diagnostic['reason'],result={'failure':diagnostic},finishedAt=time.time());s.save()
                    if callable(getattr(s,'log',None)):s.log(diagnostic['reason'],level='error',job=operation,diagnostic=diagnostic)
            finally:
                with s.LOCK:self.threads.discard(threading.current_thread())
        thread = threading.Thread(target=run, name='flow-handoff', daemon=True)
        with s.LOCK:self.threads.add(thread)
        thread.start()
        return dict(status='running', ref={'kind': 'flow_task', 'id': operation}, message='正在交接到下一步')

    @staticmethod
    def _task_result(task):
        result={k: copy.deepcopy(task[k]) for k in ('status','message','reason','result','progress') if k in task} | {'ref': {'kind': 'flow_task', 'id': task['id']}}
        if result['status']=='interrupted':result.update(status='waiting_action',reason='interrupted')
        return result

    def _imports(self, flow):
        from jianying_projects import install_to_editor
        s = self.s; rows = []
        for jid in self._job_ids(flow):
            for index, row in enumerate(s.JOBS[jid].get('jianyingResults', [])):
                if self.stop.is_set():raise InterruptedError('流程正在关闭，已完成的工程保留')
                self._check_active(flow)
                imported = row.get('editorImport')
                if not imported:
                    imported = install_to_editor(row['directory'], flow['jianyingOptions'], operation_id=flow['id']+'-'+jid+'-'+str(index))
                    with s.LOCK:row['editorImport'] = imported;s.save()
                rows.append({'jobId': jid, 'index': index, 'projectId': row['projectId'], **imported})
        return rows

    def _check_active(self,flow):
        actual=next((f for f in self.s.STATE.get('studioFlows',{}).get('flows',[]) if f['id']==flow['id']),None)
        if actual and actual['status'] in ('paused','cancelled'):raise InterruptedError('流程已暂停或停止，已完成的工程保留')

    def _editor(self, flow):
        import jianying_automation
        rows = self._imports(flow)
        first = rows[0] if rows else None
        if not first:raise ValueError('没有已生成的剪映工程')
        self._check_active(flow)
        event=self.events.setdefault(flow['id'],threading.Event())
        opened = jianying_automation.open_registered_project(first, flow['jianyingOptions'], event)
        if event.is_set() or self.stop.is_set():raise InterruptedError('剪映交接已暂停，已导入的工程保留')
        # A copied draft must not advance past the editor handoff until the
        # exact project and its real timeline have actually been observed.
        verified = (opened.get('status') == 'completed'
                    and all(opened.get(key) is True for key in
                            ('projectOpened', 'timelineVerified', 'projectTitleVerified')))
        return dict(status='completed' if verified else 'waiting_action',
                    reason='' if verified else opened.get('reason') or 'editor_project',
                    result={'imports': rows, 'editor': opened, 'resumePending': False},
                    message=('已核对剪映中的本次工程；' if verified else '工程已导入草稿库，等待打开核验；')
                    +opened.get('message', opened.get('note', '请在剪映打开「'+first['name']+'」后重新检测并继续')))

    def _evidence(self, flow):
        self._outputs(flow)
        expected = set(self._job_ids(flow)); missing = []; found = []
        from publish_materials import _official_proof_images
        for pid in flow['projectIds']:
            p = self.s.get_project(pid); matches = []
            for a in p.get('artifacts', []):
                e = a.get('officialEvidence', {})
                if e.get('association', {}).get('jobId') in expected and _official_proof_images({'artifacts':[a]},None,[],[]):matches.append(a['path'])
            if matches:found.extend(matches)
            else:missing.append(pid)
        if missing:
            names = '、'.join(flow['projectNames'][p] for p in missing)
            return dict(status='waiting_action', reason='evidence', route='tracks',
                        message='请在剪映打开本次工程并采集真实窗口截图：'+names,
                        result={'missingProjectIds': missing, 'proofImages': found})
        return dict(status='completed', message='本次工程的真实截图已核对，继续检查发布资料', result={'proofImages': found, 'missingProjectIds': []})

    def _materials(self, flow):
        self._outputs(flow)
        plans = [self.s.publish_workspace().inspect(pid) for pid in flow['projectIds']]
        missing = [{'projectId': p['projectId'], 'errors': p['errors']} for p in plans if not p['ready']]
        return dict(status='waiting_action' if missing else 'completed', reason='materials' if missing else '',
                    message='；'.join(p['title']+'：'+'；'.join(p['errors'][:3]) for p in plans if not p['ready']) if missing else '发布资料检查完成',
                    result={'missing': missing, 'fingerprints': {p['projectId']: p['fingerprint'] for p in plans}})

    def _material_version(self,flow,accept=False):
        """Recheck changed forms before touching a new packet or platform form."""
        plans=[self.s.publish_workspace().inspect(pid) for pid in flow['projectIds']]
        fingerprints={p['projectId']:p['fingerprint'] for p in plans}
        old=self._stage(flow,'materials')['result']
        if any(not p['ready'] for p in plans):
            missing=[{'projectId':p['projectId'],'errors':p['errors']} for p in plans if not p['ready']]
            return dict(status='waiting_action',reason='materials',route='publish',message='发布资料有缺项，请补齐后继续：'+'；'.join(e for p in plans for e in p['errors'][:2]),result={'projectId':missing[0]['projectId'],'missing':missing})
        if fingerprints!=old.get('fingerprints'):
            if not accept:
                changed=[pid for pid,fp in fingerprints.items() if fp!=(old.get('fingerprints') or {}).get(pid)]
                return dict(status='waiting_action',reason='materials',route='publish',message='发布资料在检查后发生变化，请核对新版本，再点检查并继续。已完成的视频不重做。',result={'projectId':changed[0] if changed else flow['projectIds'][0],'changedProjectIds':changed})
            update={'fingerprints':fingerprints,'revision':int(old.get('revision',0))+1}
            old.update(update)
            with self.s.LOCK:
                actual=next((f for f in self.s.STATE.get('studioFlows',{}).get('flows',[]) if f['id']==flow['id']),None)
                if actual:self._stage(actual,'materials')['result'].update(update);self.s.save()
        return None

    def _export_tasks(self,flow,operation,retry=False):
        revision=self._stage(flow,'materials')['result'].get('revision',0)
        suffix=':r'+str(revision) if revision else ''
        public=self.s.publish_workspace().public()['tasks'];ids=[]
        for pid in flow['projectIds']:
            tag=operation+':'+pid+suffix
            previous=next((t for t in public if t.get('operationId')==tag),None)
            retry_task=bool(retry and previous and previous['status'] in ('failed','interrupted'))
            ids.append(self.s.publish_workspace().export(pid,operation_id=tag,retry=retry_task)['taskId'])
        return ids

    def _publish_tasks(self, ids):
        if not ids:return dict(status='failed', reason='export_missing', message='尚未创建发布资料导出任务，请检查资料后继续')
        tasks = self.s.publish_workspace().public()['tasks']; selected = [next((t for t in tasks if t['id'] == tid), None) for tid in ids]
        if any(t is None for t in selected):return dict(status='failed', message='发布准备任务记录缺失')
        if any(t['status'] in ('failed','interrupted') for t in selected):
            return dict(status='failed', message=next(t.get('error') or t['stage'] for t in selected if t['status'] in ('failed','interrupted')))
        if all(t['status'] == 'completed' for t in selected):return dict(status='completed', result={'tasks': selected}, message='发布资料包已导出')
        return dict(status='running', message='正在复制校验发布资料', progress=sum(t.get('percent',0) for t in selected)/max(1,len(selected)))

    def start(self, flow, stage, operation):
        s = self.s; key = stage['key']
        if key == 'production':
            if flow['sourceSnapshot'] != s.source_snapshot(flow['projectIds'], flow['sourceVideoPaths']):
                raise ValueError('开始后源素材发生变化，请重新核对选集')
            job = s.create_job({'kind': 'pipeline', 'ids': flow['projectIds'], 'sourceVideoPaths': flow['sourceVideoPaths']},
                               config=flow['config'], flow_id=flow['id'], operation_id=operation)
            return dict(status='running', ref={'kind':'job','id':job['id']}, message='正在连续制作所选视频')
        if key == 'review':return dict(status='waiting_action', reason='review', message='请检查成片；确认后继续生成工程和发布资料')
        if key == 'jianying':
            outputs = self._outputs(flow); all_videos = [(pid, v['path']) for pid, vs in outputs.items() for v in vs]; ids = []
            for begin in range(0, len(all_videos), 30):
                chunk = all_videos[begin:begin+30]; paths = {}
                for pid, path in chunk:paths.setdefault(pid, []).append(path)
                job = s.create_job({'kind':'jianying_project','ids':list(paths),'sourceKind':'final','videoPaths':paths,'jianying':flow['jianyingOptions']},
                                   config=flow['config'], flow_id=flow['id'], operation_id=operation+':'+str(begin//30))
                ids.append(job['id'])
            return dict(status='running', ref={'kind':'jobs','ids':ids}, message='自动生成本次成品的剪映工程')
        if key == 'editor_import':return self._task(operation, lambda:self._editor(flow))
        if key == 'evidence':return self._evidence(flow)
        if key == 'materials':return self._materials(flow)
        if key == 'export':
            self._outputs(flow)
            changed=self._material_version(flow)
            if changed:return changed
            ids = self._export_tasks(flow,operation)
            return dict(status='running', ref={'kind':'publish_tasks','ids':ids}, message='自动导出已核对的发布资料包')
        if key == 'publish':return self._browser(flow, stage, operation, first=True)
        raise ValueError('流程步骤无效')

    def _browser(self, flow, stage, operation, first=False, *, retry_open=False):
        s = self.s; self._outputs(flow); aid = flow['options']['accountId']; pid = flow['projectIds'][0]
        changed=self._material_version(flow)
        if changed:return changed
        revision=self._stage(flow,'materials')['result'].get('revision',0)
        if revision and flow['options'].get('withExport'):
            exports=self._export_tasks(flow,flow['id']+':export')
            result=self._publish_tasks(exports)
            if result['status']!='completed':return result
        # Each drama is a separate official form. A human submission record is
        # required before moving to another drama; never press final Submit.
        done = []
        records = s.publish_workspace().public()['records']
        fingerprints = self._stage(flow, 'materials').get('result', {}).get('fingerprints', {})
        for candidate in flow['projectIds']:
            if any(r['projectId']==candidate and r['accountId']==aid and r.get('fingerprint')==fingerprints.get(candidate)
                   and r['status'] in ('submitted','approved') for r in records):done.append(candidate)
        remaining = [x for x in flow['projectIds'] if x not in done]
        if not remaining:return dict(status='completed', message='已保存本人核对的提交记录；平台审核结果以官方后台为准', result={'manuallyRecorded':done,'platformVerified':False})
        pid = remaining[0]; workspace = s.publish_workspace(); public = workspace.public()
        tag = operation+':'+pid+(':r'+str(revision) if revision else '')
        def find(suffix):return next((t for t in reversed(public['tasks']) if t.get('operationId')==tag+suffix),None)
        def pending(task,message):return dict(status='running',ref={'kind':'publish_task','id':task['id']},message=message,result={'projectId':pid,'submitted':False})
        previous=find(':open')
        if previous is None:
            task=workspace.browser(aid,'open',pid,operation_id=tag+':open')
            return dict(status='running',ref={'kind':'publish_task','id':task['taskId']},message='自动打开账号的官方后台',result={'projectId':pid,'submitted':False})
        if previous['status'] in ('queued','running'):return pending(previous,'正在打开并检测官方发布页面')
        if previous['status'] in ('failed','interrupted'):
            if retry_open:
                task=workspace.browser(aid,'open',pid,operation_id=tag+':open',retry=True)
                return dict(status='running',ref={'kind':'publish_task','id':task['taskId']},message='重新打开中断的官方后台，随后核对登录与提审页面',result={'projectId':pid,'submitted':False})
            return dict(status='failed',message=previous.get('error') or '官方后台打开中断，请核对后恢复流程')
        assisted=find(':assist')
        if assisted:
            if assisted['status'] in ('queued','running'):return pending(assisted,'正在辅助填写本次已核对的发布资料')
            if assisted['status'] in ('failed','interrupted'):
                return dict(status='waiting_action',reason='confirmation',message='辅助填写中断，请在官方网页核对已有内容，避免重复上传',result={'projectId':pid,'submitted':False})
            result=assisted.get('result') or {}
            if result.get('state') in ('needs_login','needs_navigation'):
                verify=find(':assist:verify')
                if stage.get('result',{}).get('retryNoFill'):
                    if verify and verify['status'] in ('queued','running'):return pending(verify,'正在重新核对登录和提审页面')
                    if verify and verify['status']=='completed':
                        detected=verify.get('result') or {}
                        if detected.get('loginState')=='authenticated' and detected.get('formRecognized') is True and not detected.get('blockers'):
                            retry=workspace.browser(aid,'assist',pid,operation_id=tag+':assist',retry=True)
                            return dict(status='running',ref={'kind':'publish_task','id':retry['taskId']},message='已核对页面，继续辅助填写',result={'retryNoFill':False,'projectId':pid,'submitted':False})
                    if not verify or time.time()-verify.get('finishedAt',verify['createdAt'])>5:
                        checked=workspace.browser(aid,'check',pid,operation_id=tag+':assist:verify',retry=True)
                        return dict(status='running',ref={'kind':'publish_task','id':checked['taskId']},message='重新检测登录与提审页面，原视频和工程保持不变',result={'retryNoFill':True,'projectId':pid})
                    return dict(status='waiting_action',reason='login' if result['state']=='needs_login' else 'navigation',message='请在官方网页恢复登录或进入提审表单，软件会继续检测',result={'projectId':pid})
                # Nothing was filled in these outcomes. Recheck/read only;
                # retry requires an explicit Continue from the operator.
                login=result['state']=='needs_login'
                return dict(status='waiting_action',reason='confirmation',message='填写前登录失效，请本人登录后点检查并继续' if login else '提审页面已变化，请回到正确表单后点检查并继续',result={'projectId':pid,'browser':result,'submitted':False})
            return dict(status='waiting_action',reason='submission',message='请在官方网页核对资料、完成提交，再记录提交结果；软件不会自动提交',result={'projectId':pid,'browser':result,'submitted':False})
        checked=find(':check')
        if checked and checked.get('finishedAt',0)<previous.get('finishedAt',0):checked=None
        result=(checked or previous).get('result') or {}
        if checked and checked['status'] in ('queued','running'):return pending(checked,'正在检测账号登录与提审页面')
        if checked and result.get('browserOpen') is False:
            task=workspace.browser(aid,'open',pid,operation_id=tag+':open',retry=True)
            return dict(status='running',ref={'kind':'publish_task','id':task['taskId']},message='重新打开已关闭的官方后台，继续核对原任务',result={'projectId':pid,'submitted':False})
        if result.get('loginState')=='authenticated' and result.get('formRecognized') is True and not result.get('blockers'):
            task=workspace.browser(aid,'assist',pid,operation_id=tag+':assist')
            return dict(status='running',ref={'kind':'publish_task','id':task['taskId']},message='自动辅助填写已识别的官方提审表单',result={'projectId':pid,'submitted':False})
        # Checks are read-only. Reuse one saved check slot instead of creating
        # an unbounded task history or redispatching uploads on every poll.
        if not checked or time.time()-checked.get('finishedAt',checked['createdAt'])>5:
            workspace.browser(aid,'check',pid,operation_id=tag+':check',retry=True)
        login=result.get('loginState')=='login_required'
        return dict(status='waiting_action',reason='login' if login else 'navigation',
                    message='请本人在已打开的官方网页扫码登录，软件会自动检测后继续' if login else '请在官方后台进入创建剧集的提审表单，软件识别后会继续辅助填写',
                    result={'projectId':pid,'browser':result,'submitted':False})

    def poll(self, flow, stage):
        key = stage['key']; ref = stage.get('ref', {})
        if key in ('production','jianying'):
            ids=ref.get('ids',[]) or [ref.get('id')]
            if stage.get('result',{}).get('resumePending'):
                for jid in ids:
                    job=self.s.JOBS.get(jid)
                    if job and job['status'] in ('paused','interrupted'):self.s.control_job(jid,'resume')
            result=self._jobs(ids,production=key=='production',flow=flow)
            if stage.get('result',{}).get('resumePending'):
                result.setdefault('result',{})['resumePending']=any(self.s.JOBS.get(jid,{}).get('status')=='pausing' for jid in ids)
                if result.get('reason')=='interrupted' and result['result']['resumePending']:
                    result.update(status='running',reason='',message='等待当前编码安全暂停后恢复，不重复创建任务')
            return result
        if key == 'editor_import':
            task = next((t for t in self.s.STATE['studioFlowTasks'] if t['id']==ref.get('id')), None)
            if task and task['status']=='interrupted' and stage.get('result',{}).get('resumePending'):
                return self._task(stage['operationId'],lambda:self._editor(flow))
            return self._task_result(task) if task else dict(status='failed',message='剪映交接记录不存在')
        # Avoid repeated filesystem probing and save operations every 500ms.
        now=time.monotonic(); stamp=(flow['id'],key)
        if now-self.last_poll.get(stamp,0)<2:return dict(status=stage['status'],reason=stage.get('reason',''),message=stage.get('message',''))
        self.last_poll[stamp]=now
        if key=='evidence':return self._evidence(flow)
        if key=='materials':return self._materials(flow)
        if key=='export':
            self._outputs(flow)
            changed=self._material_version(flow)
            if changed:return changed
            return self._publish_tasks(ref.get('ids', []))
        if key=='publish':return self._browser(flow,stage,stage['operationId'])
        return dict(status='waiting_action',reason='review',message='请检查成片后确认继续')

    def resume(self, flow, stage, operation):
        key=stage['key']; ref=stage.get('ref', {})
        if key=='review':
            if stage.get('resumeData',{}).get('reviewConfirmed') is True:
                return dict(status='completed',message='本人已检查成片',result={'reviewedAt':time.time()})
            return dict(status='waiting_action',reason='review',message='请先检查成片，再确认继续')
        if key in ('production','jianying'):
            ids=ref.get('ids',[]) or ([ref['id']] if ref.get('id') else [])
            if not ids:return self.start(flow,stage,operation)  # create_job reconciles stable operation tags
            for jid in ids:
                job=self.s.JOBS.get(jid)
                if job and job['status'] in ('paused','interrupted','failed'):self.s.control_job(jid,'resume')
            stage.setdefault('result',{})['resumePending']=True
            return self.poll(flow,stage)
        if key=='editor_import':
            self.events.setdefault(flow['id'],threading.Event()).clear()
            task=next((t for t in self.s.STATE['studioFlowTasks'] if t['id']==operation),None)
            if task and task['status'] in ('failed', 'waiting_action'):
                with self.s.LOCK:task['status']='interrupted';self.s.save()
            result=self._task(operation,lambda:self._editor(flow))
            result.setdefault('result',{})['resumePending']=True
            return result
        if key=='export':
            # Interrupted copies are retained for diagnosis; a deliberate retry
            # uses workspace retry validation, never starts from a polling loop.
            self._outputs(flow)
            changed=self._material_version(flow,accept=True)
            if changed:return changed
            ids=self._export_tasks(flow,operation,retry=True)
            return dict(status='running',ref={'kind':'publish_tasks','ids':ids},message='恢复发布资料导出，已完成的制作保持不变')
        if key=='publish':
            changed=self._material_version(flow,accept=True)
            if changed:return changed
            # _browser resolves only the current remaining drama and revision;
            # an old no-fill task cannot hijack another drama's recovery.
            stage.setdefault('result',{})['retryNoFill']=True
            result=self._browser(flow,stage,operation,retry_open=True)
            result.setdefault('result',{}).setdefault('retryNoFill',True)
            return result
        return self.poll(flow,stage)

    def control(self, flow, stage, action):
        if stage['key']=='editor_import':self.events.setdefault(flow['id'],threading.Event()).set()
        ref=stage.get('ref',{})
        if ref.get('kind') in ('job','jobs'):
            for jid in ref.get('ids',[]) or [ref.get('id')]:
                job=self.s.JOBS.get(jid)
                if job and job['status'] in ('queued','running','pausing','paused','interrupted'):
                    self.s.control_job(jid,action)

    def shutdown(self):
        self.stop.set()
        for event in self.events.values():event.set()
