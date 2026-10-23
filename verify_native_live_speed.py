"""Read the user's native link and try one episode, without touching customer data."""
from pathlib import Path
import json,os,sys,tempfile,time
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='native-live-speed-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'vendor'))
import server as s
m=s.source_manager();url='guoapp://hongguo/detail/7694653385668037657'
report={'live':True,'url':url,'wholeSeriesDownloaded':False,'base':str(BASE),'downloadProbe':{'attempted':False}}
try:
    if '--direct' in sys.argv:
        settings=m.core.call({'action':'resourceSettings'})
        settings={key:settings[key] for key in ('proxyMode','proxyURL','catalogConcurrency','catalogIntervalMs','downloadConcurrency','downloadBySource') if key in settings}
        settings.update(proxyMode='direct',proxyURL='')
        m.core.call({'action':'saveResourceSettings','settings':settings});report['connectionMode']='direct'
    begun=time.perf_counter();detail=m.resolve(url);report['detailSeconds']=round(time.perf_counter()-begun,3)
    report.update(title=detail['title'],episodeCount=detail['totalEpisodes'],sourceEntries=len(detail['episodes']),lockedEpisodes=len(detail.get('lockedEpisodes',[])))
    begun=time.perf_counter();again=m.resolve(url);report['cachedDetailMilliseconds']=round((time.perf_counter()-begun)*1000,3);assert again['cacheHit']
    print(json.dumps({key:value for key,value in report.items() if key!='base'},ensure_ascii=False),flush=True)
    import urllib.parse
    search_url='guoapp://hongguo/catalog?query='+urllib.parse.quote(detail['title'])
    begun=time.perf_counter();found=m.resolve(search_url);report['searchSeconds']=round(time.perf_counter()-begun,3)
    begun=time.perf_counter();found_again=m.resolve(search_url);report['cachedSearchMilliseconds']=round((time.perf_counter()-begun)*1000,3)
    report['searchResults']=len(found['entries']);assert found_again['cacheHit']
    first=next(iter(detail['episodes']),None)
    if first:
        original=m.resolve
        def no_cover(*args,**kwargs):
            value=original(*args,**kwargs)
            if value.get('kind')=='detail':value['coverUrl']=''
            return value
        m.resolve=no_cover
        begun=time.perf_counter();task=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[first['number']],'downloadConcurrency':5,'confirmBatches':False})
        print('SINGLE_EPISODE_PROBE_STARTED',first['number'],flush=True)
        until=time.monotonic()+60
        while time.monotonic()<until:
            row=m.list()[-1]
            if row['status'] not in ('queued','running'):break
            time.sleep(.2)
        else:
            m.cancel(task['id']);time.sleep(.5);row=m.list()[-1]
        report['downloadProbe']={'attempted':True,'episode':first['number'],'status':row['status'],'done':row.get('done',0),'elapsedSeconds':round(time.perf_counter()-begun,3),'stage':row.get('stage'),'nativeConcurrency':m.core.download_concurrency,'nativeConcurrencyActual':m.core.call({'action':'resourceSettings'})['downloadConcurrency'],'errors':[{key:item.get(key) for key in ('number','errorCode','error')} for item in row.get('items',[]) if item.get('error')]}
        if row.get('projectId'):
            video=s.get_project(row['projectId'])['videos'][0]
            report['downloadProbe'].update(bytes=video['bytes'],duration=video['duration'],audio=video['audio'])
except Exception as error:
    report['error']=str(error)
finally:
    m.shutdown();s.shutdown_jobs()
    report['note']='真实源站单集尝试与搜索计时；不代表整剧下载已完成，也不能保证客户网络的固定下载速率。未下载或验证源站图片。'
    filename='native-live-speed-direct-report.json' if '--direct' in sys.argv else 'native-live-speed-report.json'
    (ROOT/'tmp'/filename).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
