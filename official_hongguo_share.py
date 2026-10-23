"""Read public Hongguo share metadata without requesting media or app credentials."""
from __future__ import annotations
import json,re,urllib.error,urllib.parse,urllib.request
from html.parser import HTMLParser

HOST='novelquickapp.com'
LIMIT=1024*1024

def extract_url(value):
    if not isinstance(value,str) or len(value)>8000:return None
    for candidate in re.findall(r'https?://[^\s<>"，。]+',value):
        candidate=candidate.rstrip('.,;!！；)）]】')
        try:parsed=urllib.parse.urlsplit(candidate)
        except ValueError:continue
        if parsed.hostname!=HOST:continue
        checked_url(candidate)
        if re.fullmatch(r'/s/[A-Za-z0-9_-]{4,80}/?',parsed.path):
            return 'https://'+HOST+parsed.path.rstrip('/')+'/'
        if parsed.path=='/hongguo/ug/pages/video-animation-share':
            return urllib.parse.urlunsplit(('https',HOST,parsed.path,parsed.query,''))
        raise ValueError('请粘贴完整的红果官方分享链接')
    return None

def checked_url(value):
    try:parsed=urllib.parse.urlsplit(value);port=parsed.port
    except ValueError:raise ValueError('官方分享链接格式无效') from None
    if parsed.scheme!='https' or parsed.hostname!=HOST or parsed.username or parsed.password or port not in (None,443):raise ValueError('仅支持HTTPS红果官方分享页面')
    if not (re.fullmatch(r'/s/[A-Za-z0-9_-]{4,80}/?',parsed.path) or parsed.path=='/hongguo/ug/pages/video-animation-share'):
        raise ValueError('官方分享跳转到了不支持的页面')
    return value

class ShareRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections=6
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        checked_url(newurl)
        return super().redirect_request(request,fp,code,msg,headers,newurl)

class ShareParser(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.metadata=None
    def handle_starttag(self,tag,attrs):
        if tag!='script' or self.metadata:return
        value=dict(attrs).get('data-fn-args','')
        if not value or len(value)>LIMIT:return
        try:arguments=json.loads(value)
        except (ValueError,RecursionError):return
        if not isinstance(arguments,list) or len(arguments)<3 or arguments[0]!='video-animation-share_page' or arguments[1]!='pageData':return
        payload=arguments[2]
        if not isinstance(payload,dict) or not isinstance(payload.get('series_data'),dict):return
        series=payload['series_data'];title=series.get('title')
        if not isinstance(title,str) or not title.strip() or len(title)>300:return
        count=series.get('serial_count')
        try:count=int(count)
        except (ValueError,TypeError):count=None
        if count is not None and not 1<=count<=100000:count=None
        chapter=str(payload.get('used_chapter_id') or '')
        order=payload.get('chapter_order')
        self.metadata={'title':title.strip(),'totalEpisodes':count,'chapterId':chapter if re.fullmatch(r'\d{5,30}',chapter) else None,
            'sharedEpisode':order if type(order) is int and 1<=order<=100000 else None}

def parse_page(text):
    parser=ShareParser();parser.feed(text)
    if not parser.metadata:raise ValueError('官方分享页暂未返回剧名，请确认链接仍有效或稍后重试')
    return parser.metadata

def fetch(value):
    url=extract_url(value)
    if not url:raise ValueError('未识别到红果官方分享链接')
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36','Accept':'text/html'})
    try:
        with urllib.request.build_opener(ShareRedirect()).open(request,timeout=20) as response:
            checked_url(response.url)
            if response.headers.get_content_type()!='text/html':raise ValueError('官方分享页未返回网页内容')
            data=response.read(LIMIT+1)
            if len(data)>LIMIT:raise ValueError('官方分享页内容过大')
            text=data.decode(response.headers.get_content_charset() or 'utf-8','replace')
    except urllib.error.HTTPError as error:raise ValueError('官方分享页暂时无法访问（HTTP '+str(error.code)+'）') from None
    except (urllib.error.URLError,TimeoutError,OSError):raise ValueError('官方分享页连接失败，请检查网络后重试') from None
    result=parse_page(text)
    if '/s/' in urllib.parse.urlsplit(url).path:result['url']=url
    return result
