"""Three-minute full-duration neural test at six fps; not a speed benchmark."""
from pathlib import Path
import json,os,re,sys,tempfile,time
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent
seed=json.loads((ROOT/'tmp/subtitle-full-latest.json').read_text('utf-8'))
BASE=Path(tempfile.mkdtemp(prefix='subtitle-minutes-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s
checks=[];report={'base':str(BASE),'ok':False,'checks':checks,'fixture':'180 seconds, 640x368, 6 fps, looped from the supplied subtitle sample; validates duration/coverage, not 30 fps throughput'}
def check(name,value=True):
    assert value,name
    checks.append(name);print('PASS '+name,flush=True)
try:
    folder=BASE/'source';folder.mkdir();source=folder/'3分钟-6fps压力样片.mp4'
    s.ff(['-stream_loop','-1','-i',seed['media'][1]['source'],'-t','180','-vf','fps=6','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac',str(source)])
    original_hash=s.sha256(source);pid=s.scan(str(folder))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True
    engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
    s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='vsr',vsrRoot=engine['root'],vsrPython=engine['python'],vsrMode='sttn-auto',subtitleRegions=[seed['region']],subtitleRegion=seed['region'],subtitleFirst=1)
    with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':'subtitle','ids':[pid]})['id']
    # Log actual frame progress without altering production telemetry.
    original_run=s.run_process;last=[0.0]
    def observed(command,*a,**kwargs):
        notify=kwargs.get('observe')
        if notify:
            def update(line):
                notify(line)
                if time.monotonic()-last[0]>15:
                    last[0]=time.monotonic();row=s.JOBS[jid].get('telemetry',{}).get('rows',[])
                    print('MODEL '+line[-140:],flush=True)
            kwargs['observe']=update
        return original_run(command,*a,**kwargs)
    began=time.monotonic()
    with patch.object(s,'run_process',observed):s.worker(jid,[pid],'subtitle',s.JOBS[jid]['config'])
    job=s.JOBS[jid];check('three_minute_real_AI_task_completed',job['status']=='completed')
    output=next(a['path'] for a in p['artifacts'] if a['job']==jid and a['kind']=='AI字幕处理');meta=s.probe(output)
    check('full_180_seconds_preserved',abs(meta['duration']-180)<.15)
    check('original_audio_present',meta['audio'])
    raw=s.run_process([s.FFMPEG,'-hide_banner','-loglevel','error','-nostats','-i',output,'-progress','pipe:1','-f','null','-'])
    frames=int(re.findall(rb'^frame=(\d+)',raw,re.M)[-1]);check('all_1080_frames_decode',frames==1080)
    comparison=BASE/'3分钟样片-末段字幕修复对比.png'
    s.ff(['-ss','173.4','-i',str(source),'-ss','173.4','-i',output,'-filter_complex','[0:v][1:v]hstack=inputs=2','-frames:v','1','-update','1',str(comparison)])
    check('source_sha256_unchanged',s.sha256(source)==original_hash)
    report.update(ok=True,source=str(source),output=output,metadata=meta,decodedFrames=frames,processingSeconds=round(time.monotonic()-began,2),comparison=str(comparison),comparisonTimestamp=173.4,projectId=pid,jobId=jid)
finally:
    s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/subtitle-minutes-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
