"""Real local HTTP transfers: ranges, validator changes, cancellation, retry and limits."""
from pathlib import Path
import os,sys,tempfile,threading,json,time,urllib.request,urllib.error,http.client,re
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.2';COMPILED='--compiled' in sys.argv
sys.dont_write_bytecode=True
if COMPILED:sys.path[:0]=[str(ROOT/'release'/VERSION/'漫剧工坊/_internal'),str(ROOT/'vendor')]
import hongguo_source as h
base=Path(tempfile.mkdtemp(prefix='download-engine-',dir=ROOT/'tmp'));DATA=bytes(range(256))*2048;NEW=bytes(reversed(range(256)))*2048
requests=[];mode='full';counts={};tag='"first"';cancel=threading.Event()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        global tag
        n=counts.get(mode,0);counts[mode]=n+1;r=self.headers.get('Range');requests.append({'mode':mode,'range':r,'ifRange':self.headers.get('If-Range')})
        if mode=='limited':self.send_response(429);self.send_header('Retry-After','2');self.end_headers();return
        if mode=='503' and n==0:self.send_response(503);self.end_headers();return
        data=NEW if mode=='changed' else DATA;etag='"new"' if mode=='changed' else tag
        offset=int(r.split('=')[1].split('-')[0]) if r else 0
        if offset>=len(data):self.send_response(416);self.end_headers();return
        partial=bool(r and mode!='ignore-range' and self.headers.get('If-Range')==etag)
        if not partial:offset=0
        content=data[offset:];self.send_response(206 if partial else 200)
        self.send_header('ETag',etag);self.send_header('Content-Length',str(2*1024**3 if mode=='oversize' else len(content)))
        if partial:self.send_header('Content-Range',f'bytes {offset+1 if mode=="bad-range" else offset}-{len(data)-1}/{len(data)}')
        self.end_headers()
        if mode=='oversize':return
        if (mode in ('cut-once','ignore-range') and n==0) or mode=='always-cut':
            self.wfile.write(content[:len(content)//2]);self.wfile.flush();self.close_connection=True;return
        try:
            for i in range(0,len(content),16384):
                self.wfile.write(content[i:i+16384]);self.wfile.flush()
                if mode=='cancel':time.sleep(.012)
        except (OSError,ConnectionError):pass
host=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=host.serve_forever,daemon=True).start();local=f'http://127.0.0.1:{host.server_address[1]}/media'
url='https://hongguoduanju.com/video/public/123456/360p.mp4';checks=[]
def response(url,image=False,cancel=None,extra_headers=None):
    try:return urllib.request.urlopen(urllib.request.Request(local,headers=extra_headers or {}),timeout=3)
    except urllib.error.HTTPError as e:
        if e.code==429:h.ACCESS.pause(429,e.headers.get('Retry-After'));raise h.SourceLimited('test source limited') from None
        if e.code==416:raise ValueError('来源网站返回 HTTP 416') from None
        raise
def check(name,value=True):assert value,name;checks.append(name)
def run(which,path=None,progress=None):
    global mode
    mode=which;cancel.clear();path=path or base/(which+'.download')
    try:h.download(url,path,cancel,progress or (lambda n,t:None))
    except Exception as e:
        print('TEST_CONTEXT',type(e.__context__).__name__,str(e.__context__),flush=True);raise
    return path
try:
    with patch.object(h,'response',response):
        p=run('full');check('full_transfer_exact_bytes',p.read_bytes()==DATA)
        p=run('cut-once');check('interrupted_connection_uses_range',p.read_bytes()==DATA and any(x['mode']=='cut-once' and x['range']=='bytes=262144-' for x in requests))
        p=run('ignore-range');check('server_200_restarts_without_appending',p.read_bytes()==DATA)
        mode='cancel';p=base/'pause.download'
        def pause(n,t):
            if 0<n<len(DATA):cancel.set()
        try:h.download(url,p,cancel,pause)
        except h.Cancelled:pass
        partial=p.with_suffix('.download.part');state=partial.with_suffix('.part.json')
        check('cancel_preserves_partial_and_validator',partial.exists() and state.exists() and 0<partial.stat().st_size<len(DATA))
        saved=json.loads(state.read_text('utf-8'));check('resume_metadata_does_not_store_resource_url',url not in state.read_text('utf-8') and saved['etag']==tag)
        old=partial.stat().st_size;p=run('full',p);check('resume_after_pause_keeps_exact_bytes',p.read_bytes()==DATA and requests[-1]['range']==f'bytes={old}-')
        mode='cancel';cancel.clear();p=base/'change.download'
        try:h.download(url,p,cancel,pause)
        except h.Cancelled:pass
        p=run('changed',p);check('changed_etag_restarts_safely',p.read_bytes()==NEW)
        p=run('503');check('transient_503_retries_once',p.read_bytes()==DATA and counts['503']==2)
        mode='limited'
        try:h.download(url,base/'limited.download',cancel,lambda n,t:None)
        except h.SourceLimited:pass
        check('429_pauses_without_retry',counts['limited']==1 and h.ACCESS.snapshot()['paused'])
        h.ACCESS.control={}
        mode='bad-range';p=base/'bad.download';part=p.with_suffix('.download.part');part.write_bytes(DATA[:100]);part.with_suffix('.part.json').write_text(json.dumps({'identity':h.hashlib.sha256(url.encode()).hexdigest(),'etag':tag}),'utf-8')
        try:h.download(url,p,cancel,lambda n,t:None)
        except ValueError:pass
        else:raise AssertionError('bad range accepted')
        check('mismatched_content_range_rejected',not p.exists() and part.read_bytes()==DATA[:100])
        mode='oversize'
        try:h.download(url,base/'oversize.download',cancel,lambda n,t:None)
        except ValueError:pass
        else:raise AssertionError('oversize accepted')
        check('oversize_not_promoted',not (base/'oversize.download').exists())
        p=base/'orphan.download';p.with_suffix('.download.part').write_bytes(b'old unknown partial');run('full',p);check('untracked_partial_replaced_safely',p.read_bytes()==DATA)
        mode='always-cut';p=base/'retry.download'
        try:h.download(url,p,cancel,lambda n,t:None)
        except ValueError:pass
        else:raise AssertionError('incomplete transfer accepted')
        check('bounded_retries_preserve_unfinished_file',counts['always-cut']==3 and not p.exists() and p.with_suffix('.download.part').exists())
    public='https://hongguoduanju.com/video/public/123456/360p.mp4'
    html='<html><script type="application/ld+json">'+json.dumps({'@type':'VideoObject','contentUrl':public})+'</script><script type="application/ld+json">'+json.dumps({'@type':'TVEpisode','episodeNumber':2,'url':'https://hongguoduanju.com/player/123456/234567'})+'</script><video src="'+public+'"></video>'
    class Streaming:
        def __init__(self):self.calls=0
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read1(self,n):
            self.calls+=1
            if self.calls>1:raise TimeoutError('unrelated page footer never completes')
            return html.encode()
    stream=Streaming()
    with patch.object(h,'response',return_value=stream):parsed=h.fetch_html('https://hongguoduanju.com/player/123456/234567')
    check('verified_player_does_not_wait_for_streaming_footer',stream.calls==1 and h.parse_player(parsed,'123456',2)['episodeId']=='123456')
    def episode_html(n,vid):
        route=f'https://hongguoduanju.com/player/123456/{vid}'
        ep={'@type':'TVEpisode','episodeNumber':n,'url':route,'video':{'@id':route+'#video'}}
        video={'@type':'VideoObject','@id':route+'#video','contentUrl':f'https://hongguoduanju.com/video/public/{vid}/360p.mp4'}
        return ''.join('<script type="application/ld+json">'+json.dumps(x)+'</script>' for x in [ep,video])+'<video src="'+video['contentUrl']+'"></video>'
    class Multiple(Streaming):
        def read1(self,n):
            self.calls+=1
            if self.calls==1:return episode_html(1,'111111').encode()
            if self.calls==2:return episode_html(2,'222222').encode()
            raise TimeoutError('footer pending')
    stream=Multiple()
    with patch.object(h,'response',return_value=stream):parsed=h.fetch_html('https://hongguoduanju.com/player/123456/222222',expected_episode=2)
    check('streaming_recommendation_cannot_replace_selected_episode',stream.calls==2 and h.parse_player(parsed,'123456',2,'https://hongguoduanju.com/player/123456/222222')['episodeId']=='222222')
    report={'version':VERSION,'compiled':COMPILED,'passed':len(checks),'checks':checks,'localRealHttp':True,'externalNetwork':False,'base':str(base)}
    (ROOT/('tmp/download-engine-compiled.json' if COMPILED else 'tmp/download-engine-source.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
finally:host.shutdown();host.server_close()
