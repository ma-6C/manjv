"""Thirty-file controlled HTTP comparison and pipeline recovery checks."""
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
import argparse,copy,hashlib,importlib.util,json,os,sys,tempfile,threading,time,types,urllib.request

ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--compiled',action='store_true');p.add_argument('--version',default='v0.8.5');args=p.parse_args()
sys.dont_write_bytecode=True
sys.path[:0]=([str(ROOT/'release'/args.version/'漫剧工坊/_internal')] if args.compiled else [])+[str(ROOT/'vendor')]
import source_imports as current,hongguo_source as h
if args.compiled:assert current.__file__.endswith('.pyd')
spec=importlib.util.spec_from_file_location('previous_source_imports',ROOT/'tmp/download-optimization-baseline/source_imports.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
BASE=Path(tempfile.mkdtemp(prefix='download-optimization-',dir=ROOT/'tmp'));DATA=bytes(range(256))*4096
gate=threading.Lock();active=0;peak=0;requests=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        global active,peak
        with gate:active+=1;peak=max(peak,active);requests.append(self.path)
        try:
            self.send_response(200);self.send_header('Content-Length',str(len(DATA)));self.end_headers()
            for offset in range(0,len(DATA),16384):
                time.sleep(.001);self.wfile.write(DATA[offset:offset+16384]);self.wfile.flush()
        except OSError:pass
        finally:
            with gate:active-=1
host=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=host.serve_forever,daemon=True).start()
url='guoapp://hongguo/detail/123456';checks=[];runs=[]
def check(name,value=True):assert value,name;checks.append(name)
def setup(module,label,concurrency,count=30,probe_hook=None,adaptive=False):
    directory=BASE/label;directory.mkdir()
    meta={'kind':'detail','platform':'guoapp_hongguo','seriesId':'123456','url':url,'title':'30集合成传输对比','intro':'Controlled HTTP fixture','coverUrl':'','episodes':[{'number':n,'playerUrl':url+'/episode/'+str(n)} for n in range(1,count+1)]}
    imported=[];started=[]
    def download(address,path,event,progress,image=False):
        started.append(int(address.rsplit('/',1)[-1]));progress(0,len(DATA))
        with urllib.request.urlopen(address,timeout=10) as response,path.open('xb') as out:
            done=0
            while chunk:=response.read(16384):
                if event.is_set():raise h.Cancelled()
                out.write(chunk);done+=len(chunk);progress(done,len(DATA))
    def probe(path):
        assert path.read_bytes()==DATA
        if probe_hook:probe_hook(path,started)
        time.sleep(.025);return {'duration':1,'audio':True,'height':1080}
    def register(*values):
        time.sleep(.015);imported.append(values[-1]['sourceEpisode']);return 'project'
    adapter=types.SimpleNamespace(ACCESS=h.Access(interval=0),site_url=lambda value:value,Cancelled=h.Cancelled,SourceLimited=h.SourceLimited,
        valid_episode_entry=lambda *a:True,resolve_episode=lambda meta,n,*a:{'url':'http://127.0.0.1:'+str(host.server_address[1])+'/'+str(n),'episodeId':str(700000+n),'uploadDate':None},download=download)
    manager=module.ImportManager(directory/'data',register,probe,adapter);manager.start_worker=lambda:None;manager.resolve=lambda *a,**k:copy.deepcopy(meta)
    row=manager.start({'url':url,'directory':str(directory),'video':True,'episodes':list(range(1,count+1)),'downloadConcurrency':concurrency,'adaptiveDownloads':adaptive,'segmentedDownload':False,'downloadQuality':0})
    return manager,manager.get(row['id']),imported,started
try:
    for concurrency in (1,3,5):
        comparison={}
        for module,label in ((previous,'previous'),(current,'pipeline')):
            peak=0;manager,row,imported,started=setup(module,label+'-'+str(concurrency),concurrency)
            begun=time.monotonic();manager.run();elapsed=time.monotonic()-begun
            check(label+'_'+str(concurrency)+'_all_thirty_verified_and_imported',row['status']=='completed' and row['done']==30 and sorted(imported)==list(range(1,31)))
            check(label+'_'+str(concurrency)+'_network_slots_bounded',peak<=concurrency)
            comparison[label]={'seconds':round(elapsed,3),'bytes':len(DATA)*30,'files':30,'peakTransfers':peak}
            if module is current:
                diagnostic=manager.report(row['id'])
                check('pipeline_'+str(concurrency)+'_phase_metrics_are_real',all(diagnostic['phaseSeconds'].get(key,0)>0 for key in ('lookup','download','verify','import')))
                check('pipeline_'+str(concurrency)+'_diagnostic_keeps_paths_out',str(BASE) not in json.dumps(diagnostic))
        comparison['concurrency']=concurrency;comparison['timeReductionPercent']=round(100*(1-comparison['pipeline']['seconds']/comparison['previous']['seconds']),1)
        runs.append(comparison)
    check('one_worker_pipeline_overlaps_processing_and_network',runs[0]['pipeline']['seconds']<runs[0]['previous']['seconds']*.95)
    def overlapping_probe(path,started):
        if path.name=='700001.download':
            deadline=time.monotonic()+3
            while 2 not in started and time.monotonic()<deadline:time.sleep(.005)
            assert 2 in started,'Network slot still blocked by verification'
    manager,row,imported,started=setup(current,'overlap',1,count=3,probe_hook=overlapping_probe);manager.run()
    check('next_transfer_starts_before_first_verification_finishes',row['status']=='completed' and row['done']==3)
    window=current.DownloadWindow(5,True)
    check('automatic_window_starts_at_selected_limit',window.current==5)
    for _ in range(6):window.observe(True,1000,1)
    check('stable_transfers_ramp_to_selected_limit',window.current==5)
    window.observe(False);check('network_error_reduces_parallelism',window.current==2)
    for _ in range(30):window.observe(True,1000,1)
    check('adaptive_window_never_exceeds_selected_limit',window.current<=5 and len(window.events)>0)
    fixed=current.DownloadWindow(3,False);fixed.observe(False)
    check('manual_parallelism_stays_fixed',fixed.current==3)
    shared=current.DownloadWindow(5,True)
    for _ in range(3):shared.observe(True,3000,3)
    for _ in range(3):shared.observe(True,3000,4)
    check('bandwidth_sharing_is_judged_by_aggregate_rate',shared.current==5)
    shared.sample(0,5,0);shared.sample(6000,5,6);shared.sample(6600,5,12)
    check('one_slow_total_rate_window_does_not_lower_parallelism',shared.current==5)
    shared.sample(7200,5,18)
    check('persistent_total_rate_drop_reduces_parallelism',shared.current==4)
    for body in ({'downloadQuality':True},{'downloadQuality':480},{'adaptiveDownloads':1},{'segmentedDownload':'yes'}):
        try:manager.start({'url':url,'directory':row['directory'],'video':True,'episodes':[1],**body})
        except ValueError:check('invalid_option_rejected_'+next(iter(body))+'_'+str(next(iter(body.values()))))
        else:raise AssertionError('invalid download option accepted')
    report={'version':args.version,'compiled':args.compiled,'passed':len(checks),'checks':checks,'comparison':runs,'base':str(BASE),'localRealHttp':True,'syntheticContent':True,'filesPerRun':30,'processingDelayInjected':True,'externalSpeedGuarantee':False}
    destination=ROOT/('tmp/download-optimization-compiled.json' if args.compiled else 'tmp/download-optimization-source.json')
    destination.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=True),flush=True)
finally:host.shutdown();host.server_close()
