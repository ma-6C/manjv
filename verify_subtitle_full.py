"""Isolated whole-video scope, real media, output validation and recovery checks."""
from pathlib import Path
import argparse, copy, json, os, subprocess, sys, tempfile
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--real-ai',action='store_true');parser.add_argument('--source',type=Path);args=parser.parse_args()
BASE=Path(tempfile.mkdtemp(prefix='subtitle-full-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s

checks=[];report={'base':str(BASE),'checks':checks,'realAI':args.real_ai,'ok':False}
def check(name,value=True):
    assert value,name
    checks.append(name);print('PASS '+name,flush=True)
def create(pid,**body):
    with patch.object(s,'ensure_runner',lambda:None):result=s.create_job({'kind':'subtitle','ids':[pid],**body})
    return s.JOBS[result['id']]
def run(job):s.worker(job['id'],job['ids'],job['kind'],job['config']);return job

try:
    folder=BASE/'source';folder.mkdir()
    first=folder/'01.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=size=320x180:rate=10:duration=1.2','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(first)])
    import shutil
    for n in range(2,7):shutil.copy2(first,folder/f'{n:02d}.mp4')
    pid=s.scan(str(folder))['projects'][0]['id'];project=s.get_project(pid);project['rights']=True
    paths=[v['path'] for v in project['videos']];hashes={p:s.sha256(p) for p in paths}
    s.STATE['config'].update(output=str(BASE/'output'),subtitleMode='local',subtitleFirst=1,parallel=1)
    job=create(pid)
    check('standalone_defaults_to_all_six_not_legacy_first_one',job['options']['subtitleAllSelected'] and len(job['options']['sourceVideoPaths'][pid])==6)
    check('selection_is_frozen_in_job',job['options']['sourceVideoPaths'][pid]==paths)
    run(job)
    files=[a['path'] for a in project['artifacts'] if a['job']==job['id']]
    check('six_files_processed_continuously',job['status']=='completed' and len(files)==6)
    check('whole_duration_and_audio_preserved',all(abs(s.probe(p)['duration']-1.2)<.11 and s.probe(p)['audio'] for p in files))
    current=run(create(pid,sourceVideoPaths={pid:[paths[4]]}))
    check('current_episode_processes_only_the_selected_file',current['status']=='completed' and current['options']['sourceVideoPaths'][pid]==[paths[4]] and sum(a['job']==current['id'] for a in project['artifacts'])==1)
    selected=[paths[5],paths[1]];ordered=run(create(pid,sourceVideoPaths={pid:selected}))
    check('free_selection_keeps_order_and_excludes_others',ordered['status']=='completed' and ordered['options']['sourceVideoPaths'][pid]==selected)
    s.STATE['config'].update(subtitleMode='vsr',vsrRoot='',vsrPython='')
    try:create(pid)
    except ValueError as error:check('missing_engine_rejected_before_enqueue','本地AI去字幕引擎' in str(error))
    else:raise AssertionError('Missing engine accepted')
    engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'))
    s.STATE['config'].update(subtitleMode='vsr',vsrRoot=engine['root'],vsrPython=engine['python'],vsrMode='sttn-auto')
    # Controlled engine failures use real playable inputs; no model calls here.
    broken=create(pid,sourceVideoPaths={pid:[paths[0]]})
    with patch.object(s,'run_process',lambda *a,**k:b''):run(broken)
    check('silent_engine_without_output_is_not_completed',broken['status']=='failed' and '有效视频' in broken['error'] and not any(a['job']==broken['id'] for a in project['artifacts']))
    invalid=create(pid,sourceVideoPaths={pid:[paths[1]]})
    def corrupt(command,*a,**k):Path(command[command.index('--output')+1]).write_bytes(b'not-video'*100);return b''
    with patch.object(s,'run_process',corrupt):run(invalid)
    check('invalid_engine_output_reports_actionable_failure',invalid['status']=='failed' and 'AI输出视频无法读取' in invalid['error'])
    recovery=create(pid,sourceVideoPaths={pid:[paths[0],paths[1],paths[2]]});calls=[]
    def partial(command,*a,**k):
        calls.append(command[command.index('--input')+1])
        if len(calls)==2:raise RuntimeError('controlled interruption after first full video')
        shutil.copy2(command[command.index('--input')+1],command[command.index('--output')+1]);return b''
    with patch.object(s,'run_process',partial):run(recovery)
    check('partial_failure_preserves_first_completed_episode',recovery['status']=='failed' and len(recovery['checkpoints'])==1)
    completed=s.cached(recovery['id'],f'{pid}:subtitle:0')[0];completed_stat=completed.stat().st_mtime_ns
    calls.clear()
    def finish(command,*a,**k):calls.append(command[command.index('--input')+1]);shutil.copy2(calls[-1],command[command.index('--output')+1]);return b''
    with patch.object(s,'ensure_runner',lambda:None):s.control_job(recovery['id'],'resume')
    with patch.object(s,'run_process',finish):run(recovery)
    check('resume_automatically_handles_remaining_two_only',recovery['status']=='completed' and calls==[paths[1],paths[2]] and completed.stat().st_mtime_ns==completed_stat)
    # Simulate upstream losing audio, with real FFmpeg restoration in the app.
    silent=BASE/'silent.mp4';s.ff(['-i',str(first),'-an','-c:v','copy',str(silent)])
    audio_job=create(pid,sourceVideoPaths={pid:[paths[3]]});original_run=s.run_process
    def no_audio(command,*a,**k):
        if '--inpaint-mode' in command:shutil.copy2(silent,command[command.index('--output')+1]);return b''
        return original_run(command,*a,**k)
    with patch.object(s,'run_process',no_audio):run(audio_job)
    audio_result=next(a for a in project['artifacts'] if a['job']==audio_job['id'])
    check('missing_audio_is_recovered_without_reencoding_video',audio_job['status']=='completed' and s.probe(audio_result['path'])['audio'])
    check('all_original_media_unchanged',all(s.sha256(p)==digest for p,digest in hashes.items()))

    if args.real_ai:
        source=args.source or Path(json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source'])
        assert source.is_file(),'Real subtitle sample missing'
        source_hash=s.sha256(source);real=BASE/'real-source';real.mkdir()
        # A looped, scaled fixture deliberately exceeds both preview limits.
        # It tests full-duration neural inference, not a client feature-film benchmark.
        long=real/'第01集-36秒完整视频.mp4';short=real/'第02集-12秒完整视频.mp4'
        s.ff(['-stream_loop','2','-i',str(source),'-vf','scale=640:368','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac','-movflags','+faststart',str(long)])
        s.ff(['-i',str(source),'-vf','scale=640:368','-c:v','libx264','-preset','fast','-crf','18','-c:a','aac',str(short)])
        real_pid=s.scan(str(real))['projects'][0]['id'];real_project=s.get_project(real_pid);real_project['rights']=True
        roi={'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}
        s.STATE['config'].update(subtitleRegions=[roi],subtitleRegion=roi,subtitleFirst=1)
        real_job=create(real_pid);run(real_job)
        check('real_sttn_whole_series_completed',real_job['status']=='completed')
        artifacts=[a for a in real_project['artifacts'] if a['job']==real_job['id'] and a['kind']=='AI字幕处理']
        check('real_ai_continues_second_episode_beyond_first_one',len(artifacts)==2)
        pairs=[]
        for video,artifact in zip(real_project['videos'],artifacts):
            output=artifact['path'];meta=s.probe(output)
            check('real_full_duration_'+video['name'],abs(meta['duration']-video['duration'])<.15 and meta['duration']>10 and meta['audio'])
            decoded=s.run_process([s.FFMPEG,'-hide_banner','-loglevel','error','-nostats','-i',output,'-progress','pipe:1','-f','null','-'])
            import re
            frames=int(re.findall(rb'^frame=(\d+)',decoded,re.M)[-1])
            check('real_decodes_all_frames_'+video['name'],abs(frames-round(video['duration']*30))<=1)
            pairs.append({'source':video['path'],'output':output,'metadata':meta,'decodedFrames':frames})
        comparison=BASE/'整片去字幕-实际AI前后对比.png'
        s.ff(['-ss','28.5','-i',str(long),'-ss','28.5','-i',artifacts[0]['path'],'-filter_complex','[0:v][1:v]hstack=inputs=2','-frames:v','1','-update','1',str(comparison)])
        check('supplied_original_unchanged',s.sha256(source)==source_hash)
        report.update(projectId=real_pid,jobId=real_job['id'],media=pairs,comparison=str(comparison),sourceSHA256=source_hash,fixture='12.07s supplied sample looped 3 times at 640x368; two full neural model runs',region=roi)
    report['ok']=True
finally:
    s.shutdown_jobs()
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/subtitle-full-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(checks),'report':str(BASE/'report.json')},ensure_ascii=False),flush=True)
