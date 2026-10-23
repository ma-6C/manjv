"""Public Hongguo catalogue adapter. No app credentials or private playback APIs."""
from __future__ import annotations
import copy
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import hashlib
from email.utils import parsedate_to_datetime
import episode_selection
from html.parser import HTMLParser
from pathlib import Path

BASE = 'https://hongguoduanju.com'
CATALOG = BASE + '/category/comic-drama'
VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

class SourceLimited(ValueError): pass
class SourceLocked(ValueError): pass

class Access:
    def __init__(self,interval=2):
        self.flight=threading.BoundedSemaphore(2);self.lock=threading.RLock();self.next_at=0;self.path=None;self.control={};self.interval=interval
    def configure(self,data):
        with self.lock:
            if self.path:return
            self.path=Path(data)/'source-access.json'
            try:self.control=json.loads(self.path.read_text('utf-8'))
            except (OSError,ValueError):self.control={}
    def snapshot(self):
        with self.lock:return copy.deepcopy(self.control)
    def pause(self,code,retry=None):
        until=None
        if retry:
            try:until=time.time()+max(0,int(retry))
            except (TypeError,ValueError):
                try:until=parsedate_to_datetime(retry).timestamp()
                except (TypeError,ValueError,OverflowError):pass
        with self.lock:
            self.control={'paused':True,'code':code,'retryAt':until,'message':'来源限制访问，采集已暂停；请核对后继续'}
            self.save()
    def save(self):
        if self.path:
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(self.control),'utf-8');temp.replace(self.path)
    def resume(self):
        with self.lock:
            if self.control.get('retryAt',0) and self.control['retryAt']>time.time():raise ValueError('服务器要求的等待时间尚未结束')
            self.control={};self.save()
    def enter(self,cancel=None):
        deadline=time.monotonic()+30
        while not self.flight.acquire(timeout=.1):
            if cancel and cancel.is_set():raise Cancelled()
            if time.monotonic()>deadline:raise ValueError('来源连接忙，请等待当前请求完成后再试')
        try:
            if self.snapshot().get('paused'):raise SourceLimited('来源访问已暂停，请在采集页核对并继续')
            # Reserve starts across both transfers. Overlapping response bodies must
            # not turn into overlapping bursts of new requests.
            while True:
                if cancel and cancel.is_set():raise Cancelled()
                with self.lock:
                    if self.control.get('paused'):raise SourceLimited('来源访问已暂停，请在采集页核对并继续')
                    wait=max(0,self.next_at-time.monotonic())
                    if not wait:
                        self.next_at=time.monotonic()+self.interval;break
                if cancel:
                    if cancel.wait(min(wait,.1)):raise Cancelled()
                else:time.sleep(min(wait,.1))
        except BaseException:self.flight.release();raise

ACCESS=Access()

class Response:
    def __init__(self,r):self.raw=r;self.headers=r.headers;self.status=getattr(r,'status',200)
    def read(self,n=-1):return self.raw.read(n)
    def read1(self,n):return self.raw.read1(n) if hasattr(self.raw,'read1') else self.raw.read(n)
    def __enter__(self):return self
    def __exit__(self,*args):
        try:self.raw.close()
        finally:ACCESS.flight.release()

class Node:
    def __init__(self, tag='', attrs=None):
        self.tag, self.attrs, self.parts = tag, dict(attrs or []), []
    def text(self):
        return ''.join(p.text() if isinstance(p, Node) else p for p in self.parts)
    def all(self, tag=None, cls=None):
        for p in self.parts:
            if isinstance(p, Node):
                if (not tag or p.tag == tag) and (not cls or any(c.startswith(cls) for c in p.attrs.get('class','').split())):
                    yield p
                yield from p.all(tag, cls)

class DOM(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node(); self.stack = [self.root]; self.feed(html)
    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs); self.stack[-1].parts.append(n)
        if tag not in VOID: self.stack.append(n)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]; break
    def handle_data(self, data): self.stack[-1].parts.append(data)

def site_url(value):
    if not isinstance(value,str) or len(value)>8000: raise ValueError('请输入红果网站列表或详情链接')
    matches = re.findall(r'https://[^\s<>"，。]+', value)
    u = urllib.parse.urlsplit(matches[0] if matches else value.strip())
    if u.scheme!='https' or u.hostname!='hongguoduanju.com' or u.username or u.password or u.port not in (None,443):
        raise ValueError('当前支持 hongguoduanju.com 的漫剧列表、详情和播放器链接')
    if u.path=='/category/comic-drama':
        q=urllib.parse.parse_qs(u.query); page=q.get('page',['1'])[0]
        if not page.isdigit() or not 1<=int(page)<=500: raise ValueError('页码应在 1 至 500 之间')
        return CATALOG + ('?page='+str(int(page)) if int(page)>1 else '')
    sid = urllib.parse.parse_qs(u.query).get('series_id',[''])[0] if u.path=='/detail' else ''
    if re.fullmatch(r'/player/\d{5,30}',u.path): sid=u.path.rsplit('/',1)[1]
    if not re.fullmatch(r'\d{5,30}',sid): raise ValueError('链接中缺少有效剧集 ID')
    return BASE+'/detail?series_id='+sid

def resource_url(url, image=False):
    u=urllib.parse.urlsplit(url)
    host=u.hostname or ''
    allowed=(host.endswith('.byteimg.com') and image) or (host=='hongguoduanju.com')
    if u.scheme!='https' or not allowed or u.username or u.password or u.port not in (None,443):
        raise ValueError('来源页面提供了不支持的资源地址')
    return url

class Redirect(urllib.request.HTTPRedirectHandler):
    def __init__(self,image=False): self.image=image; self.count=0
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count+=1
        if self.count>4: raise ValueError('来源重定向过多')
        resource_url(newurl,self.image)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def response(url, image=False, cancel=None, extra_headers=None):
    resource_url(url,image)
    ACCESS.enter(cancel)
    try:
        headers={
            'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36',
            'Accept-Encoding':'identity'}
        headers.update(extra_headers or {})
        raw=urllib.request.build_opener(Redirect(image)).open(urllib.request.Request(url,headers=headers),timeout=30)
        return Response(raw)
    except urllib.error.HTTPError as e:
        ACCESS.flight.release()
        e.close()
        if e.code in (401,403,429) or e.headers.get('Retry-After'):
            ACCESS.pause(e.code,e.headers.get('Retry-After'));raise SourceLimited('来源返回 HTTP '+str(e.code)+'，同源采集队列已暂停') from None
        raise ValueError('来源网站返回 HTTP '+str(e.code)) from None
    except BaseException as e:
        ACCESS.flight.release()
        if isinstance(e,(OSError,urllib.error.URLError)):raise ValueError('连接来源网站失败或超时，请稍后重试') from None
        raise

def fetch_html(url,cancel=None,expected_episode=None):
    for attempt in range(3):
        if cancel and cancel.is_set():raise Cancelled()
        try:
            with response(url,cancel=cancel) as r:
                data=bytearray();player=re.fullmatch(r'/player/(\d+)(?:/\d+)?',urllib.parse.urlsplit(url).path)
                while True:
                    if cancel and cancel.is_set():raise Cancelled()
                    block=r.read1(65536)
                    if not block:break
                    data.extend(block)
                    if len(data)>6*1024*1024:raise ValueError('来源页面过大')
                    html=data.decode('utf-8-sig','replace')
                    if re.search(r'<title[^>]*>[^<]*(?:安全验证|访问受限|访问过于频繁|Access Denied|Verify)',html,re.I):
                        ACCESS.pause(403);raise SourceLimited('来源要求验证，采集队列已暂停')
                    # Streaming pages may keep recommendations pending after the actual player is ready.
                    # Stop only once public video, declared URL, series identity and episode identity agree.
                    if player and 'VideoObject' in html and 'TVEpisode' in html and '<video' in html:
                        try:
                            dom=DOM(html).root
                            for episode in structured(dom):
                                if episode.get('@type')!='TVEpisode':continue
                                number=expected_episode if expected_episode is not None else episode.get('episodeNumber')
                                if type(number) is int and number>0:parse_player(html,player[1],number,url);return html
                        except ValueError as e:
                            if isinstance(e,SourceLocked):raise
                return data.decode('utf-8-sig')
        except (OSError,ValueError) as e:
            if isinstance(e,(SourceLimited,SourceLocked)):raise
            retry=isinstance(e,OSError) or '连接来源网站失败' in str(e) or any('HTTP '+str(code) in str(e) for code in (500,502,503,504))
            if not retry or attempt==2:raise ValueError('来源页面读取失败，请稍后重试') from None
            if cancel:
                if cancel.wait(2**attempt):raise Cancelled()
            else:time.sleep(2**attempt)

def first(root, tag=None, cls=None):
    return next(root.all(tag,cls),Node())

def parse_catalog(html,url=CATALOG):
    root=DOM(html).root; entries=[]; seen=set()
    for a in root.all('a','pc-card-'):
        try: detail=site_url(urllib.parse.urljoin(BASE,a.attrs.get('href','')))
        except ValueError: continue
        if '/detail?' not in detail or detail in seen: continue
        seen.add(detail)
        title=first(a,'p','pc-title-').text().strip()
        if not title: continue
        episode=first(a,'p','pc-episode-').text().strip()
        count=re.search(r'全(\d+)集',episode)
        entries.append({'title':title,'url':detail,'seriesId':urllib.parse.parse_qs(urllib.parse.urlsplit(detail).query)['series_id'][0],
            'totalEpisodes':int(count[1]) if count else None,
            'tags':[n.text().strip() for n in a.all('span','pc-tag-text-')]})
    if not entries: raise ValueError('未识别到剧集列表，网站结构可能已变化')
    pages=[int(n.text()) for n in root.all('a') if n.text().strip().isdigit() and 'page=' in n.attrs.get('href','')]
    current=int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('page',['1'])[0])
    return {'kind':'catalog','url':site_url(url),'entries':entries,'lastPage':max(pages+[current]),'fetchedAt':time.time()}

def structured(root):
    for n in root.all('script'):
        if n.attrs.get('type')=='application/ld+json':
            try: data=json.loads(n.text())
            except ValueError: continue
            if isinstance(data,dict):
                yield data
                for d in data.get('@graph',[]):
                    if isinstance(d,dict): yield d

def locked_episodes(root):
    """Only explicit lock markers; lack of a link by itself is not a lock."""
    numbers=set()
    for cell in root.all():
        classes=cell.attrs.get('class','').split()
        if not any(c.startswith(('pc-episode-item-','pc-episode-cell-')) or re.fullmatch(r'pc-episode-[A-Za-z0-9_]+',c) for c in classes):continue
        label=(first(cell,'div','pc-episode-cell-text-').text() or first(cell,'div','pc-episode-text-').text()).strip()
        if not label.isdigit():continue
        for node in [cell,*cell.all()]:
            classes=node.attrs.get('class','')
            hints=' '.join(str(node.attrs.get(k,'')) for k in ('aria-label','title','data-state','data-status','data-lucide'))
            if re.search(r'(?:^|[\s_-])lock(?:ed)?(?:$|[\s_-])',classes,re.I) or re.search(r'锁定|需解锁|已锁|\blocked\b|\block\b',hints,re.I):
                numbers.add(int(label));break
    return sorted(numbers)

def parse_detail(html,url):
    root=DOM(html).root
    series=next((d for d in structured(root) if d.get('@type')=='TVSeries'),None)
    if not series or not series.get('name'): raise ValueError('未识别到剧集详情，网站结构可能已变化')
    url=site_url(url); sid=urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['series_id'][0]
    heat=first(root,'span','pc-hero-heat-').text().strip()
    rating=first(root,'span','pc-hero-rating-text-').text().strip()
    # Visible numbered episode cells, not recommendations or comments.
    numbers=[int(n.text()) for n in root.all('div','pc-episode-cell-text-') if n.text().strip().isdigit()]
    links=set();episodes=[]
    for a in root.all('a','pc-episode-cell-'):
        href=a.attrs.get('href','')
        if re.fullmatch(r'/player/'+sid+r'(?:/\d+)?',href):
            label=first(a,'div','pc-episode-cell-text-').text().strip() or a.text().strip()
            if label.isdigit() and href not in links:
                episodes.append({'number':int(label),'playerUrl':BASE+href,'status':'candidate'})
            links.add(href)
    cover=series.get('image','')
    if not isinstance(cover,str): cover=''
    if cover:
        try: resource_url(cover,True)
        except ValueError: cover=''
    tags=[n.text().strip() for n in root.all('span','pc-hero-tag-text-') if not n.text().strip().startswith('短剧热播榜')]
    now=time.time()
    return {'kind':'detail','platform':'hongguo_web','seriesId':sid,'url':url,'title':str(series['name'])[:300],
        'intro':str(series.get('description',''))[:20000],'coverUrl':cover,'tags':list(dict.fromkeys(tags)),
        'totalEpisodes':max(numbers) if numbers else None,'webEpisodeLinks':len(links),
        'downloadScope':'只处理页面直接提供的公开播放入口，逐集核对视频与集序','episodes':episodes,'lockedEpisodes':locked_episodes(root),
        'heat':{'display':heat or None,'status':'success' if heat else 'not_provided','scope':'series','fetchedAt':now},
        'rating':rating or None,'playCount':None,'publishedAt':None,'fetchedAt':now,
        'firstEpisodeAvailable':('/player/'+sid) in links,
        'fieldStatus':{'playCount':'not_provided','publishedAt':'not_provided'}}

def parse_player(html,sid,number=1,player_url=None):
    root=DOM(html).root
    if number in locked_episodes(root):raise SourceLocked('剧集已锁定，当前来源未提供可访问的素材；请在平台核对授权或导出入口')
    data=list(structured(root));target=urllib.parse.urlsplit(player_url).path if player_url else None
    sources={urllib.parse.urljoin(BASE,n.attrs.get('src','')) for n in root.all('video')}
    episodes=[e for e in data if e.get('@type')=='TVEpisode' and e.get('episodeNumber')==number
              and re.fullmatch(r'/player/'+sid+r'(?:/\d+)?',urllib.parse.urlsplit(str(e.get('url',''))).path)
              and (not target or urllib.parse.urlsplit(str(e.get('url',''))).path==target)]
    if not episodes:raise ValueError('网页集序无法核对，未下载')
    for episode in episodes:
        reference=episode.get('video',{}).get('@id') if isinstance(episode.get('video'),dict) else None
        for obj in data:
            if obj.get('@type')!='VideoObject' or (reference and obj.get('@id')!=reference):continue
            src=obj.get('contentUrl','')
            if not isinstance(src,str) or src not in sources or not re.fullmatch(re.escape(BASE)+r'/video/public/\d+/(?:360|480|720|1080)p\.mp4',src):continue
            return {'url':src,'episodeId':src.split('/')[-2],'uploadDate':obj.get('uploadDate'),'duration':obj.get('duration'),'scope':f'网页第{number}集'}
    raise ValueError('当前网页未提供可验证的公开 MP4，请使用平台可导出的素材')

def resolve(value):
    url=site_url(value); html=fetch_html(url)
    return parse_catalog(html,url) if '/category/' in url else parse_detail(html,url)

def image_extension(header):
    return '.jpg' if header.startswith(b'\xff\xd8\xff') else '.png' if header.startswith(b'\x89PNG\r\n\x1a\n') else '.webp' if header[:4]==b'RIFF' and header[8:12]==b'WEBP' else None

class Cancelled(Exception): pass

def download(url,path,cancel,progress,image=False):
    import shutil,http.client
    path=Path(path);partial=path.with_suffix(path.suffix+'.part');state=partial.with_suffix(partial.suffix+'.json')
    limit=12*1024*1024 if image else 1024*1024*1024;identity=hashlib.sha256(url.encode()).hexdigest();started=time.monotonic()
    for attempt in range(3):
        if cancel.is_set():raise Cancelled()
        if ACCESS.snapshot().get('paused'):raise SourceLimited('来源访问暂停，已保留下载进度')
        try:
            try:saved=json.loads(state.read_text('utf-8'))
            except (OSError,ValueError):saved={}
            offset=partial.stat().st_size if partial.is_file() else 0
            validator=saved.get('etag') or saved.get('modified')
            if offset and (saved.get('identity')!=identity or not validator or offset>limit):
                partial.unlink();offset=0
            headers={'Range':f'bytes={offset}-','If-Range':validator} if offset else {}
            with response(url,image,cancel,headers) as r:
                raw=r.headers.get('Content-Length','');length=int(raw) if raw.isdigit() else None
                tag=r.headers.get('ETag');modified=r.headers.get('Last-Modified')
                if r.status==206:
                    part=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',r.headers.get('Content-Range',''))
                    if not part or int(part[1])!=offset or int(part[2])<offset or int(part[2])>=int(part[3]):raise ValueError('下载续传范围不一致，已停止以防文件损坏')
                    total=int(part[3])
                    if length is not None and length!=int(part[2])-offset+1:raise ValueError('下载续传长度不一致')
                    if offset and ((saved.get('etag') and tag!=saved['etag']) or (not saved.get('etag') and modified!=saved.get('modified'))):
                        partial.unlink(missing_ok=True);state.unlink(missing_ok=True);raise OSError('来源文件已更新，重新读取')
                elif r.status==200:offset=0;total=length
                else:raise ValueError('下载返回不支持的状态')
                if total is not None and total>limit:raise ValueError('下载文件超过大小上限')
                if total is not None and shutil.disk_usage(path.parent).free<max(0,total-offset)+64*1024**2:raise ValueError('磁盘空间不足，无法保存当前文件，请清理或更换保存位置')
                pending=state.with_suffix(state.suffix+'.tmp')
                pending.write_text(json.dumps({'identity':identity,'etag':tag if tag and not tag.startswith('W/') else None,'modified':modified,'totalBytes':total}),'utf-8');pending.replace(state)
                done=offset;progress(done,total);last=time.monotonic()
                with partial.open('ab' if offset else 'wb') as f:
                    while True:
                        if cancel.is_set():raise Cancelled()
                        if ACCESS.snapshot().get('paused'):raise SourceLimited('来源访问暂停，已保留下载进度')
                        if time.monotonic()-started>600:raise ValueError('单个文件下载超时，已保留可续传进度')
                        chunk=r.read1(256*1024)
                        if not chunk:break
                        done+=len(chunk)
                        if done>limit or (total is not None and done>total):raise ValueError('下载文件超过大小上限或声明长度')
                        f.write(chunk)
                        if time.monotonic()-last>=.2:progress(done,total);last=time.monotonic()
                progress(done,total)
                if not done or (total is not None and done!=total):raise OSError('下载中断，尝试恢复当前文件')
            if cancel.is_set():raise Cancelled()
            partial.replace(path)
            try:state.unlink(missing_ok=True)
            except OSError:pass
            return
        except (Cancelled,SourceLimited):raise
        except (OSError,urllib.error.URLError,http.client.HTTPException) as e:
            if attempt==2:raise ValueError('下载连接中断，多次重试后仍未完成；已保留可续传部分，请继续任务') from None
            if cancel.wait(2**attempt):raise Cancelled()
        except ValueError as e:
            if 'HTTP 416' in str(e) and offset:
                partial.unlink(missing_ok=True);state.unlink(missing_ok=True)
                if attempt<2:continue
            transient='连接来源网站失败' in str(e) or any('HTTP '+str(code) in str(e) for code in (500,502,503,504))
            if transient and attempt<2:
                if cancel.wait(2**attempt):raise Cancelled()
                continue
            raise

from source_imports import ImportManager
import sys
class Manager(ImportManager):
    def __init__(self,data,import_video,probe):
        super().__init__(data,import_video,probe,sys.modules[__name__])
