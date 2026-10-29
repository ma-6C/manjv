"""Persistent, ordered episode imports with stable drama directories."""
from pathlib import Path
import copy,hashlib,json,re,threading,time,uuid,shutil,tempfile,concurrent.futures,contextlib
import episode_selection

def read(path,default):
    try:return json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):return copy.deepcopy(default)

def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8');temporary.replace(path)

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def check_storage(directory,required=64*1024**2):
    directory=Path(directory)
    if shutil.disk_usage(directory).free<required:raise ValueError('保存位置空间不足，请更换目录或清理空间后继续')
    try:
        with tempfile.TemporaryFile(dir=directory) as f:f.write(b'check');f.flush()
    except OSError:raise ValueError('保存目录不可写，请检查权限或选择其他目录') from None

class DownloadWindow:
    def __init__(self,limit,adaptive):
        self.limit=limit;self.adaptive=adaptive;self.current=limit
        self.good=0;self.cooldown=0;self.previous=None;self.events=[];self.started=time.monotonic()
        self.sample_start=None;self.sample_bytes=0;self.slow_windows=0;self.lock=threading.RLock()
    def change(self,value,reason):
        old=self.current;self.current=value
        if old!=value:self.events.append({'from':old,'to':value,'reason':reason,'atSeconds':round(time.monotonic()-self.started,3)})
        self.events=self.events[-20:]
    def sample(self,total_bytes,active,now=None):
        if not self.adaptive:return
        now=time.perf_counter() if now is None else now
        with self.lock:
            if active<self.current or self.sample_start is None:
                self.sample_start=now;self.sample_bytes=total_bytes;self.slow_windows=0;return
            elapsed=now-self.sample_start
            if elapsed<6:return
            rate=max(0,total_bytes-self.sample_bytes)/elapsed
            if self.previous and rate<self.previous*.65:self.slow_windows+=1
            else:self.slow_windows=0;self.previous=rate if self.previous is None else self.previous*.5+rate*.5
            if self.slow_windows>=2:
                self.change(max(1,self.current-1),'总下载速度持续回落，降低并行')
                self.previous=None;self.slow_windows=0;self.cooldown=3;self.good=0
            self.sample_start=now;self.sample_bytes=total_bytes
    def observe(self,success,bytes_count=0,seconds=0):
        if not self.adaptive:return
        with self.lock:
            if not success:
                self.change(max(1,self.current//2),'网络异常，降低并行');self.good=0;self.cooldown=3
                self.sample_start=None;self.previous=None
            elif bytes_count>0 and seconds>0:
                self.good+=1
                if self.cooldown:self.cooldown-=1
                elif self.good>=3:
                    self.change(min(self.limit,self.current+1),'传输稳定，逐步增加并行');self.good=0

class ImportManager:
    def __init__(self,data,import_video,probe,adapter):
        self.h=adapter;self.data=Path(data);self.data.mkdir(parents=True,exist_ok=True)
        self.path=self.data/'source-imports.json';self.index_path=self.data/'source-directories.json'
        self.lock=threading.RLock();self.import_video=import_video;self.probe=probe
        self.events={};self.worker=None;self.previews={};self.cache={};self.stopping=False
        stored=read(self.path,[])
        self.rows=[r for r in stored if isinstance(r,dict) and isinstance(r.get('id'),str) and r.get('status')][-100:] if isinstance(stored,list) else []
        self.index=read(self.index_path,{})
        if not isinstance(self.index,dict):self.index={}
        self.h.ACCESS.configure(self.data)
        migrated=False;auto_continue=False
        for r in self.rows:
            r.setdefault('episodes',[1] if r.get('video') else [])
            for key in ('batchSize','confirmBatches'):
                if key in r:r.pop(key);migrated=True
            r.setdefault('downloadConcurrency',1)
            r.setdefault('items',[{'number':n,'status':'completed' if r.get('status')=='completed' else 'pending'} for n in r['episodes']])
            if r.get('status')=='awaiting_confirmation':
                r.update(status='queued',stage='等待自动继续剩余集数');migrated=True;auto_continue=True
            elif r.get('status') in ('queued','running'):r.update(status='interrupted',stage='上次采集中断，完整文件保留；可继续剩余集')
            for item in r.get('items',[]):
                if item.get('status')=='running' or (item.get('status') in ('completed','skipped') and not item.get('path')):item['status']='pending'
                item.pop('activePhase',None)
                for field in ('bytesPerSecond','etaSeconds'):item.pop(field,None)
            if r.get('video') and r['status']=='completed' and any(i['status']=='pending' for i in r['items']):
                r.update(status='interrupted',stage='需要核对本地文件并补做入库，请继续')
        if migrated:self.save()
        if auto_continue:self.start_worker()
    def save(self):write(self.path,self.rows)
    def list(self):
        with self.lock:return copy.deepcopy(self.rows)
    def report(self,jid):
        with self.lock:
            row=self.get(jid)
            return {'format':1,'product':'ManjuStudio','taskId':row['id'],'title':row.get('title'),'status':row['status'],
                'sourceHost':'guoapp/hongguo' if row.get('url','').startswith('guoapp:') else 'hongguoduanju.com','selectedEpisodes':row.get('episodes',[]),'completedEpisodes':row.get('done',0),
                'downloadMode':'continuous',
                'downloadConcurrency':row.get('downloadConcurrency',1),'elapsedSeconds':row.get('elapsedSeconds',0),
                'downloadConcurrencyActual':row.get('downloadConcurrencyActual'), 'adaptiveDownloads':row.get('adaptiveDownloads',False),
                'segmentedDownload':row.get('segmentedDownload',False),'downloadQuality':row.get('downloadQuality',0),
                'connectionLimit':6 if row.get('url','').startswith('guoapp:') else 2,
                'phaseSeconds':row.get('phaseSeconds',{}),'concurrencyChanges':row.get('concurrencyChanges',[]),
                'stage':row.get('stage'),'failedStage':row.get('failedStage'),'bytes':row.get('bytes',0),'totalBytes':row.get('totalBytes'),
                'bytesPerSecond':row.get('bytesPerSecond'),'transferSeconds':row.get('transferSeconds'),'etaSeconds':row.get('etaSeconds'),
                'items':[{k:i.get(k) for k in ('number','status','error','errorCode','failedStage','bytes','duration','stage','totalBytes','bytesPerSecond','transferSeconds','etaSeconds','phaseSeconds','activePhase','requestedQuality','actualQuality','transferMode')} for i in row.get('items',[])],
                'note':'不含接口密钥、授权码、完整文件路径或原始网页内容。'}
    def update(self,row,**values):
        with self.lock:row.update(values,updatedAt=time.time())
    @contextlib.contextmanager
    def timing(self,row,item,phase):
        begun=time.perf_counter()
        if item is not None:
            with self.lock:item['activePhase']=phase
        try:yield
        finally:
            elapsed=time.perf_counter()-begun
            with self.lock:
                totals=row.setdefault('phaseSeconds',{});totals[phase]=totals.get(phase,0)+elapsed
                if item is not None:
                    values=item.setdefault('phaseSeconds',{});values[phase]=values.get(phase,0)+elapsed
                    if item.get('activePhase')==phase:item.pop('activePhase',None)
    def progress(self,row,item=None,tuner=None):
        samples=[];begun=time.monotonic()
        def track(done,total):
            now=time.monotonic();samples.append((now,done))
            while len(samples)>2 and now-samples[0][0]>10:samples.pop(0)
            elapsed=now-samples[0][0];rate=(done-samples[0][1])/elapsed if elapsed>=.2 else None
            values=dict(bytes=done,totalBytes=total,bytesPerSecond=rate,transferSeconds=now-begun,
                        etaSeconds=max(0,(total-done)/rate) if total and rate and rate>0 else None)
            with self.lock:
                if item is None:self.update(row,**values);return
                item.update(values)
                active=[i for i in row['items'] if i.get('status')=='running' and i.get('activePhase')=='download']
                item['networkBytes']=done
                if tuner:
                    transferring=sum(bool(i.get('bytesPerSecond')) and i.get('bytes',0)>0 and (not i.get('totalBytes') or i['bytes']<i['totalBytes']) for i in active)
                    tuner.sample(sum(i.get('networkBytes',0) for i in row['items']),transferring)
                self.update(row,bytes=sum(i.get('bytes',0) for i in active),
                    totalBytes=sum(i['totalBytes'] for i in active) if active and all(i.get('totalBytes') for i in active) else None,
                    bytesPerSecond=sum(i.get('bytesPerSecond') or 0 for i in active) or None,
                    transferSeconds=now-begun,etaSeconds=None)
        return track
    def html(self,url,refresh=False,cancel=None,expected_episode=None):
        with self.lock:cached=self.cache.get(url)
        if not refresh and cached and time.monotonic()-cached[0]<300:return cached[1]
        value=self.h.fetch_html(url,cancel,expected_episode=expected_episode) if expected_episode is not None else self.h.fetch_html(url,cancel)
        with self.lock:
            self.cache[url]=(time.monotonic(),value)
            while len(self.cache)>24:self.cache.pop(next(iter(self.cache)))
        return value
    def resolve(self,value,refresh=False,cancel=None):
        url=self.h.site_url(value);html=self.html(url,refresh,cancel)
        result=self.h.parse_catalog(html,url) if '/category/' in url else self.h.parse_detail(html,url)
        self.remember(result);return result
    def remember(self,value):
        if value.get('kind')!='detail':return
        with self.lock:
            self.previews[value['seriesId']]={'url':value.get('coverUrl','')}
            while len(self.previews)>24:self.previews.pop(next(iter(self.previews)))
    def cover(self,sid):
        with self.lock:entry=self.previews.get(sid,{})
        if not entry.get('url'):raise ValueError('封面未提供，请先读取剧集详情')
        if 'bytes' not in entry:
            with self.h.response(entry['url'],True) as r:data=r.read(2*1024*1024+1)
            ext=self.h.image_extension(data[:16])
            if len(data)>2*1024*1024 or not ext:raise ValueError('封面过大或格式未识别')
            with self.lock:entry.update(bytes=data,mime={'.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'}[ext])
        return entry['bytes'],entry['mime']
    def start_worker(self):
        if self.stopping:raise ValueError('服务正在关闭，请重新打开软件')
        if not self.worker or not self.worker.is_alive():
            self.worker=threading.Thread(target=self.run,daemon=True);self.worker.start()
    def start(self,body):
        url=self.h.site_url(body.get('url',''))
        if '/detail?' not in url and not url.startswith('guoapp://hongguo/detail/'):raise ValueError('请先选择一部剧集')
        value=body.get('directory')
        if not isinstance(value,str) or not value.strip():raise ValueError('请选择保存目录')
        root=Path(value).expanduser()
        if not root.is_absolute() or not root.is_dir():raise ValueError('保存目录必须是已存在的绝对路径')
        root=root.resolve();check_storage(root);video=body.get('video',False)
        if type(video) is not bool:raise ValueError('下载选项无效')
        numbers=episode_selection.normalize(body.get('episodes',[1]),order=body.get('order','chosen')) if video else []
        concurrency=body.get('downloadConcurrency',1)
        allowed_concurrency=[1,2,3,5] if url.startswith('guoapp://hongguo/detail/') else [1,2]
        if type(concurrency) is not int or concurrency not in allowed_concurrency:raise ValueError('同时下载请选择'+('1、2、3或5集' if len(allowed_concurrency)>2 else '1集或2集'))
        native=url.startswith('guoapp://hongguo/detail/')
        adaptive=body.get('adaptiveDownloads',False);segmented=body.get('segmentedDownload',False);quality=body.get('downloadQuality',0)
        if type(adaptive) is not bool or type(segmented) is not bool:raise ValueError('下载加速选项无效')
        if type(quality) is not int or quality not in (0,720,1080):raise ValueError('画质请选择最高可用、720p或1080p')
        if not native and (segmented or quality):raise ValueError('当前来源不支持分段或画质选择，请使用原生剧库')
        with self.lock:
            active=[r for r in self.rows if r['status'] in ('queued','running','awaiting_confirmation','limited')]
            if len(active)>=20:raise ValueError('采集队列已满')
            for r in active:
                if r['url']==url and Path(r['directory'])==root and set(numbers).intersection(r.get('episodes',[])):
                    raise ValueError('所选集数已有采集任务，请在队列中继续，避免重复下载')
            row={'id':uuid.uuid4().hex,'url':url,'directory':str(root),'video':video,'episodes':numbers,
                 'downloadConcurrency':concurrency,'order':body.get('order','chosen'),'status':'queued','stage':'等待采集','createdAt':time.time(),
                 'adaptiveDownloads':adaptive,'segmentedDownload':segmented,'downloadQuality':quality,'phaseSeconds':{},
                 'bytes':0,'totalBytes':None,'done':0,'warnings':[],
                 'items':[{'number':n,'status':'pending'} for n in numbers]}
            self.rows.append(row)
            while len(self.rows)>100:
                terminal=next((r for r in self.rows if r['status'] in ('completed','cancelled','failed')),None)
                if not terminal:break
                self.rows.remove(terminal)
            self.events[row['id']]=threading.Event();self.save();self.start_worker()
            return copy.deepcopy(row)
    def get(self,jid):
        row=next((r for r in self.rows if r['id']==jid),None)
        if not row:raise ValueError('采集任务不存在')
        return row
    def control(self,jid,action,episodes=None):
        with self.lock:
            row=self.get(jid)
            if action=='cancel':
                if row['status'] not in ('queued','running','awaiting_confirmation','limited','interrupted'):raise ValueError('没有可停止的采集任务')
                self.events.setdefault(jid,threading.Event()).set()
                if row['status']!='running':row.update(status='cancelled',stage='已停止，完整文件保留')
            elif action=='resume':
                if row['status'] not in ('awaiting_confirmation','limited','interrupted','failed','cancelled'):raise ValueError('当前任务不能继续')
                self.h.ACCESS.resume()
                for item in row.get('items',[]):
                    if item.get('status') in ('failed','running') or (item.get('status') in ('completed','skipped') and not item.get('path')):item['status']='pending'
                self.events[jid]=threading.Event();row.update(status='queued',stage='等待继续剩余集数')
                self.start_worker()
            elif action=='reorder':
                if row['status'] not in ('queued','awaiting_confirmation','interrupted'):raise ValueError('请在等待状态调整顺序')
                remaining=[x for x in row.get('items',[]) if x['status']=='pending']
                ordered=episode_selection.normalize(episodes)
                if set(ordered)!={x['number'] for x in remaining}:raise ValueError('排序必须包含每个剩余集数，且不能增加其他集')
                mapping={x['number']:x for x in remaining}
                row['items']=[x for x in row['items'] if x['status']!='pending']+[mapping[n] for n in ordered]
                row['episodes']=[x['number'] for x in row['items']]
            else:raise ValueError('未知采集操作')
            self.save();return copy.deepcopy(row)
    def cancel(self,jid):return self.control(jid,'cancel')
    def directory(self,root,meta,row=None):
        root=Path(root).resolve();key=str(root).casefold()+'|'+meta['platform']+'|'+meta['seriesId']
        with self.lock:
            saved=self.index.get(key)
            title=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',meta['title']).strip(' .')[:60] or '漫剧'
            if not re.fullmatch(r'\d{5,30}',meta['seriesId']):raise ValueError('剧集ID无效，无法确定独立保存目录')
            platform_dir=(root/('红果原生' if meta.get('platform')=='guoapp_hongguo' else '红果')).resolve()
            if not platform_dir.is_relative_to(root):raise ValueError('归档目录超出所选保存位置')
            canonical=platform_dir/(title+'__'+meta['seriesId'])
            target=Path(saved).resolve() if isinstance(saved,str) and saved else canonical.resolve()
            if target.parent!=platform_dir or not target.name.endswith('__'+meta['seriesId']):
                target=canonical.resolve()
                if row is not None:
                    warning='旧保存目录映射无效，已改用本剧独立子文件夹；原目录中的视频未移动'
                    if warning not in row['warnings']:row['warnings'].append(warning)
            if target.parent!=platform_dir or not target.is_relative_to(root):raise ValueError('归档目录超出本剧独立保存位置')
            if target.exists():
                metadata=target/'剧集资料.json'
                if metadata.exists():
                    existing=read(metadata,{})
                    if not isinstance(existing,dict) or existing.get('seriesId')!=meta['seriesId'] or existing.get('platform')!=meta['platform']:
                        raise ValueError('本剧保存目录中的资料属于其他剧或已损坏，未写入视频，请核对保存位置')
                elif any(target.iterdir()):
                    raise ValueError('同名目录已有其他资料，请选择其他保存位置')
            target.mkdir(parents=True,exist_ok=True);self.index[key]=str(target);write(self.index_path,self.index)
            return target
    def records(self,directory):
        path=directory/'下载记录.json'
        try:result=json.loads(path.read_text('utf-8')) if path.exists() else []
        except (OSError,ValueError):raise ValueError('下载清单无法读取，请保留文件并核对本地资料') from None
        if not isinstance(result,list):raise ValueError('下载清单格式损坏，请先核对本地资料')
        return [r for r in result if isinstance(r,dict) and type(r.get('episode')) is int and Path(r.get('filename','')).name==r.get('filename')]
    def process(self,row,event):
        with self.timing(row,None,'lookup'):meta=self.resolve(row['url'],cancel=event)
        self.update(row,title=meta['title'])
        if event.is_set():raise self.h.Cancelled()
        meta['importRoot']=str(Path(row['directory']).resolve())
        directory=self.directory(row['directory'],meta,row);check_storage(directory);self.update(row,savedDirectory=str(directory))
        records=self.records(directory)
        temporary_dir=directory/'.下载中';temporary_dir.mkdir(exist_ok=True)
        if not temporary_dir.resolve().is_relative_to(directory.resolve()):raise ValueError('临时目录不在素材目录中')
        # Commit intent is durable before moving the verified media into its final filename.
        for item in row['items']:
            journal=temporary_dir/f'{item["number"]}.commit.json'
            if not journal.exists():continue
            entry=read(journal,{})
            if entry.get('episode')!=item['number'] or not re.fullmatch(r'\d+',str(entry.get('episodeId',''))) or entry.get('filename')!=f'第{item["number"]:04}集.mp4':
                raise ValueError('下载恢复记录无效，请保留文件并人工核对')
            target=directory/entry['filename'];temporary=temporary_dir/(entry['episodeId']+'.download')
            candidate=target if target.exists() else temporary
            if not candidate.resolve().is_relative_to(directory.resolve()):raise ValueError('下载恢复路径超出素材目录')
            if not candidate.is_file() or candidate.stat().st_size!=entry.get('bytes') or digest(candidate)!=entry.get('sha256'):
                raise ValueError('下载恢复文件与校验记录不一致，未覆盖文件')
            if not self.probe(candidate).get('duration',0)>0:raise ValueError('下载恢复视频校验失败')
            if candidate==temporary:temporary.rename(target)
            previous=next((r for r in records if r['episode']==item['number']),None)
            if previous and previous!=entry:raise ValueError('下载恢复记录与已有清单冲突，未覆盖')
            records=[r for r in records if r['episode']!=item['number']]+[entry];records.sort(key=lambda r:r['episode'])
            write(directory/'下载记录.json',records)
        available={e['number']:e for e in meta.get('episodes',[])}
        # Keep only links actually returned by the source for this task. A refreshed
        # catalogue may expose fewer entries; that must not erase already selected links.
        snapshot=row.setdefault('episodeLinks',{})
        saved_directory=Path(row.get('savedDirectory',''))
        if not snapshot and saved_directory.is_absolute() and saved_directory.resolve().is_relative_to(Path(row['directory']).resolve()):
            legacy=read(saved_directory/'剧集资料.json',{})
            if legacy.get('platform')==meta['platform'] and legacy.get('seriesId')==meta['seriesId']:
                snapshot.update({str(e['number']):copy.deepcopy(e) for e in legacy.get('episodes',[]) if isinstance(e,dict) and e.get('number') in row['episodes']})
        for n in row['episodes']:
            if n in available:snapshot.setdefault(str(n),copy.deepcopy(available[n]))
        for raw,entry in snapshot.items():
            n=int(raw)
            valid_entry=self.h.valid_episode_entry(meta,entry) if hasattr(self.h,'valid_episode_entry') and isinstance(entry,dict) else isinstance(entry,dict) and bool(re.fullmatch(r'https://hongguoduanju\.com/player/'+re.escape(meta['seriesId'])+r'(?:/\d+)?',entry.get('playerUrl','')))
            if n not in row['episodes'] or not isinstance(entry,dict) or entry.get('number')!=n or not valid_entry:
                raise ValueError('已选集播放入口记录无效，请核对来源后创建新任务')
            available[n]=entry
        with self.lock:self.save()
        recorded={r['episode'] for r in records if (directory/r['filename']).is_file()}
        locked=set(meta.get('lockedEpisodes',[]))
        missing=[i['number'] for i in row['items'] if i['status'] not in ('completed','skipped') and i['number'] not in available and i['number'] not in recorded and i['number'] not in locked]
        if missing:raise ValueError('来源未提供所选集的公开入口：'+','.join(map(str,missing))+'；没有改为下载其他集')
        if not (directory/'简介.txt').exists():(directory/'简介.txt').write_text(meta['intro'],'utf-8-sig')
        meta['downloadRecords']=records
        write(directory/'剧集资料.json',meta)
        cover=next((p for p in directory.glob('封面.*') if p.suffix in ('.jpg','.png','.webp')),None)
        if not cover and meta.get('coverUrl'):
            try:
                self.update(row,stage='保存原始封面',bytes=0,totalBytes=None)
                temporary=directory/'封面.image'
                self.h.download(meta['coverUrl'],temporary,event,self.progress(row),True)
                ext=self.h.image_extension(temporary.read_bytes()[:16])
                if not ext:temporary.unlink();raise ValueError('封面格式未识别')
                cover=directory/('封面'+ext);temporary.rename(cover)
            except (self.h.Cancelled,self.h.SourceLimited):raise
            except Exception:
                if '封面未保存' not in row['warnings']:row['warnings'].append('封面未保存')
        commit_lock=threading.RLock();claimed_ids={r['episodeId']:r['episode'] for r in records}
        def item_stage(item,text):
            with self.lock:
                item.update(stage=text)
                active=[i for i in row['items'] if i.get('status')=='running']
                self.update(row,currentEpisode=item['number'],stage=text if len(active)<=1 else '同时处理：'+ '、'.join('第'+str(i['number'])+'集' for i in active))
        def process_item(item):
            nonlocal records
            if event.is_set():raise self.h.Cancelled()
            try:
                n=item['number']
                with self.lock:item.update(status='running',bytes=0,totalBytes=None,bytesPerSecond=None,etaSeconds=None)
                item_stage(item,f'核对第{n}集')
                existing=next((r for r in records if r['episode']==n),None)
                path=directory/(existing['filename'] if existing else f'第{n:04}集.mp4')
                if not path.resolve().is_relative_to(directory.resolve()):raise ValueError('集数文件超出素材目录')
                # A verified local record is sufficient for resuming an import.
                # Do not wait on a remote page again just to skip the same file.
                with self.timing(row,item,'lookup'):
                    if existing and path.exists():
                        info={'episodeId':existing['episodeId'],'uploadDate':existing.get('episodeUploadDate')}
                    elif n in locked:raise ValueError('剧集已锁定，当前来源未提供可访问的素材；请在平台核对授权或导出入口')
                    elif n in available and meta.get('platform')=='guoapp_hongguo':
                        info=self.h.resolve_episode(meta,n,available[n],event)
                    elif n in available:
                        player_url=available[n]['playerUrl']
                        player_html=self.html(player_url,cancel=event,expected_episode=n)
                        try:info=self.h.parse_player(player_html,meta['seriesId'],n,player_url)
                        except ValueError as e:
                            if '剧集已锁定' in str(e):raise
                            item_stage(item,f'重新核对第{n}集来源资料')
                            info=self.h.parse_player(self.html(player_url,refresh=True,cancel=event,expected_episode=n),meta['seriesId'],n,player_url)
                    else:info={'episodeId':existing['episodeId'],'uploadDate':existing.get('episodeUploadDate')}
                if existing and existing.get('episodeId')!=info['episodeId']:raise ValueError(f'第{n}集来源版本不同，已保留本地文件，请人工核对')
                with commit_lock:
                    owner=claimed_ids.setdefault(info['episodeId'],n)
                    if owner!=n:raise ValueError('网页集序无法核对：多个集号指向相同视频，未重复下载')
                if path.exists():
                    item_stage(item,f'等待校验第{n}集');yield
                    with self.timing(row,item,'verify'):
                        if not existing or path.stat().st_size!=existing.get('bytes') or digest(path)!=existing.get('sha256'):
                            raise ValueError(f'第{n}集本地文件与记录不一致，未覆盖，请核对')
                        details=self.probe(path);outcome='skipped'
                else:
                    check_storage(directory)
                    temporary=temporary_dir/(info['episodeId']+'.download')
                    temporary.unlink(missing_ok=True)
                    try:
                        item_stage(item,f'下载第{n}集')
                        with self.timing(row,item,'download'):
                            if meta.get('platform')=='guoapp_hongguo' and hasattr(self.h,'fetch_media'):plan=self.h.fetch_media(info['url'],event,self.progress(row,item,window))
                            else:self.h.download(info['url'],temporary,event,self.progress(row,item,window));plan=None
                        item_stage(item,f'等待转存校验第{n}集');yield
                        if event.is_set():raise self.h.Cancelled()
                        if plan is not None:
                            item_stage(item,f'转存第{n}集')
                            with self.timing(row,item,'materialize'):self.h.materialize_media(plan,temporary,event)
                            item.update(requestedQuality=row.get('downloadQuality',0),actualQuality=plan.get('quality',0),transferMode=plan.get('transferMode','single'))
                        item_stage(item,f'校验第{n}集视频与音轨')
                        with self.timing(row,item,'verify'):
                            details=self.probe(temporary);checksum=digest(temporary)
                        if not item.get('actualQuality'):
                            dimensions=[details.get('width',0),details.get('height',0)]
                            item['actualQuality']=min(dimensions) if all(dimensions) else 0
                        if not details.get('duration',0)>0:raise ValueError(f'第{n}集视频校验失败')
                        if event.is_set():raise self.h.Cancelled()
                        entry={'episode':n,'episodeId':info['episodeId'],'scope':'原生来源' if meta.get('platform')=='guoapp_hongguo' else '网页公开版','filename':path.name,'bytes':temporary.stat().st_size,
                               'sha256':checksum,'duration':details['duration'],'audio':details.get('audio',False),
                               'requestedQuality':row.get('downloadQuality',0),'actualQuality':item.get('actualQuality',0),
                               'episodeUploadDate':info['uploadDate'],'verifiedAt':time.time()}
                        with commit_lock:
                            write(temporary_dir/f'{n}.commit.json',entry)
                            temporary.rename(path)
                    finally:
                        if not (temporary_dir/f'{n}.commit.json').exists():temporary.unlink(missing_ok=True)
                    with commit_lock:
                        records=[r for r in records if r['episode']!=n]+[entry];records.sort(key=lambda r:r['episode'])
                        write(directory/'下载记录.json',records)
                    outcome='completed'
                with commit_lock:
                    meta['downloadRecords']=records;meta['savedCover']=cover.name if cover else None;write(directory/'剧集资料.json',meta)
                    details.update(sourceEpisode=n,sourceEpisodeId=info['episodeId'])
                    with self.timing(row,item,'import'):pid=self.import_video(directory,meta,path,cover,details)
                    with self.lock:
                        item.update(status=outcome,stage='已入库' if outcome=='completed' else '本地校验通过，已跳过下载',path=str(path),duration=details['duration'],bytes=path.stat().st_size,bytesPerSecond=None,etaSeconds=None);item.pop('error',None);item.pop('errorCode',None);item.pop('failedStage',None)
                        self.update(row,projectId=pid,videoDuration=details['duration'],done=sum(x['status'] in ('completed','skipped') for x in row['items']))
                        self.save()
                    try:(temporary_dir/f'{n}.commit.json').unlink(missing_ok=True)
                    except OSError:
                        if '恢复记录待下次清理（素材已入库）' not in row['warnings']:row['warnings'].append('恢复记录待下次清理（素材已入库）')
            except (self.h.Cancelled,self.h.SourceLimited):raise
            except ValueError as e:
                message=str(e)
                if not any(text in message for text in ('HTTP 404','来源页面读取失败','连接来源网站','网页集序无法核对','未提供可验证','下载连接中断','视频校验失败','剧集已锁定')):raise
                with self.lock:
                    item.update(status='failed',error=message[:220],failedStage=item.get('stage',''),stage='本集未完成',bytesPerSecond=None,etaSeconds=None)
                    item['errorCode']='source_locked' if '剧集已锁定' in message else 'source_not_found' if 'HTTP 404' in message else 'identity_mismatch' if '网页集序无法核对' in message else 'source_unavailable'
                    self.save()
        pending=[i for i in row['items'] if i['status'] not in ('completed','skipped')]
        concurrency=row.get('downloadConcurrency',1)
        window=DownloadWindow(concurrency,row.get('adaptiveDownloads',False));iterator=iter(pending);exhausted=False
        active={};processing={};generators=[]
        def fetch_item(item):
            generator=process_item(item)
            try:next(generator)
            except StopIteration:return None
            return generator
        def finish_item(generator):
            try:next(generator)
            except StopIteration:return
            finally:generator.close()
            raise RuntimeError('分集处理阶段无效')
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as network_pool, concurrent.futures.ThreadPoolExecutor(max_workers=2) as processing_pool:
            def submit_more():
                nonlocal exhausted
                if event.is_set():raise self.h.Cancelled()
                if self.h.ACCESS.snapshot().get('paused'):raise self.h.SourceLimited('来源访问已暂停，完整文件和队列保留')
                while not exhausted and len(active)<window.current and len(active)+len(processing)<concurrency+2:
                    item=next(iterator,None)
                    if item is None:exhausted=True;break
                    active[network_pool.submit(fetch_item,item)]=item
                self.update(row,downloadConcurrencyActual=window.current,processingJobs=len(processing),concurrencyChanges=copy.deepcopy(window.events))
            try:
                submit_more()
                while active or processing:
                    completed,_=concurrent.futures.wait([*active,*processing],return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in completed:
                        if future in active:
                            item=active.pop(future);generator=future.result()
                            if item.get('status')!='failed':window.observe(True,item.get('bytes',0),item.get('phaseSeconds',{}).get('download',0))
                            elif item.get('errorCode') in ('source_unavailable','source_not_found'):window.observe(False)
                            if generator is not None:generators.append(generator);processing[processing_pool.submit(finish_item,generator)]=item
                        else:processing.pop(future);future.result()
                    submit_more()
            except BaseException:
                event.set()
                for future in [*active,*processing]:future.cancel()
                raise
            finally:
                network_pool.shutdown(wait=True,cancel_futures=True);processing_pool.shutdown(wait=True,cancel_futures=True)
                for future in active:
                    if not future.cancelled() and future.exception() is None:
                        generator=future.result()
                        if generator is not None:generators.append(generator)
                for generator in generators:generator.close()
                self.update(row,processingJobs=0)
        meta['savedCover']=cover.name if cover else None;write(directory/'剧集资料.json',meta)
        failed=[i for i in row['items'] if i['status']=='failed']
        self.update(row,status='failed' if failed else 'completed',bytesPerSecond=None,etaSeconds=None,stage=f'已入库{row["done"]}/{len(row["episodes"])}集，{len(failed)}集失败；可继续重试失败集' if failed else (f'所选{len(row["episodes"])}集已处理并入库' if row['video'] else '资料已保存（未下载视频）'))
    def run(self):
        while True:
            with self.lock:
                if self.stopping or self.h.ACCESS.snapshot().get('paused'):self.worker=None;return
                row=next((r for r in self.rows if r['status']=='queued'),None)
                if not row:self.worker=None;return
                row.update(status='running',stage='读取剧集资料');self.save();event=self.events.setdefault(row['id'],threading.Event())
            started=time.monotonic();elapsed=row.get('elapsedSeconds',0)
            try:self.process(row,event)
            except self.h.Cancelled:self.update(row,status='cancelled',stage='已停止，已保存的完整文件保留')
            except self.h.SourceLimited as e:self.update(row,status='limited',stage=str(e))
            except Exception as e:
                message=str(e) if isinstance(e,ValueError) else '采集失败，请检查网络、磁盘空间或保存权限'
                self.update(row,status='failed',failedStage=row.get('stage',''),stage=message[:220])
                for item in row['items']:
                    if item['status']=='running':item.update(status='failed',error=message[:220])
            finally:
                with self.lock:
                    row['elapsedSeconds']=round(elapsed+time.monotonic()-started,3)
                    if row['status']!='running':
                        for item in row['items']:
                            if item['status']=='running':item.update(status='pending',stage='等待继续',bytesPerSecond=None,etaSeconds=None)
                    if row['status'] in ('completed','failed','cancelled'):self.events.pop(row['id'],None)
                    self.save()
    def shutdown(self):
        with self.lock:
            self.stopping=True
            for e in self.events.values():e.set()
            self.save()
