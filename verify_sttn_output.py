"""Verify checked STTN I/O against the existing portable v1 engine, without editing it."""
from pathlib import Path
from unittest.mock import patch
import json,os,sys,tempfile,threading,time
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='sttn-output-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,vsr_pool,engine_manager
checks=[];report={'base':str(BASE),'checks':checks,'ok':False}
def check(name,value=True):assert value,name;checks.append(name);print('PASS '+name,flush=True)
def create(pid,paths):
    with patch.object(s,'ensure_runner',lambda:None):return s.JOBS[s.create_job({'kind':'subtitle','ids':[pid],'sourceVideoPaths':{pid:paths}})['id']]
def run(job):s.worker(job['id'],job['ids'],job['kind'],job['config']);return job
engine=engine_manager.active(ROOT/'tmp/engine-installed-data')
if not engine:
    engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
    report['portableV1']=False
else:report['portableV1']=True
runtime=engine['python'];root=Path(engine['root'])
source=Path(json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source'])
source_hash=s.sha256(source)
watched=[root/'backend/main.py',root/'backend/tools/video_io.py',root/'backend/models/sttn-auto/infer_model.pth']
hashes={str(p):s.sha256(p) for p in watched}
try:
    # Fast standalone writer tests use the real FFmpeg and engine's NumPy.
    writer_test=BASE/'writer_test.py'
    writer_test.write_text(vsr_pool.STRICT_IO_SOURCE+'''
import sys,json,numpy as np
APP_FFMPEG=sys.argv[1]
folder=__import__('pathlib').Path(sys.argv[2])
writer=CheckedVideoWriter(folder/'writer-ok.mp4',5,(48,32))
for n in range(5):writer.write(np.zeros((32,48,3),dtype=np.uint8))
writer.release();writer.release();writer.dispose()
failures=[]
for label,shape in [('encoder_exit',(32,48,3)),('broken_pipe',(720,1280,3))]:
 writer=CheckedVideoWriter(folder/'missing-parent'/f'{label}.mp4',5,(shape[1],shape[0]))
 try:
  writer.write(np.zeros(shape,dtype=np.uint8));writer.release()
 except RuntimeError as error:
  message=str(error);assert 'exit code' in message and ('No such file' in message or 'Error opening' in message),message
  failures.append(label)
 else:raise AssertionError('Encoder failure was swallowed')
 finally:writer.dispose()
try:CheckedVideoWriter(folder/'odd.mp4',5,(49,33))
except ValueError:failures.append('odd_dimensions')
else:raise AssertionError('Odd dimensions accepted')
writer=CheckedVideoWriter(folder/'empty.mp4',5,(48,32))
try:writer.release()
except RuntimeError:failures.append('zero_frames')
else:raise AssertionError('Empty result accepted')
finally:writer.dispose()
print(json.dumps({'failures':failures}))
''','utf-8')
    raw=s.run_process([runtime,'-B',str(writer_test),s.FFMPEG,str(BASE)],timeout=60)
    outcome=json.loads(raw.decode('utf-8').splitlines()[-1])
    check('checked_writer_produces_real_decodable_video',abs(s.probe(BASE/'writer-ok.mp4')['duration']-1)<.1)
    check('encoder_exit_and_broken_pipe_keep_actual_stderr',set(outcome['failures'])=={'encoder_exit','broken_pipe','odd_dimensions','zero_frames'})
    folder=BASE/'source';folder.mkdir();first=folder/'第001集-14秒.mp4';silent=folder/'第002集-无声.mp4'
    s.ff(['-stream_loop','1','-i',str(source),'-t','14','-vf','scale=360:640,fps=12','-c:v','libx264','-preset','fast','-c:a','aac',str(first)])
    s.ff(['-i',str(first),'-t','2','-an','-c:v','copy',str(silent)])
    p=s.scan(str(folder))['projects'][0];paths=[v['path'] for v in p['videos']]
    roi={'x':.15,'y':.79,'w':.7,'h':.13}
    s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='vsr',vsrRoot=str(root),vsrPython=runtime,vsrMode='sttn-auto',
        vsrReuseWorker=True,subtitleRegions=[roi],subtitleRegion=roi)
    # Deliberately make the old engine FFmpeg locator unusable in this process.
    # The corrected bridge must use the already bundled application FFmpeg.
    source_code=vsr_pool.WORKER_SOURCE.replace('factory=sttn.STTNInpaint;models={}',
        "from backend.tools.ffmpeg_cli import FFmpegCLI\n FFmpegCLI.ffmpeg_path=property(lambda self: 'Z:/missing-old-engine/ffmpeg.exe')\n factory=sttn.STTNInpaint;models={}")
    assert source_code!=vsr_pool.WORKER_SOURCE
    stats=[];real_run=vsr_pool.POOL.run
    def measured(*args,**kwargs):
        value=real_run(*args,**kwargs);stats.append(value.copy());return value
    with patch.object(vsr_pool,'WORKER_SOURCE',source_code),patch.object(vsr_pool.POOL,'run',measured):
        began=time.perf_counter();job=run(create(p['id'],paths));report['seconds']=round(time.perf_counter()-began,3)
    check('real_sttn_two_videos_complete_with_old_ffmpeg_disabled',job['status']=='completed')
    check('same_model_worker_reused',len(stats)==2 and stats[0]['pid']==stats[1]['pid'] and stats[1]['reusedProcess'])
    outputs=[a for a in p['artifacts'] if a['job']==job['id']]
    check('all_outputs_registered_only_after_validation',len(outputs)==2 and len(job['checkpoints'])>=2)
    media=[s.probe(a['path']) for a in outputs]
    check('customer_360x640_dimensions_and_full_duration',media[0]['width']==360 and media[0]['height']==640 and abs(media[0]['duration']-14)<.15)
    check('audio_and_silent_inputs_both_mux_correctly',media[0]['audio'] and not media[1]['audio'])
    for row in outputs:s.run_process([s.FFMPEG,'-v','error','-xerror','-i',row['path'],'-f','null','-'],timeout=60)
    check('both_results_fully_decode')
    invalid_encoder=BASE/'missing-encoder.exe'
    try:
        vsr_pool.POOL.run(runtime,root,{'input':str(first),'output':str(BASE/'invalid-result.mp4'),'duration':14,'mode':'sttn-auto','regions':[[500,570,40,320]],'ffmpeg':str(invalid_encoder)},threading.Event())
    except vsr_pool.WorkerError as error:
        check('real_worker_returns_encoder_startup_error_and_traceback','FFmpeg executable' in str(error) and 'Traceback' in error.details)
        check('failed_worker_is_closed_without_marking_video_complete',vsr_pool.POOL.client is None)
    else:raise AssertionError('Invalid executable was silently accepted')
    # Turning reuse off still uses checked output, and closes the worker.
    s.STATE['config']['vsrReuseWorker']=False
    single=run(create(p['id'],[paths[1]]))
    check('reuse_disabled_still_uses_checked_path_and_closes_worker',single['status']=='completed' and vsr_pool.POOL.client is None)
    check('portable_engine_sources_and_model_unchanged',all(s.sha256(path)==digest for path,digest in hashes.items()))
    check('supplied_original_unchanged',s.sha256(source)==source_hash)
    report.update(ok=True,outputs=outputs,media=media,workerStats=[{k:v for k,v in x.items() if k!='engineLog'} for x in stats],engineRoot=str(root))
finally:
    vsr_pool.POOL.close();s.shutdown_jobs()
    (ROOT/'tmp/sttn-output-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'passed':len(checks),'base':str(BASE)},ensure_ascii=False))
