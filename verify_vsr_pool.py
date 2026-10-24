"""Real two-video model reuse plus controlled worker lifecycle checks."""
from pathlib import Path
import copy,json,os,shutil,sys,tempfile,time,threading
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='vsr-pool-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,vsr_pool
report={'base':str(BASE),'ok':False,'checks':[]};timings=[]
def check(name,value=True):assert value,name;report['checks'].append(name);print('PASS '+name,flush=True)
try:
    source=Path(json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source'])
    folder=BASE/'source';folder.mkdir();first=folder/'01.mp4'
    s.ff(['-ss','3','-i',str(source),'-t','2','-vf','scale=640:368,fps=6','-c:v','libx264','-preset','fast','-c:a','aac',str(first)])
    shutil.copy2(first,folder/'02.mp4');hashes={str(p):s.sha256(p) for p in folder.glob('*.mp4')}
    pid=s.scan(str(folder))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True
    engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'));region={'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}
    s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='vsr',vsrRoot=engine['root'],vsrPython=engine['python'],vsrMode='sttn-auto',vsrReuseWorker=True,subtitleRegions=[region],subtitleRegion=region)
    with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':'subtitle','ids':[pid]})['id']
    real=vsr_pool.POOL.run
    def measured(*args,**kwargs):
        started=time.monotonic();value=real(*args,**kwargs);timings.append({'seconds':round(time.monotonic()-started,3),**value});print('REAL '+json.dumps(timings[-1]),flush=True);return value
    with patch.object(vsr_pool.POOL,'run',measured):s.worker(jid,[pid],'subtitle',s.JOBS[jid]['config'])
    job=s.JOBS[jid];check('two_real_AI_videos_completed',job['status']=='completed')
    check('same_worker_process_for_both_videos',len(timings)==2 and timings[0]['pid']==timings[1]['pid'] and timings[1]['reusedProcess'])
    check('model_loaded_once_and_reused',timings[1]['modelLoads']==1 and timings[1]['modelCacheHits']>=1)
    artifacts=[a for a in p['artifacts'] if a['job']==jid]
    check('whole_duration_and_audio_valid',len(artifacts)==2 and all(abs(s.probe(a['path'])['duration']-2)<.15 and s.probe(a['path'])['audio'] for a in artifacts))
    for a in artifacts:s.run_process([s.FFMPEG,'-v','error','-i',a['path'],'-f','null','-'])
    check('outputs_fully_decode');check('source_files_unchanged',all(s.sha256(path)==digest for path,digest in hashes.items()))
    proc=vsr_pool.POOL.client.process;s.shutdown_jobs();check('shutdown_releases_worker',proc.poll() is not None)
    fake="import json,sys,os,time\nprint(json.dumps({'event':'ready','pid':os.getpid()}),flush=True)\nfor line in sys.stdin:\n r=json.loads(line)\n if r.get('slow'):time.sleep(5)\n print(json.dumps({'event':'result','id':r['id'],'ok':True}),flush=True)\n"
    with patch.object(vsr_pool,'WORKER_SOURCE',fake):
        pool=vsr_pool.Pool(idle_seconds=.2);event=threading.Event();pool.run(sys.executable,ROOT,{'duration':1},event)
        proc=pool.client.process;time.sleep(.5);check('idle_timeout_releases_worker',proc.poll() is not None)
        event=threading.Event();threading.Timer(.2,event.set).start()
        try:pool.run(sys.executable,ROOT,{'duration':1,'slow':True},event)
        except InterruptedError:check('cancel_terminates_inflight_worker',pool.client is None)
        else:raise AssertionError('Cancellation ignored')
        check('cancelled_pool_can_restart',pool.run(sys.executable,ROOT,{'duration':1},threading.Event())['ok']);pool.close()
    report.update(ok=True,timings=timings,projectId=pid,jobId=jid,outputs=[a['path'] for a in artifacts],fixture='Two identical 2s clips at 640x368 / 6fps; cold-start versus reused process, not a full-series benchmark')
finally:
    vsr_pool.POOL.close();s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/vsr-pool-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'base':str(BASE)},ensure_ascii=False),flush=True)
