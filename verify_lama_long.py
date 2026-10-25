"""Full-duration LaMa fixture and real cancellation; not a normal-FPS speed benchmark."""
from pathlib import Path
import json,os,sys,tempfile,time,threading
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='lama-long-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s
report={'base':str(BASE),'ok':False,'checks':[],'fixture':'180s, 640x368, 2fps / 360 frames; duration coverage only'}
def check(name,value):assert value,name;report['checks'].append(name);print('PASS '+name,flush=True)
try:
    source=Path(json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source']);folder=BASE/'source';folder.mkdir();video=folder/'180秒样片.mp4'
    s.ff(['-stream_loop','-1','-i',str(source),'-t','180','-vf','scale=640:368,fps=2','-c:v','libx264','-preset','fast','-c:a','aac',str(video)])
    pid=s.scan(str(folder))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True;digest=s.sha256(video)
    engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'));r={'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}
    s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='vsr',vsrMode='lama-box',vsrRoot=engine['root'],vsrPython=engine['python'],vsrReuseWorker=True,subtitleRegion=r,subtitleRegions=[r],lamaDevice='auto')
    with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':'subtitle','ids':[pid]})['id']
    job=s.JOBS[jid];start=time.perf_counter();s.worker(jid,[pid],'subtitle',job['config']);elapsed=time.perf_counter()-start
    check('three_minute_job_completes',job['status']=='completed');output=next(a['path'] for a in p['artifacts'] if a['job']==jid);meta=s.probe(output)
    check('duration_audio_and_browser_codec',abs(meta['duration']-180)<.15 and meta['audio'] and meta['codec']=='h264')
    check('all_360_frames_processed',job['vsrWorker']['frames']==360)
    s.run_process([s.FFMPEG,'-v','error','-i',output,'-f','null','-']);check('whole_output_fully_decodes',True)
    # The same real worker is interrupted during an in-flight second clip.
    cancel=threading.Event();process=s.lama_local.POOL.client.process
    timer=threading.Timer(.5,cancel.set);timer.start()
    try:s.lama_local.POOL.run(engine['python'],engine['root'],{'input':str(video),'output':str(BASE/'cancelled.mp4'),'regions':[[306,330,184,457]],'duration':180,'device':'auto','ffmpeg':s.FFMPEG},cancel)
    except InterruptedError:check('cancel_releases_active_worker',process.poll() is not None and s.lama_local.POOL.client is None)
    else:raise AssertionError('Cancellation ignored')
    check('source_preserved',s.sha256(video)==digest)
    report.update(ok=True,projectId=pid,jobId=jid,seconds=round(elapsed,3),worker=job['vsrWorker'],output=output)
finally:
    s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/lama-long-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'base':str(BASE)},ensure_ascii=False),flush=True)
