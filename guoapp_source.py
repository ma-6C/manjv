"""Bridge the pinned guoapp native core into the existing import workspace."""
from __future__ import annotations
import copy,ctypes,hashlib,json,os,re,shutil,subprocess,threading,time,urllib.parse,uuid
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError as FutureTimeout
from pathlib import Path
import hongguo_source as web
import official_hongguo_share as official_share
import unicodedata
from source_imports import ImportManager

PREFIX='guoapp://hongguo/'

def is_native(value):return isinstance(value,str) and value.startswith(PREFIX)

def site_url(value):
    if not is_native(value):return web.site_url(value)
    parsed=urllib.parse.urlsplit(value)
    if parsed.username or parsed.password or parsed.port or parsed.fragment:raise ValueError('原生目录地址无效')
    query=urllib.parse.parse_qs(parsed.query)
    if parsed.path=='/catalog':
        page=query.get('page',['1'])[0]
        if not page.isdigit() or not 1<=int(page)<=500:raise ValueError('页码应在1至500之间')
        search=query.get('query',[''])[0].strip()[:120]
        category=query.get('category',[''])[0]
        if category not in ('','short_play','comic_series','ai_series'):raise ValueError('原生分类无效')
        return PREFIX+'catalog?'+urllib.parse.urlencode({'page':int(page),'query':search,'category':category})
    if re.fullmatch(r'/detail/\d{5,30}',parsed.path) and not parsed.query:return PREFIX+parsed.path.lstrip('/')
    raise ValueError('请选择原生目录中的剧集')

class Core:
    def __init__(self,data):
        self.root=Path(__file__).resolve().parent/'engines'/'guoapp-core'
        self.data=Path(data)/'guoapp-core';self.lock=threading.RLock();self.library=None
        self.cover_slots=threading.BoundedSemaphore(4);self.cover_locks={}
        self.download_settings_lock=threading.Lock();self.download_concurrency=None
    def status(self):
        try:
            manifest=json.loads((self.root/'manifest.json').read_text('utf-8'))
            return {'available':(self.root/'duanju_core.dll').is_file(),'version':manifest['version'],'sourceCommit':manifest['sourceCommit']}
        except (OSError,ValueError,KeyError):return {'available':False,'message':'原生红果组件尚未准备好'}
    def load(self):
        with self.lock:
            if self.library:return
            try:
                manifest=json.loads((self.root/'manifest.json').read_text('utf-8'))
                dll=self.root/'duanju_core.dll'
                with dll.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
                if digest!=manifest['sha256']:raise ValueError('原生红果组件校验失败，请重新部署组件')
                library=ctypes.CDLL(str(dll))
                library.DuanjuRequest.argtypes=[ctypes.c_char_p];library.DuanjuRequest.restype=ctypes.c_void_p
                library.DuanjuFree.argtypes=[ctypes.c_void_p];library.DuanjuFree.restype=None
            except (OSError,KeyError):raise ValueError('原生红果组件无法加载，请检查完整的组件目录') from None
            self.data.mkdir(parents=True,exist_ok=True)
            self.library=library
            try:self.call({'action':'initialize','directory':str(self.data)})
            except Exception:self.library=None;raise
    def call(self,payload):
        if self.library is None:self.load()
        pointer=self.library.DuanjuRequest(json.dumps(payload,ensure_ascii=False).encode('utf-8'))
        if not pointer:raise ValueError('原生红果核心未返回结果')
        try:result=json.loads(ctypes.string_at(pointer).decode('utf-8'))
        finally:self.library.DuanjuFree(pointer)
        if not result.get('ok'):raise ValueError(str(result.get('error') or '原生来源请求失败')[:220])
        return result.get('data')
    def configure_downloads(self,concurrency):
        if type(concurrency) is not int or concurrency not in (1,2,3,5):raise ValueError('原生下载并发应为1、2、3或5集')
        with self.download_settings_lock:
            if self.download_concurrency==concurrency:return
            settings=self.call({'action':'resourceSettings'})
            if 'proxyUrl' not in settings and 'proxyURL' in settings:settings['proxyUrl']=settings['proxyURL']
            allowed=('proxyMode','proxyUrl','catalogConcurrency','catalogIntervalMs','downloadConcurrency','downloadBySource')
            settings={key:value for key,value in settings.items() if key in allowed}
            if settings.get('downloadConcurrency')!=concurrency:
                settings['downloadConcurrency']=concurrency
                self.call({'action':'saveResourceSettings','settings':settings})
            self.download_concurrency=concurrency
    def cover(self,drama):
        with self.lock:lock=self.cover_locks.setdefault(drama['id'],threading.Lock())
        with lock,self.cover_slots:
            result=self.call({'action':'cover','drama':drama})
            source=self.cover_path(result.get('path',''))
            if result.get('heic'):
                fingerprint=hashlib.sha256((str(source)+str(source.stat().st_mtime_ns)+str(source.stat().st_size)).encode()).hexdigest()
                target=source.parent/'compatible-manju'/(fingerprint+'.jpg')
                if not target.is_file():
                    prepared=self.call({'action':'prepareCover','drama':drama})
                    if not prepared.get('heic'):source=self.cover_path(prepared.get('path',''))
                    else:
                        intermediate=self.cover_path(prepared.get('input',''))
                        target.parent.mkdir(exist_ok=True)
                        temporary=target.with_suffix('.'+uuid.uuid4().hex+'.part')
                        filters=[prepared.get('filters',''),"scale=w='min(800,iw)':h='min(800,ih)':force_original_aspect_ratio=decrease"]
                        import imageio_ffmpeg
                        command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-nostdin','-n','-max_alloc','67108864','-threads','1','-f','hevc','-i',str(intermediate),'-frames:v','1','-an','-sn','-vf',','.join(f for f in filters if f),'-filter_threads','1','-threads','1','-c:v','mjpeg','-pix_fmt','yuvj420p','-q:v','3','-f','image2',str(temporary)]
                        try:
                            subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                            if not temporary.is_file() or temporary.stat().st_size>4*1024*1024 or web.image_extension(temporary.read_bytes()[:16])!='.jpg':raise ValueError('封面转换未生成有效图片')
                            temporary.replace(target)
                        except (subprocess.SubprocessError,OSError):raise ValueError('封面格式转换失败，请重新读取剧集') from None
                        finally:
                            temporary.unlink(missing_ok=True)
                            if intermediate!=source and intermediate.name.startswith('.decode-'):intermediate.unlink(missing_ok=True)
                if target.is_file():source=self.cover_path(str(target))
            data=source.read_bytes();ext=web.image_extension(data[:16])
            mime={'.jpg':'image/jpeg','.png':'image/png','.webp':'image/webp'}.get(ext)
            if not mime and data.startswith((b'GIF87a',b'GIF89a')):mime='image/gif'
            if not mime and len(data)>=12 and data[4:8]==b'ftyp' and data[8:12] in (b'avif',b'avis'):mime='image/avif'
            if not mime:raise ValueError('封面格式暂不支持，请重新读取剧集')
            if mime in ('image/gif','image/avif'):
                from PIL import Image
                import io
                try:
                    with Image.open(io.BytesIO(data)) as image:
                        if image.width*image.height>16000000:raise ValueError('封面像素过大')
                        image.thumbnail((800,800));output=io.BytesIO();image.convert('RGB').save(output,format='JPEG',quality=90)
                        data,mime=output.getvalue(),'image/jpeg'
                except OSError:raise ValueError('封面图片无法解码') from None
            return data,mime
    def cover_path(self,value):
        path=Path(value).resolve()
        if not path.is_relative_to((self.data/'covers-v1').resolve()) or not path.is_file() or not 0<path.stat().st_size<=20*1024*1024:raise ValueError('封面缓存路径或大小无效')
        return path

class Adapter:
    def __init__(self,core):self.core=core;self.media={};self.covers={};self.lock=threading.RLock();self.quality=0;self.segments=1
    def __getattr__(self,name):return getattr(web,name)
    site_url=staticmethod(site_url)
    def remember_cover(self,drama):
        sid=str(drama.get('sourceId') or drama['id'].rsplit(':',1)[-1])
        with self.lock:self.covers[sid]=copy.deepcopy(drama)
        return 'guoapp-cover://hongguo/'+sid
    def cover(self,sid):
        if not re.fullmatch(r'\d{5,30}',sid):raise ValueError('封面剧集ID无效')
        with self.lock:drama=copy.deepcopy(self.covers.get(sid))
        if not drama:raise ValueError('请先读取原生目录或剧集详情')
        return self.core.cover(drama)
    @staticmethod
    def valid_episode_entry(meta,entry):
        if meta.get('platform')=='guoapp_hongguo':
            chapter=entry.get('nativeChapter') or {}
            return (entry.get('playerUrl')==meta['url']+'/episode/'+str(entry.get('number'))
                and bool(re.fullmatch(r'hongguo:'+re.escape(meta['seriesId'])+r':\d{5,30}',str(chapter.get('id',''))))
                and str(chapter.get('currentEpisode'))==str(entry.get('number')) and not chapter.get('vip'))
        return bool(re.fullmatch(r'https://hongguoduanju\.com/player/'+re.escape(meta['seriesId'])+r'(?:/\d+)?',entry.get('playerUrl','')))
    def resolve_episode(self,meta,n,entry,event):
        if event.is_set():raise web.Cancelled()
        chapter=entry.get('nativeChapter') or {}
        if not self.valid_episode_entry(meta,entry):raise ValueError('原生分集资料无效，请重新读取剧集')
        episode_id=str(chapter['id']).rsplit(':',1)[-1]
        if not re.fullmatch(r'\d+',episode_id):raise ValueError('原生来源未提供可核对的视频ID')
        token='guoapp-media:'+uuid.uuid4().hex
        with self.lock:
            if len(self.media)>=16:raise ValueError('原生下载任务繁忙，请等待当前任务完成')
            self.media[token]=(copy.deepcopy(meta['nativeDrama']),copy.deepcopy(chapter),n,self.quality,self.segments)
        return {'url':token,'episodeId':episode_id,'uploadDate':None}
    def download(self,url,path,cancel,progress,image=False):
        if url.startswith('guoapp-cover://hongguo/'):
            if not image:raise ValueError('封面不能用作视频来源')
            if cancel.is_set():raise web.Cancelled()
            data,_=self.cover(url.rsplit('/',1)[-1])
            if cancel.is_set():raise web.Cancelled()
            Path(path).write_bytes(data);progress(len(data),len(data));return
        if not url.startswith('guoapp-media:'):return web.download(url,path,cancel,progress,image)
        plan=self.fetch_media(url,cancel,progress)
        self.materialize_media(plan,path,cancel)
    def fetch_media(self,url,cancel,progress):
        with self.lock:entry=self.media.pop(url,None)
        if not entry:raise ValueError('原生下载会话失效，请继续任务重新获取')
        drama,chapter,index,quality,segments=entry
        job_id=hashlib.sha256((drama['id']+'\0'+str(index)).encode()).hexdigest()[:32]
        self.core.call({'action':'enqueueDownloads','drama':drama,'entries':[{'chapter':chapter,'index':index}],'force':True,'quality':quality,'segments':segments})
        deadline=time.monotonic()+1800
        try:
            while True:
                if cancel.is_set():raise web.Cancelled()
                jobs=self.core.call({'action':'downloads'})['jobs']
                job=next((row for row in jobs if row['id']==job_id),None)
                if not job:raise ValueError('原生下载任务未建立，请重新读取剧集')
                progress(job.get('bytes',0),job.get('total') or None)
                if job['state']=='completed':break
                if job['state']=='failed':
                    message=str(job.get('error') or '原生下载失败')[:180]
                    limited=re.search(r'HTTP (403|429)',message)
                    if limited:
                        retry=re.search(r'Retry-After=(\d+)',message)
                        web.ACCESS.pause(int(limited.group(1)),retry.group(1) if retry else None)
                        raise web.SourceLimited('来源要求等待，下载已暂停，已完成文件保留')
                    raise ValueError('来源页面读取失败：'+message)
                if job['state']=='paused':self.core.call({'action':'controlDownloads','jobId':job_id,'command':'resume'})
                if time.monotonic()>deadline:raise ValueError('下载连接中断：原生下载超时，可继续重试')
                cancel.wait(.35)
            plan=self.core.call({'action':'localPlayback','drama':drama,'index':index})
            source=Path(plan.get('url','')).resolve()
            if not plan.get('local') or not source.is_relative_to((self.core.data/'downloads').resolve()) or not source.is_file():raise ValueError('原生下载文件路径无效')
            progress(source.stat().st_size,source.stat().st_size)
            plan['transferMode']=job.get('transferMode','single')
            return plan
        except BaseException:
            try:self.core.call({'action':'controlDownloads','jobId':job_id,'command':'pause'})
            except ValueError:pass
            raise
    def materialize_media(self,plan,path,cancel):
        if cancel.is_set():raise web.Cancelled()
        source=Path(plan.get('url','')).resolve()
        if not plan.get('local') or not source.is_relative_to((self.core.data/'downloads').resolve()) or not source.is_file():raise ValueError('原生下载文件路径无效')
        key=plan.get('decryptionKey')
        if key:
            if not re.fullmatch(r'[0-9a-fA-F]{32}',key):raise ValueError('原生来源返回的视频播放参数无效')
            import imageio_ffmpeg
            command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-nostdin','-n','-decryption_key',key,'-i',str(source),'-map','0:v:0','-map','0:a?','-c','copy','-movflags','+faststart','-f','mp4',str(path)]
            process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                while process.poll() is None:
                    if cancel.wait(.2):raise web.Cancelled()
                if process.returncode:raise ValueError('视频校验失败：原生下载文件无法转为可剪辑MP4')
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
        else:
            with source.open('rb') as src,Path(path).open('xb') as dest:
                while chunk:=src.read(1024*1024):
                    if cancel.is_set():raise web.Cancelled()
                    dest.write(chunk)

class Manager(ImportManager):
    def __init__(self,data,import_video,probe):
        self.core=Core(data);self.dramas={};self.native_cache=OrderedDict();self.native_flights={}
        super().__init__(data,import_video,probe,Adapter(self.core))
    def cover(self,sid,platform=''):
        if platform=='guoapp_hongguo':return self.h.cover(sid)
        if platform not in ('','hongguo_web'):raise ValueError('封面来源无效')
        return super().cover(sid)
    def resolve(self,value,refresh=False,cancel=None):
        if official_share.extract_url(value):return self.resolve_share(value,refresh,cancel)
        if not is_native(value):return super().resolve(value,refresh,cancel)
        url=site_url(value);now=time.monotonic();begun=time.perf_counter();ttl=60 if '/catalog?' in url else 300
        if cancel and cancel.is_set():raise web.Cancelled()
        with self.lock:
            cached=self.native_cache.get(url)
            if cached and not refresh and now-cached[0]<ttl:
                self.native_cache.move_to_end(url)
                result=copy.deepcopy(cached[1]);result.update(cacheHit=True,lookupMilliseconds=round((time.perf_counter()-begun)*1000,2));return result
            future=self.native_flights.get(url);owner=future is None
            if owner:future=Future();self.native_flights[url]=future
        if not owner:
            while True:
                if cancel and cancel.is_set():raise web.Cancelled()
                try:result=copy.deepcopy(future.result(timeout=.1));break
                except FutureTimeout:continue
            result.update(cacheHit=True,lookupMilliseconds=round((time.perf_counter()-begun)*1000,2));return result
        try:
            result=self.resolve_native(url,refresh,cancel)
            with self.lock:
                self.native_cache[url]=(time.monotonic(),copy.deepcopy(result));self.native_cache.move_to_end(url)
                while len(self.native_cache)>48:self.native_cache.popitem(last=False)
            future.set_result(copy.deepcopy(result))
            result.update(cacheHit=False,lookupMilliseconds=round((time.perf_counter()-begun)*1000,2));return result
        except BaseException as error:
            future.set_exception(error);raise
        finally:
            with self.lock:self.native_flights.pop(url,None)
    def process(self,row,event):
        if row.get('video') and is_native(row.get('url')):
            self.core.configure_downloads(row.get('downloadConcurrency',1))
            self.h.quality=row.get('downloadQuality',0);self.h.segments=2 if row.get('segmentedDownload',False) else 1
        return super().process(row,event)
    def resolve_share(self,value,refresh=False,cancel=None):
        if cancel and cancel.is_set():raise web.Cancelled()
        share=official_share.fetch(value)
        catalog=self.resolve(PREFIX+'catalog?'+urllib.parse.urlencode({'query':share['title'],'page':1}),refresh,cancel)
        normalize=lambda text:re.sub(r'\s+','',unicodedata.normalize('NFKC',text)).casefold()
        matches=[entry for entry in catalog['entries'] if normalize(entry['title'])==normalize(share['title'])]
        if len(matches)>1 and share.get('totalEpisodes'):
            matches=[entry for entry in matches if entry.get('totalEpisodes')==share['totalEpisodes']]
        if len(matches)==1:
            detail=self.resolve(matches[0]['url'],refresh,cancel)
            chapter=share.get('chapterId')
            if not chapter or any(str(entry.get('nativeChapter',{}).get('id','')).endswith(':'+chapter) for entry in detail['episodes']):
                detail['officialShare']={**share,'matched':True};detail['shareCatalog']=catalog
                return detail
        catalog['officialShare']={**share,'matched':False}
        catalog['warning']='已识别官方剧名“'+share['title']+'”，请从搜索结果中核对并选择对应剧集。'
        return catalog
    def resolve_native(self,value,refresh=False,cancel=None):
        url=site_url(value)
        if cancel and cancel.is_set():raise web.Cancelled()
        parsed=urllib.parse.urlsplit(url);query=urllib.parse.parse_qs(parsed.query)
        if parsed.path=='/catalog':
            page=int(query.get('page',['1'])[0]);category=query.get('category',[''])[0];search=query.get('query',[''])[0]
            result=self.core.call({'action':'catalog','source':'hongguo','page':page,'category':category,'query':search,'force':refresh})
            entries=[]
            for drama in result.get('items') or []:
                sid=str(drama.get('sourceId') or drama['id'].rsplit(':',1)[-1])
                if not re.fullmatch(r'\d{5,30}',sid):continue
                with self.lock:self.dramas[sid]=drama
                entries.append({'seriesId':sid,'url':PREFIX+'detail/'+sid,'title':drama['title'],'tags':drama.get('tags') or [],'totalEpisodes':drama.get('episodes'),'platform':'guoapp_hongguo','coverUrl':self.h.remember_cover(drama)})
            return {'kind':'catalog','platform':'guoapp_hongguo','url':url,'entries':entries,'lastPage':page+int(bool(result.get('hasMore'))),'warning':result.get('warning'),'query':search,'category':category}
        sid=parsed.path.rsplit('/',1)[-1]
        with self.lock:drama=copy.deepcopy(self.dramas.get(sid,{'id':'hongguo:'+sid,'source':'hongguo','sourceId':sid,'title':'红果剧集'}))
        detail=self.core.call({'action':'detail','drama':drama});drama=detail['drama'];chapters=detail.get('chapters') or []
        episodes=[];locked=[]
        for position,chapter in enumerate(chapters,1):
            try:number=int(chapter.get('currentEpisode') or position)
            except (TypeError,ValueError):raise ValueError('原生来源分集编号无效') from None
            if number<1 or number>100000 or any(e['number']==number for e in episodes):raise ValueError('原生来源分集编号重复或无效')
            if chapter.get('vip'):locked.append(number);continue
            episodes.append({'number':number,'playerUrl':url+'/episode/'+str(number),'status':'candidate','nativeChapter':chapter})
        return {'kind':'detail','platform':'guoapp_hongguo','seriesId':sid,'url':url,'title':drama['title'],'intro':drama.get('description',''),
            'coverUrl':self.h.remember_cover(drama),'tags':drama.get('tags') or [],'totalEpisodes':len(chapters),'webEpisodeLinks':len(episodes),'episodes':episodes,'lockedEpisodes':locked,
            'nativeDrama':drama,'heat':{'display':drama.get('heat')},'rating':None,'playCount':drama.get('views') or None,'publishedAt':drama.get('onlineDate') or None,
            'fetchedAt':time.time(),'downloadScope':'原生来源返回的可访问分集，下载校验后导入素材库','fieldStatus':{}}
