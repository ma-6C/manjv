"""Isolated native integration fixture; every video and image is synthetic."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,copy,hashlib,json,os,re,subprocess,sys,tempfile,threading,time,urllib.parse

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--compiled',action='store_true');p.add_argument('--version',default='v0.8.4');p.add_argument('--queue-scroll-fixture',action='store_true');args=p.parse_args()
DIST=ROOT/'release'/args.version/'漫剧工坊'
BASE=Path(tempfile.mkdtemp(prefix='native-fullseries-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True
sys.path[:0]=([str(DIST/'_internal')] if args.compiled else [])+[str(ROOT/'vendor')]
import server as s,local_session
if args.compiled:
    assert s.__file__.endswith('.pyd');sys.frozen=True;s.licensing.verify_distribution(DIST)
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    assert s.licensing.activate(s.DATA,token)['valid'];s.PUBLIC=DIST/'_internal/web'
from PIL import Image
import io

m=s.source_manager();settings={'proxyMode':'auto','proxyURL':'','catalogConcurrency':3,'catalogIntervalMs':250,'downloadConcurrency':2,'downloadBySource':False}
drama={'id':'hongguo:123456789','source':'hongguo','sourceId':'123456789','title':'全集下载验收（63集合成短片）','description':'受控接口、合成短片；不是源站下载结果。','episodes':63,'tags':['合成验收']}
chapters=[{'id':f'hongguo:123456789:{23000000+n}','source':'hongguo','title':f'第{n}集','currentEpisode':n,'videoUrl':f'fixture://{n}','vip':n in (58,61)} for n in range(1,64)]
template=m.core.data/'downloads'/'synthetic.mp4';template.parent.mkdir(parents=True,exist_ok=True)
subprocess.run([s.FFMPEG,'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x96:rate=12','-f','lavfi','-i','sine=frequency=440:sample_rate=44100','-t','0.5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(template)],check=True)
image=io.BytesIO();Image.new('RGB',(80,110),(107,74,216)).save(image,'JPEG');image_bytes=image.getvalue()
m.core.cover=lambda _: (image_bytes,'image/jpeg')
calls={};jobs={};gate=threading.RLock();settings_changes=[]

def fixture_call(request):
    action=request['action']
    if action=='catalog':
        query=request.get('query','')
        with gate:calls[query]=calls.get(query,0)+1
        time.sleep(.9 if query=='slow' else .18)
        if query=='fail':raise ValueError('受控搜索失败')
        result=copy.deepcopy(drama)
        if query:result['title']='搜索结果：'+query
        return {'items':[result],'hasMore':True}
    if action=='detail':return {'drama':copy.deepcopy(drama),'chapters':copy.deepcopy(chapters)}
    if action=='resourceSettings':return copy.deepcopy(settings)
    if action=='saveResourceSettings':
        with gate:settings.update(request['settings']);settings_changes.append(copy.deepcopy(settings))
        return copy.deepcopy(settings)
    if action=='enqueueDownloads':
        with gate:
            for entry in request['entries']:
                n=entry['index'];assert not chapters[n-1]['vip'];assert entry['chapter']['id']==chapters[n-1]['id']
                jid=hashlib.sha256((drama['id']+'\0'+str(n)).encode()).hexdigest()[:32]
                jobs[jid]={'id':jid,'state':'completed','bytes':template.stat().st_size,'total':template.stat().st_size,'index':n}
        return {'added':len(request['entries'])}
    if action=='downloads':
        with gate:return {'jobs':copy.deepcopy(list(jobs.values()))}
    if action=='localPlayback':
        time.sleep(.07)
        return {'local':True,'url':str(template),'decryptionKey':''}
    if action=='controlDownloads':return True
    raise ValueError('unexpected fixture action '+action)

m.core.call=fixture_call
checks=[];cache_url='guoapp://hongguo/catalog?query=coalesced'
start=time.monotonic()
with ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(lambda _:m.resolve(cache_url),range(4)))
assert calls['coalesced']==1 and sum(not r['cacheHit'] for r in results)==1
checks.append('four_simultaneous_searches_share_one_native_call')
cached_start=time.monotonic();cached=m.resolve(cache_url);cached_seconds=time.monotonic()-cached_start
assert cached['cacheHit'] and calls['coalesced']==1
checks.append('repeated_search_uses_bounded_memory_cache')
cached['entries'][0]['title']='mutated caller copy'
assert m.resolve(cache_url)['entries'][0]['title']!='mutated caller copy'
checks.append('cached_results_are_copy_isolated')
m.resolve(cache_url,True);assert calls['coalesced']==2
checks.append('explicit_refresh_requeries_native_core')

s.STATE['config'].update(sourceImportRoot=str(BASE),output=str(BASE/'output'),gpu=False)
url='guoapp://hongguo/detail/123456789'
def wait(jid):
    until=time.monotonic()+30
    while time.monotonic()<until:
        row=m.list()[-1]
        if row['id']==jid and row['status'] not in ('queued','running'):return row
        time.sleep(.05)
    raise RuntimeError('fixture setup timeout')
first=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[1],'downloadConcurrency':1,'confirmBatches':False})
assert wait(first['id'])['status']=='completed'
queued=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[2],'downloadConcurrency':1,'batchSize':1,'confirmBatches':True})
row=wait(queued['id']);assert row['status']=='completed' and row['done']==1
checks.append('real_adapter_seeds_verified_local_files_with_legacy_flags_ignored')
(ROOT/'tmp/native-fullseries-backend-report.json').write_text(json.dumps({'fixture':True,'passed':len(checks),'checks':checks,'cachedLookupMilliseconds':round(cached_seconds*1000,3)},indent=2),'utf-8')
host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session();base='http://127.0.0.1:'+str(host.server_address[1])
metadata={'url':base,'launch':base+'/launch/'+host.session.launch,'base':str(BASE),'pid':os.getpid(),'fixture':True,'seedTask':queued['id'],'compiled':args.compiled,'version':args.version,'signedDistributionVerified':args.compiled}
(ROOT/'tmp/native-fullseries-ui-host.json').write_text(json.dumps(metadata),'utf-8')
fixture_stop=threading.Event()
if '--queue-scroll-fixture' in sys.argv:
    for i in range(20):
        active=i==0
        items=[{'number':n,'status':'running' if active else 'failed','stage':'合成传输进度','bytes':n*1024,'totalBytes':102400,'error':'合成错误详情，用于验证手动展开状态和滚动保持。'} for n in range(1,5)]
        m.rows.append({'id':f'scroll-fixture-{i:02}','url':f'guoapp://hongguo/detail/{987650000+i}','directory':str(BASE),'video':True,'episodes':[1,2,3,4],
                       'downloadConcurrency':1,'status':'running' if active else 'failed','title':f'滚动保持验收记录 {i:02}（合成）','stage':'刷新 0','done':0,'items':items,'createdAt':time.time(),'warnings':[]})
    m.save()
    def animate_queue():
        tick=0
        while not fixture_stop.wait(.1):
            tick+=1
            with m.lock:
                for row in m.rows:
                    if row['id'].startswith('scroll-fixture-'):
                        row['stage']='合成进度刷新 '+str(tick)
                        if row['status']=='running':
                            for item in row['items']:item.update(bytes=tick%100*1024,stage='合成传输 '+str(tick))
    threading.Thread(target=animate_queue,daemon=True).start()
print(json.dumps(metadata),flush=True)
def shutdown():
    host.shutdown()
threading.Timer(180,shutdown).start()
try:host.serve_forever()
finally:
    fixture_stop.set();m.shutdown();s.shutdown_jobs();host.server_close()
    (BASE/'fixture-core-stats.json').write_text(json.dumps({'catalogCalls':calls,'settingsChanges':settings_changes,'downloads':len(jobs)},indent=2),'utf-8')
