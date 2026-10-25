"""Local publishing preparation and visible-browser assistance orchestration.

No final submit is performed here. Platform results are separately recorded by
the owner after checking the actual official backend.
"""
from __future__ import annotations
import copy
import hashlib
import os
from pathlib import Path
import re
import threading
import time
import urllib.parse
import uuid

import publish_materials

SETTING_KEYS = {'title','synopsis','producer','trialEpisodes','dramaType','episodeCount',
                'totalCostYuan','rightsConfirmed','coverPath','proofImages','storyboardImages',
                'costImages','copyrightImages','costReportPaths'}
PATH_LISTS = {'proofImages','storyboardImages','costImages','copyrightImages','costReportPaths'}


class Workspace:
    def __init__(self, state, data, lock, save, snapshot, probe, browser_factory=None):
        self.state, self.data, self.lock, self.save = state, Path(data), lock, save
        self.snapshot, self.probe = snapshot, probe
        self.browser_factory = browser_factory
        self._browser = None
        self._threads = set()
        self._stop = threading.Event()
        with lock:
            value = state.setdefault('publishWorkspace', {})
            for key, default in [('settings',{}),('plans',{}),('tasks',[]),('browser',{}),('records',[])]:
                value.setdefault(key, default)
            for task in value['tasks']:
                if task.get('status') in ('queued','running'):
                    task.update(status='interrupted',stage='上次操作已中断，请核对资料或官方后台后重新开始')
            # A saved browser snapshot is not evidence of a current login session.
            for item in value['browser'].values():
                item.update(loginState='unknown',stale=True)

    @property
    def value(self):
        return self.state['publishWorkspace']

    def public(self):
        with self.lock:
            return copy.deepcopy(self.value)

    def settings(self, pid, values):
        self.snapshot(pid)
        if not isinstance(values,dict) or set(values)-SETTING_KEYS:
            raise ValueError('提审配置字段无效')
        clean={}
        for key,value in values.items():
            if key in PATH_LISTS:
                if not isinstance(value,list) or len(value)>200 or any(not isinstance(x,str) or len(x)>2000 for x in value):
                    raise ValueError('附件列表无效，一类最多选择200个文件')
                clean[key]=list(dict.fromkeys(x.strip() for x in value if x.strip()))
            elif key=='rightsConfirmed':
                if type(value) is not bool:raise ValueError('素材授权确认值无效')
                clean[key]=value
            elif key in ('trialEpisodes','episodeCount'):
                if value in ('',None):clean[key]=None;continue
                if type(value) is not int or not 1<=value<=10000:raise ValueError('集数需填写1至10000的整数')
                clean[key]=value
            elif key=='totalCostYuan':
                if value in ('',None):clean[key]=None;continue
                if type(value) not in (int,float) or not 0<value<=1e12:raise ValueError('请填写实际制作成本，单位为元')
                clean[key]=value
            else:
                if not isinstance(value,str) or len(value)>(20000 if key=='synopsis' else 2000):raise ValueError('提审字段长度无效')
                if key=='dramaType' and value not in ('animation','digital'):raise ValueError('剧目类型无效')
                clean[key]=value.strip()
        with self.lock:
            self.value['settings'].setdefault(pid,{}).update(clean)
            self.value['plans'].pop(pid,None)
            self.save()
        return self.public()

    def inspect(self,pid,overrides=None):
        if overrides is not None:self.settings(pid,overrides)
        project,config=self.snapshot(pid)
        with self.lock:settings=copy.deepcopy(self.value['settings'].get(pid,{}))
        plan=publish_materials.inspect(project,config,settings,probe=self.probe)
        plan['checkedAt']=time.time()
        with self.lock:
            self.value['plans'][pid]=plan
            self.save()
        return copy.deepcopy(plan)

    def discover(self,folder):
        if not isinstance(folder,str) or not folder.strip():raise ValueError('请选择剧目总文件夹或单部剧的成品目录')
        return {'candidates':publish_materials.discover(folder)}

    def import_folders(self,folders):
        if not isinstance(folders,list) or not 1<=len(folders)<=100 or any(not isinstance(x,str) for x in folders):
            raise ValueError('一次可导入1至100个剧目文件夹')
        imported=[]
        for folder in dict.fromkeys(folders):
            directory=Path(folder).expanduser().resolve()
            plan=publish_materials.inspect_folder(directory,{},probe=self.probe)
            videos=plan['files']['videos']
            if not videos:raise ValueError(directory.name+' 没有可读取的成品视频')
            pid=hashlib.sha256(('publish:'+str(directory).casefold()).encode()).hexdigest()[:16]
            fields=plan['fields']
            entries=[]
            for video in videos:
                value=dict(video,mtime=Path(video['path']).stat().st_mtime)
                if not value.get('duration'):value.update(self.probe(video['path']))
                entries.append(value)
            with self.lock:
                old=next((p for p in self.state['projects'] if p['id']==pid),None)
                if old is None:
                    self.state['projects'].append({'id':pid,'source':str(directory),'name':plan['title'],
                        'originalName':plan['title'],'intro':fields.get('synopsis',''),'originalIntro':fields.get('synopsis',''),
                        'cover':(plan['files'].get('cover') or {}).get('path',''),'videos':entries,
                        'status':'已导入成品','review':'待准备','rights':False,'notes':'本人选择成品目录导入，仅用于发布准备',
                        'artifacts':[{'path':v['path'],'name':v['name'],'bytes':v['bytes'],'kind':'视频','job':'publish-import','time':''} for v in entries],
                        'finalVideoPaths':[v['path'] for v in entries],'publishFolder':str(directory)})
                spec={k:fields[k] for k in SETTING_KEYS if k in fields and k!='rightsConfirmed'}
                for key in PATH_LISTS:
                    filekey={'costReportPaths':'costReports'}.get(key,key)
                    spec[key]=[v['path'] for v in plan['files'].get(filekey,[])]
                if plan['files'].get('cover'):spec['coverPath']=plan['files']['cover']['path']
                # Import does not assert copyright; preserve an explicit saved confirmation.
                self.value['settings'][pid]=spec|self.value['settings'].get(pid,{})
                self.save()
            imported.append(pid)
            self.inspect(pid)
        return {'projectIds':imported,**self.public()}

    def _account(self,account_id):
        with self.lock:account=next((a for a in self.state['accounts'] if a['id']==account_id),None)
        if not account:raise ValueError('请先选择一个已添加的视频号账号')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',account['id']):raise ValueError('账号标识无效')
        return copy.deepcopy(account)

    def _start(self,kind,pid,account_id,work):
        if self._stop.is_set():raise ValueError('发布工作区正在关闭')
        with self.lock:
            if self._stop.is_set():raise ValueError('发布工作区正在关闭')
            active=[t for t in self.value['tasks'] if t['status'] in ('queued','running')]
            if any((account_id and t.get('accountId')==account_id) or (not account_id and t['kind']==kind and t.get('projectId')==pid) for t in active):
                raise ValueError('已有相同发布操作正在进行，请等待当前操作完成')
            task={'id':uuid.uuid4().hex[:16],'kind':kind,'projectId':pid,'accountId':account_id,
                  'status':'queued','stage':'等待执行','createdAt':time.time(),'result':None,'error':''}
            self.value['tasks'].append(task)
            self.value['tasks']=self.value['tasks'][-100:]
            self.save()
        def run():
            try:
                with self.lock:
                    if self._stop.is_set():raise InterruptedError('发布工作区已关闭')
                    task.update(status='running',stage='整理提审资料' if kind=='export' else '正在操作官方后台');self.save()
                result=work(task)
                with self.lock:
                    if self._stop.is_set():task.update(status='interrupted',stage='应用已关闭，请核对操作结果')
                    else:
                        task.update(status='completed',stage='资料已导出' if kind=='export' else '后台操作完成，请查看检测结果',result=result)
                        if kind.startswith('browser_'):self.value['browser'][account_id]=result|{'checkedAt':time.time(),'stale':False}
                    task['finishedAt']=time.time();self.save()
            except Exception as error:
                with self.lock:
                    task.update(status='interrupted' if self._stop.is_set() else 'failed',stage='应用已关闭，请核对操作结果' if self._stop.is_set() else '操作未完成',error=str(error)[:1500],finishedAt=time.time());self.save()
            finally:
                with self.lock:self._threads.discard(threading.current_thread())
        thread=threading.Thread(target=run,name='publish-'+task['id'],daemon=True)
        with self.lock:self._threads.add(thread)
        thread.start()
        return {'taskId':task['id'],'status':'queued'}

    def export(self,pid):
        plan=self.inspect(pid)
        if not plan['ready']:raise ValueError('资料尚未齐全：'+'；'.join(plan['errors'][:4]))
        _,config=self.snapshot(pid)
        destination=Path(config['output']).resolve()/'提审资料'
        destination.mkdir(parents=True,exist_ok=True)
        def work(task):
            last=[0.0]
            def progress(done,total,name):
                now=time.monotonic()
                if done!=total and now-last[0]<.4:return
                last[0]=now
                with self.lock:
                    task.update(stage='正在复制并校验：'+name,completedBytes=done,totalBytes=total,
                                percent=round(done/max(1,total)*100,1));self.save()
            return publish_materials.export_packet(plan,destination,cancel=self._stop.is_set,progress=progress)
        return self._start('export',pid,'',work)

    def browser(self,account_id,action,pid=''):
        if action not in ('open','check','assist','close'):raise ValueError('后台操作无效')
        account=self._account(account_id)
        plan=None
        if action=='assist':
            plan=self.inspect(pid)
            if not plan['ready']:raise ValueError('资料尚未齐全：'+'；'.join(plan['errors'][:4]))
            with self.lock:
                if any(r['projectId']==pid and r['accountId']==account_id and r['status'] in ('submitted','approved') and r.get('fingerprint')==plan['fingerprint'] for r in self.value['records']):
                    raise ValueError('该账号已记录本版本资料提交，先到官方后台核对，避免重复上传')
        def work(task):
            with self.lock:
                if self._stop.is_set():raise InterruptedError('发布工作区已关闭')
                if self._browser is None:
                    if self.browser_factory:self._browser=self.browser_factory(self.data)
                    else:
                        from publish_browser import BrowserManager
                        self._browser=BrowserManager(self.data)
                manager=self._browser
            return manager.command(account,action,{'plan':plan} if plan else {})
        return self._start('browser_'+action,pid,account_id,work)

    def record(self,body):
        pid=body.get('projectId','');self.snapshot(pid)
        account=self._account(body.get('accountId',''))
        status=body.get('status')
        if status not in ('submitted','approved','needs_changes'):raise ValueError('提交记录状态无效')
        note=body.get('note','');url=body.get('evidenceUrl','')
        if not isinstance(note,str) or not isinstance(url,str) or len(note)>3000 or len(url)>2000:raise ValueError('核对说明过长')
        if not note.strip():raise ValueError('请填写在官方后台核对到的结果说明')
        if url:
            parsed=urllib.parse.urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!='channels.weixin.qq.com' or parsed.username or parsed.password:
                raise ValueError('结果链接请填写视频号官方后台的HTTPS地址')
            # Persist no login-ticket or query credentials.
            url=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,'',''))
        plan=self.inspect(pid)
        item={'id':uuid.uuid4().hex[:16],'projectId':pid,'accountId':account['id'],'status':status,
              'note':note.strip(),'evidenceUrl':url,'source':'manual','recordedAt':time.time(),
              'fingerprint':plan['fingerprint'],'platformVerified':False}
        with self.lock:
            self.value['records'].append(item);self.value['records']=self.value['records'][-500:]
            project=next(p for p in self.state['projects'] if p['id']==pid)
            project['review']={'submitted':'已提交','approved':'审核通过','needs_changes':'需修改'}[status]
            project['reviewSource']='manual'
            self.save()
        return copy.deepcopy(item)

    def file(self,pid,path):
        # Reinspect so removed/moved files or stale plans cannot grant access.
        plan=self.inspect(pid)
        allowed=[]
        for group in plan['files'].values():
            allowed.extend(group if isinstance(group,list) else [group] if isinstance(group,dict) else [])
        target=Path(path).resolve()
        if not any(Path(v['path']).resolve()==target for v in allowed) or not target.is_file():raise ValueError('文件不在本剧提审清单中')
        return target

    def open(self,pid,task_id='',key=''):
        project,config=self.snapshot(pid)
        target=Path(project.get('publishFolder') or project.get('source','')).resolve()
        if task_id:
            with self.lock:task=next((x for x in self.value['tasks'] if x['id']==task_id and x['projectId']==pid and x['kind']=='export' and x['status']=='completed'),None)
            if not task:raise ValueError('没有已完成的资料导出任务')
            target=Path(task['result']['directory']).resolve()
        elif key:
            plan=self.inspect(pid);group=plan['files'].get(key)
            first=group[0] if isinstance(group,list) and group else group if isinstance(group,dict) else None
            if not first:raise ValueError('该项还没有附件，请先补充资料')
            target=Path(first['path']).resolve().parent
        if not target.is_dir():raise ValueError('资料目录已被移动')
        if os.name=='nt':os.startfile(str(target))
        return {'path':str(target)}

    def shutdown(self):
        self._stop.set()
        with self.lock:manager=self._browser
        if manager:manager.shutdown()
        with self.lock:
            for task in self.value['tasks']:
                if task['status'] in ('queued','running'):task.update(status='interrupted',stage='应用关闭，重新操作前请核对后台')
            self.save()
