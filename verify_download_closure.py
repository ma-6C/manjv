"""Queue concurrency with real HTTP bytes; source failures and durable recovery."""
from pathlib import Path
import sys,json,threading,time,tempfile,urllib.request,hashlib,types,copy
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;sys.dont_write_bytecode=True
VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.2'
if '--compiled' in sys.argv:sys.path.insert(0,str(ROOT/'release'/VERSION/'漫剧工坊/_internal'))
import hongguo_source as h,source_imports as si
if '--compiled' in sys.argv:assert h.__file__.endswith('.pyd') and si.__file__.endswith('.pyd')
BASE=Path(tempfile.mkdtemp(prefix='download-closure-',dir=ROOT/'tmp'));checks=[];results={}
DATA=bytes(range(256))*2048;counts={};running=0;peak=0;gate=threading.Lock()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        global running,peak
        with gate:
            counts[self.path]=counts.get(self.path,0)+1;running+=1;peak=max(peak,running)
        self.send_response(200);self.send_header('Content-Length',str(len(DATA)));self.send_header('ETag','"closure"');self.end_headers()
        try:
            for pos in range(0,len(DATA),16384):
                time.sleep(.025);self.wfile.write(DATA[pos:pos+16384]);self.wfile.flush()
        except OSError:pass
        finally:
            with gate:running-=1
host=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=host.serve_forever,daemon=True).start()
sid='123456';url=h.BASE+'/detail?series_id='+sid
def check(name,value=True):assert value,name;checks.append(name)
def local_response(url,image=False,cancel=None,extra_headers=None):
    return urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(host.server_address[1])+'/'+url.rsplit('/',1)[-1],headers=extra_headers or {}),timeout=4)
def setup(label,concurrency,fail=(),confirm=False,batch=5,numbers=None):
    base=BASE/label;base.mkdir();meta={'kind':'detail','platform':'hongguo_web','seriesId':sid,'url':url,'title':'队列验收','intro':'HTTP transfer fixture','coverUrl':'',
        'episodes':[{'number':n,'playerUrl':h.BASE+f'/player/{sid}/{700000+n}'} for n in range(1,9)]}
    access=h.Access(interval=.01);parsed=[];imported=[]
    def fetch(value,cancel=None,**kwargs):return value
    def parse_player(value,series,number,player_url=None):
        parsed.append(number)
        if number in fail:raise ValueError('网页集序无法核对，未下载')
        return {'url':'https://hongguoduanju.com/video/public/'+str(700000+number),'episodeId':str(700000+number),'uploadDate':None}
    adapter=types.SimpleNamespace(ACCESS=access,site_url=h.site_url,Cancelled=h.Cancelled,SourceLimited=h.SourceLimited,fetch_html=fetch,parse_detail=lambda *a:copy.deepcopy(meta),parse_player=parse_player,download=h.download)
    def register(directory,meta,path,cover,details):
        assert path.read_bytes()==DATA
        imported.append(details['sourceEpisode']);return 'project'
    manager=si.ImportManager(base/'data',register,lambda p:{'duration':1,'audio':True},adapter);manager.start_worker=lambda:None
    row=manager.start({'url':url,'directory':str(base),'video':True,'episodes':numbers or list(range(1,9)),
        'batchSize':batch,'confirmBatches':confirm,'downloadConcurrency':concurrency})
    return manager,manager.get(row['id']),parsed,imported
try:
    with patch.object(h,'response',local_response):
        for concurrency in (1,2):
            peak=0;m,row,parsed,imported=setup('workers-'+str(concurrency),concurrency)
            begun=time.monotonic();m.run();elapsed=time.monotonic()-begun
            check(f'workers_{concurrency}_all_eight_exact_files_and_manifest',row['status']=='completed' and row['done']==8 and len(set(imported))==8)
            records=json.loads((Path(row['savedDirectory'])/'下载记录.json').read_text('utf-8'))
            check(f'workers_{concurrency}_no_commit_lost',len(records)==8 and [r['episode'] for r in records]==list(range(1,9)) and all(r['sha256']==hashlib.sha256(DATA).hexdigest() for r in records))
            check(f'workers_{concurrency}_bounded_inflight',peak<=concurrency and (concurrency==1 or peak==2))
            check(f'workers_{concurrency}_selected_order_unchanged',row['episodes']==list(range(1,9)))
            results[str(concurrency)]={'seconds':round(elapsed,3),'peakHttpTransfers':peak,'files':8,'bytes':8*len(DATA)}
        check('two_workers_reduce_latency_fixture_time',results['2']['seconds']<results['1']['seconds']*.8)
        m,row,parsed,imported=setup('consecutive-unavailable',2,fail=(2,3,4));m.run()
        check('three_missing_do_not_hide_remaining_selected',row['done']==5 and {i['number'] for i in row['items'] if i['status']=='failed'}=={2,3,4} and all(i['status']!='pending' for i in row['items']))
        before={p:p.stat().st_mtime_ns for p in Path(row['savedDirectory']).glob('*.mp4')};m.h.parse_player=lambda text,series,n,player_url=None: {'url':'https://hongguoduanju.com/video/public/'+str(700000+n),'episodeId':str(700000+n),'uploadDate':None}
        m.control(row['id'],'resume');m.run()
        check('retry_only_missing_and_keep_valid_files',row['done']==8 and row['status']=='completed' and all(p.stat().st_mtime_ns==stamp for p,stamp in before.items()))
        # A new task reuses local records without a remote playback lookup.
        parsed.clear();m.h.parse_player=lambda *a:(_ for _ in ()).throw(AssertionError('verified local must not query remote player'))
        new=m.start({'url':url,'directory':row['directory'],'video':True,'episodes':[8,1],'batchSize':3,'confirmBatches':False,'downloadConcurrency':2});m.run();new=m.get(new['id'])
        check('local_reuse_has_no_player_requests',new['status']=='completed' and all(i['status']=='skipped' for i in new['items']))
        report=m.report(row['id']);serialized=json.dumps(report,ensure_ascii=False)
        check('report_records_concurrency_and_missing_stages_without_paths',report['downloadConcurrency']==2 and str(BASE) not in serialized and 'episodeLinks' not in serialized)
        m,row,parsed,imported=setup('legacy-batch-flags',2,confirm=True,batch=3,numbers=[6,1,4,2,8]);m.run()
        check('legacy_batch_flags_do_not_pause_or_truncate_selection',row['status']=='completed' and set(imported)=={6,1,4,2,8} and row['episodes']==[6,1,4,2,8])
        check('continuous_report_has_no_retired_batch_controls',m.report(row['id'])['downloadMode']=='continuous' and 'confirmBatches' not in row and 'batchSize' not in row)
        m,seed,parsed,imported=setup('legacy-waiting-upgrade',2,numbers=[6]);m.run()
        saved_six=Path(seed['items'][0]['path']);saved_stamp=saved_six.stat().st_mtime_ns
        old=m.start({'url':url,'directory':seed['directory'],'video':True,'episodes':[6,1,4,2,8],'downloadConcurrency':2})
        old=m.get(old['id']);old.update(status='awaiting_confirmation',done=1,batchSize=1,confirmBatches=True)
        old['items'][0].update(status='completed',path=str(saved_six))
        for status in ('cancelled','interrupted','failed','limited'):
            kept=copy.deepcopy(old);kept.update(id='preserve-'+status,status=status);m.rows.append(kept)
        m.save()
        migrated=si.ImportManager(m.data,m.import_video,m.probe,m.h)
        deadline=time.monotonic()+20
        while time.monotonic()<deadline and migrated.get(old['id'])['status'] in ('queued','running'):time.sleep(.05)
        recovered=migrated.get(old['id'])
        check('old_waiting_confirmation_automatically_continues_after_load',recovered['status']=='completed' and recovered['done']==5 and len(imported)==5)
        check('legacy_continuation_preserves_completed_file',saved_six.stat().st_mtime_ns==saved_stamp and imported.count(6)==1)
        check('cancelled_failed_limited_and_interrupted_tasks_not_auto_restarted',all(migrated.get('preserve-'+status)['status']==status for status in ('cancelled','interrupted','failed','limited')))
        stored=json.loads(migrated.path.read_text('utf-8'))
        check('retired_batch_fields_removed_from_saved_tasks',all('batchSize' not in task and 'confirmBatches' not in task for task in stored))
        migrated.shutdown()
        m,paused,parsed,imported=setup('legacy-upgrade-source-paused',2,numbers=[1,2])
        paused.update(status='awaiting_confirmation',batchSize=1,confirmBatches=True);m.save();m.h.ACCESS.pause(429,'30')
        migrated=si.ImportManager(m.data,m.import_video,m.probe,m.h)
        worker=migrated.worker
        if worker:worker.join(timeout=1)
        check('legacy_auto_continue_respects_existing_source_wait',migrated.get(paused['id'])['status']=='queued' and not imported and m.h.ACCESS.snapshot()['paused'])
        migrated.shutdown()
        m,row,parsed,imported=setup('duplicate-id',2)
        m.h.parse_player=lambda text,series,n,player_url=None: {'url':'https://hongguoduanju.com/video/public/700001','episodeId':'700001','uploadDate':None}
        m.run();check('same_media_id_cannot_be_archived_as_different_episodes',row['done']==1 and sum(i['status']=='failed' for i in row['items'])==7)
        m,row,parsed,imported=setup('cancel',2)
        original=m.h.download
        def stop(url,path,cancel,progress,image=False):
            def update(n,total):
                progress(n,total)
                if n>0:cancel.set()
            return original(url,path,cancel,update,image)
        m.h.download=stop;m.run()
        check('parallel_cancel_preserves_partial_and_starts_no_more',row['status']=='cancelled' and row['done']==0 and len(parsed)<=2 and any(Path(row['savedDirectory']).rglob('*.part')))
    access=h.Access(interval=.08);starts=[]
    def enter():
        access.enter();starts.append(time.monotonic());time.sleep(.16);access.flight.release()
    threads=[threading.Thread(target=enter) for _ in range(4)]
    for t in threads:t.start()
    for t in threads:t.join()
    starts.sort();check('two_slots_keep_global_request_spacing',all(b-a>=.075 for a,b in zip(starts,starts[1:])))
    access.pause(429,'2')
    try:access.enter()
    except h.SourceLimited:check('source_pause_blocks_all_transfer_slots')
    else:raise AssertionError('pause ignored')
    # Invalid parallelism is rejected before any worker starts.
    try:m.start({'url':url,'directory':row['directory'],'video':True,'episodes':[1],'downloadConcurrency':5})
    except ValueError:check('unsupported_concurrency_rejected')
    else:raise AssertionError('unbounded concurrency accepted')
    report={'version':VERSION,'compiled':'--compiled' in sys.argv,'passed':len(checks),'checks':checks,'localRealHttp':True,'externalNetwork':False,
        'syntheticContent':True,'base':str(BASE),'latencyFixture':results,'timeReductionPercent':round(100*(1-results['2']['seconds']/results['1']['seconds']),1)}
    (ROOT/('tmp/download-closure-compiled.json' if '--compiled' in sys.argv else 'tmp/download-closure-source.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
finally:host.shutdown();host.server_close()
