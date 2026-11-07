"""Kill only our child app and its encoders mid-render, then resume via its API."""
from pathlib import Path
import copy,hashlib,http.cookiejar,json,os,subprocess,sys,time,urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
previous=Path(json.loads((ROOT/'tmp/real-promotion-local-latest.json').read_text('utf-8'))['base'])
source=json.loads((previous/'input-manifest.json').read_text('utf-8'))
analysis=json.loads((previous/'核选方案.json').read_text('utf-8'))
BASE=ROOT/'output'/('混剪中断恢复验收-'+time.strftime('%Y%m%d-%H%M%S'));BASE.mkdir(parents=True)
seed={'project':source['project'],'analysis':analysis}
seedpath=BASE/'seed.json';seedpath.write_text(json.dumps(seed,ensure_ascii=False),'utf-8')
(ROOT/'tmp/real-promotion-recovery-latest.json').write_text(json.dumps({'base':str(BASE)},ensure_ascii=False),'utf-8')
flags=getattr(subprocess,'CREATE_NO_WINDOW',0);proc=None;log=None;checks=[]
report={'base':str(BASE),'realMedia':True,'hardStop':True,'externalCalls':False,'platformPublished':False}
def read(path):
    try:return json.loads(path.read_text('utf-8'))
    except (OSError,ValueError):return None
def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def identity(path):
    p=Path(path);return {'bytes':p.stat().st_size,'mtimeNs':p.stat().st_mtime_ns,'sha256':digest(p)}
def start(resume=False):
    global proc,log
    if (BASE/'host.json').is_file():(BASE/'host.json').unlink()
    log=(BASE/('resumed-process.log' if resume else 'initial-process.log')).open('wb')
    proc=subprocess.Popen([sys.executable,str(ROOT/'tools/serve_real_promotion_recovery.py'),'--base',str(BASE),*(['--resume'] if resume else [])],cwd=ROOT,
        stdout=log,stderr=log,creationflags=flags)
    end=time.monotonic()+45
    while time.monotonic()<end:
        if proc.poll() is not None:raise RuntimeError('Isolated host exited; inspect its process log')
        host=read(BASE/'host.json')
        if host and host['pid']==proc.pid:return host
        time.sleep(.1)
    raise TimeoutError('Isolated host did not start')
def stop():
    global proc,log
    if proc is not None and proc.poll() is None:
        # PID comes directly from our Popen handle; no user app is enumerated or killed.
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,creationflags=flags,check=True)
        proc.wait(timeout=15)
    if log:log.close();log=None
def client_for(host):
    client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    client.open(host['launch'],timeout=15).read()
    def api(name,body=None):
        req=urllib.request.Request(host['url']+'/api/'+name,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json','X-Local-Client':'1'})
        with client.open(req,timeout=30) as response:return json.load(response)
    return api
begun=time.monotonic()
try:
    host=start();jid=host['jobId'];seed['jobId']=jid;seedpath.write_text(json.dumps(seed,ensure_ascii=False),'utf-8')
    firstkey=source['project']['id']+':promotion-mix:'+analysis['clips'][0]['id']
    secondkey=source['project']['id']+':promotion-mix:'+analysis['clips'][1]['id']
    end=time.monotonic()+240;before={};partial=None
    while time.monotonic()<end:
        if proc.poll() is not None:raise RuntimeError('Initial host stopped unexpectedly')
        jobs=read(BASE/'data/jobs.json') or []
        job=next((j for j in jobs if j['id']==jid),{})
        points=job.get('checkpoints',{})
        if job.get('status') in ('failed','completed'):raise RuntimeError('Job stopped before intended mid-render checkpoint: '+str(job.get('error',job.get('status'))))
        first=points.get(firstkey)
        if first:
            firstpath=Path(first['files'][0]['path']);work=firstpath.parent
            partial=work/'part_01_01.mp4'
            if partial.is_file() and partial.stat().st_size>0 and secondkey not in points:
                completed_paths=[firstpath,work/'part_01_00.mp4']
                before={str(p):identity(p) for p in completed_paths}
                report['interruptedJob']={'id':jid,'status':job['status'],'stage':job['stage'],'completedCheckpointKeys':list(points)}
                report['inProgressPart']=str(partial)
                break
        time.sleep(.1)
    else:raise TimeoutError('No mid-render interruption point observed')
    stop();checks.append('hard_killed_owned_source_app_and_encoder_mid_second_clip')
    report['filesBeforeRestart']=before
    print('HARD_STOP_CAPTURED '+json.dumps({'completedFiles':len(before),'jobId':jid}),flush=True)
    restarted=start(True);assert restarted['loadedStatus']=='interrupted',restarted['loadedStatus']
    checks.append('restart_reports_interrupted_instead_of_completed')
    api=client_for(restarted)
    response=api('jobs/control',{'id':jid,'action':'resume'});checks.append('resumed_via_real_application_control_api')
    end=time.monotonic()+240
    while time.monotonic()<end:
        state=api('state');job=next(j for j in state['jobs'] if j['id']==jid)
        if job['status'] in ('completed','failed','cancelled'):
            assert job['status']=='completed',job.get('error');break
        time.sleep(.5)
    else:raise TimeoutError('Resumed mix did not complete')
    finalproject=next(p for p in state['projects'] if p['id']==source['project']['id'])
    clips=finalproject['promotionClips'];assert len(clips)==2 and len({c['id'] for c in clips})==2
    checks.append('both_output_clips_registered_once_without_duplicates')
    after={p:identity(p) for p in before}
    changed=[p for p in before if after[p]!=before[p]]
    report['completedFilesReencoded']=changed
    for clip in clips:
        subprocess.run([os.environ.get('FFMPEG_EXE') or str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe'))),'-hide_banner','-loglevel','error','-i',clip['path'],'-map','0:v:0','-map','0:a:0','-f','null','-'],check=True,capture_output=True,creationflags=flags)
    checks.append('resumed_outputs_video_and_audio_decode_completely')
    assert source['originalHashes']=={p:digest(p) for p in source['originalHashes']}
    checks.append('all_three_original_episodes_unchanged')
    assert not state.get('promotionTasks');checks.append('recovery_does_not_create_platform_publish_tasks')
    assert not changed,'Completed intermediate was re-encoded: '+', '.join(Path(p).name for p in changed)
    checks.append('completed_clip_and_intermediate_reused_with_same_hash_and_mtime')
    report.update(ok=True,clips=clips,jobStatus=job['status'])
except Exception as error:
    report.update(ok=False,error=str(error));raise
finally:
    stop();report.update(checks=checks,seconds=round(time.monotonic()-begun,3))
    (BASE/'recovery-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('REAL_HARD_STOP_REPORT '+json.dumps({'ok':report.get('ok'),'checks':len(checks),'seconds':report['seconds'],'report':str(BASE/'recovery-report.json')},ensure_ascii=False),flush=True)
