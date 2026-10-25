"""Real STTN/LaMa selection, full-video coverage, batch reuse and scope checks."""
from pathlib import Path
import copy,json,os,sys,tempfile,time,threading,subprocess,runpy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='local-repair-engines-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,lama_local,engine_manager
report={'base':str(BASE),'ok':False,'checks':[],'realAI':True,'installerBuilt':False};outputs={}
def check(name,value=True):assert value,name;report['checks'].append(name);print('PASS '+name,flush=True)
def create(mode,paths):
    s.STATE['config']['vsrMode']=mode
    with patch.object(s,'ensure_runner',lambda:None):jid=s.create_job({'kind':'subtitle','ids':[pid],'sourceVideoPaths':{pid:paths}})['id']
    return s.JOBS[jid]
def run(job):
    start=time.perf_counter();s.worker(job['id'],job['ids'],job['kind'],job['config']);elapsed=time.perf_counter()-start
    print('JOB '+job['config']['vsrMode']+' '+job['status']+' '+job['stage'],flush=True)
    if job['status']!='completed':raise RuntimeError(job.get('error',job['stage']))
    paths=[a['path'] for a in p['artifacts'] if a['job']==job['id']];report.setdefault('runs',[]).append({'engine':job['config']['vsrMode'],'seconds':round(elapsed,3),'worker':job.get('vsrWorker'),'outputs':paths,'jobId':job['id']})
    return paths
try:
    original=Path(json.loads((ROOT/'tmp/current-subtitle-test.json').read_text('utf-8'))['source']);original_hash=s.sha256(original)
    folder=BASE/'source';folder.mkdir();first=folder/'01.mp4';second=folder/'02.mp4'
    s.ff(['-ss','2','-i',str(original),'-t','2','-vf','scale=640:368,fps=6','-c:v','libx264','-preset','fast','-c:a','aac',str(first)])
    s.ff(['-ss','4','-i',str(original),'-t','3','-vf','scale=640:368,fps=6','-c:v','libx264','-preset','fast','-c:a','aac',str(second)])
    pid=s.scan(str(folder))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True;hashes={v['path']:s.sha256(v['path']) for v in p['videos']}
    engine=json.loads((ROOT/'engines/vsr-install.json').read_text('utf-8'));region={'x':360/1254,'y':599/720,'w':535/1254,'h':47/720}
    s.STATE['config'].update(output=str(BASE/'output'),vsrRoot=engine['root'],vsrPython=engine['python'],vsrReuseWorker=True,subtitleMode='vsr',subtitleRegions=[region],subtitleRegion=region,lamaDevice='auto')
    a=create('sttn-auto',[str(first)]);b=create('lama-box',[str(first),str(second)])
    check('each_queued_job_freezes_its_engine',a['config']['vsrMode']=='sttn-auto' and b['config']['vsrMode']=='lama-box')
    outputs['sttn']=run(a);check('first_task_uses_STTN',a['localRepairEngine']=='sttn-auto')
    sttn_process=s.vsr_pool.POOL.client.process
    outputs['lama']=run(b);check('second_task_uses_LaMa',b['localRepairEngine']=='lama-box')
    check('switch_releases_previous_engine',sttn_process.poll() is not None and s.vsr_pool.POOL.client is None)
    stats=b['vsrWorker'];check('LaMa_reuses_real_model_across_two_different_clips',stats['modelLoads']==1 and stats['modelCacheHits']>=1 and stats['completedVideos']==2 and stats['frames']==18)
    check('full_duration_and_original_audio',all(abs(s.probe(path)['duration']-seconds)<.15 and s.probe(path)['audio'] for path,seconds in [(outputs['sttn'][0],2),(outputs['lama'][0],2),(outputs['lama'][1],3)]))
    for path in outputs['sttn']+outputs['lama']:s.run_process([s.FFMPEG,'-v','error','-i',path,'-f','null','-'])
    check('all_outputs_fully_decode')
    # Compare raw decoded frames; codec losses are allowed, but outside the box
    # should retain source detail rather than being replaced with model output.
    import numpy as np
    def frame(path):
        data=subprocess.check_output([s.FFMPEG,'-v','error','-ss','0.8','-i',str(path),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-']);return np.frombuffer(data,np.uint8).reshape(368,640,3)
    before=frame(first);after=frame(outputs['lama'][0]);difference=np.abs(before.astype(float)-after.astype(float));mask=np.zeros((368,640),bool)
    y0,y1,x0,x1=round(region['y']*368),round((region['y']+region['h'])*368),round(region['x']*640),round((region['x']+region['w'])*640);mask[y0:y1,x0:x1]=True
    outside=float(difference[~mask].mean());inside=float(difference[mask].mean());report['pixelDifference']={'outsideMean':outside,'insideMean':inside}
    check('boxed_area_is_repaired_while_outside_is_preserved',outside<5 and inside>outside*2)
    from PIL import Image
    image=Image.new('RGB',(1280,368));image.paste(Image.fromarray(before),(0,0));image.paste(Image.fromarray(after),(640,0));image.save(BASE/'LaMa-原片与修复对比.png')
    s.STATE['config']['vsrMode']='lama-box';s.save()
    with patch.object(engine_manager,'active',return_value={'root':engine['root'],'python':engine['python'],'verifiedMode':'sttn-auto'}):reloaded=runpy.run_path(str(ROOT/'server.py'),run_name='isolated_restart_check')
    check('restart_does_not_replace_user_engine_with_bundle_default',reloaded['STATE']['config']['vsrMode']=='lama-box')
    before_jobs=len(s.JOBS)
    with patch.object(lama_local,'ready',return_value=False):
        try:create('lama-box',[str(first)])
        except ValueError:check('missing_second_model_blocks_before_queueing',len(s.JOBS)==before_jobs)
        else:raise AssertionError('Missing model accepted')
    # CPU selection is a separate real path and must keep the existing STTN option.
    s.STATE['config']['lamaDevice']='cpu';cpu=create('lama-box',[str(first)]);outputs['cpu']=run(cpu)
    check('CPU_only_LaMa_repairs_full_clip',cpu['vsrWorker']['device']=='cpu' and s.probe(outputs['cpu'][0])['audio'])
    check('original_sources_unchanged',s.sha256(original)==original_hash and all(s.sha256(path)==value for path,value in hashes.items()))
    report.update(ok=True,projectId=pid,outputs=outputs,region=region,fixture='Two different 2s/3s clips, 640x368, 6fps; not a feature-film throughput benchmark')
finally:
    s.shutdown_jobs();(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/local-repair-engines-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'ok':report['ok'],'checks':len(report['checks']),'base':str(BASE)},ensure_ascii=False),flush=True)
