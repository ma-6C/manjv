"""Isolated acceptance host with explicitly simulated cloud responses; never bundled."""
from pathlib import Path
import base64,io,json,os,shutil,sys,threading,urllib.parse
import server
import ai_providers as ai
import media_download
from test_workflow_host import TestHandler
BASE=Path(os.environ['MANJU_DATA']).parent;FIXTURE=BASE/'fixtures';FIXTURE.mkdir(parents=True,exist_ok=True)
SOURCE=FIXTURE/'原始样片';SOURCE.mkdir(exist_ok=True);VIDEO=SOURCE/'01.mp4'
if not VIDEO.exists():server.ff(['-f','lavfi','-i','testsrc2=s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-pix_fmt','yuv420p',str(VIDEO)])
(SOURCE/'简介.txt').write_text('小猫和伙伴寻找丢失的月光，最终一起回到家。','utf-8')
from PIL import Image
ref=FIXTURE/'参考图.png';Image.new('RGB',(320,180),'#6761ba').save(ref)
buf=io.BytesIO();Image.new('RGB',(512,512),'#afa1dc').save(buf,'PNG');png=base64.b64encode(buf.getvalue()).decode()
LOCK=threading.RLock();JOURNAL=BASE/'mock-cloud.json'
def read():return json.loads(JOURNAL.read_text('utf-8')) if JOURNAL.exists() else {'requests':[],'created':[],'textCalls':0,'polls':{}}
def request(url,payload=None,key='',protocol='chat',**kwargs):
    if urllib.parse.urlsplit(url).hostname!='mock.invalid':raise AssertionError('Unexpected external request blocked in isolated acceptance')
    with LOCK:
        data=read();data['requests'].append({'path':urllib.parse.urlsplit(url).path,'model':payload.get('model') if payload else None,'account':'primary' if key=='fixture-secret-primary' else 'other'})
        try:
            if url.endswith('/models'):return {'data':[{'id':'fixture-text'},{'id':'fixture-image'}]}
            if url.endswith('/chat/completions'):
                if key=='fixture-secret-primary':raise ai.ProviderError('fixture rate limit','RateLimit',429)
                data['textCalls']+=1;n=data['textCalls'];title=['月光守护之约','星河寻光之旅','晨曦归家之路'][n%3]
                return {'model':'fixture-text','choices':[{'message':{'content':json.dumps({'title':title,'synopsis':f'第{n}次改写：小猫与伙伴踏上寻找月光的旅途，最后一同回家。'},ensure_ascii=False)}}],'usage':{'total_tokens':20}}
            if '/images/generations' in url:return {'data':[{'b64_json':png}]}
            if url.endswith('/video/clear'):return {'task_id':'fixture-subtitle','status':'running'}
            if url.endswith('/video/status'):return {'status':'completed','video_url':'https://cdn.mock.invalid/result.mp4'}
            raise AssertionError('Unexpected fixture protocol')
        finally:JOURNAL.write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
def download(url,target,cancel,**kwargs):
    if url!='https://cdn.mock.invalid/result.mp4':raise AssertionError('Unexpected fixture media URL')
    if cancel.is_set():raise InterruptedError('fixture download paused')
    shutil.copy2(VIDEO,target)
ai.request_json=request;media_download.download=download
port=int(sys.argv[1]);meta={'url':f'http://127.0.0.1:{port}','base':str(BASE),'source':str(SOURCE),'reference':str(ref),'simulation':True}
(BASE/'service.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),'utf-8')
server.ThreadingHTTPServer(('127.0.0.1',port),TestHandler).serve_forever()
