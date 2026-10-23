"""Compare both production encode plans with the same real public episodes/GPU."""
from pathlib import Path
import os,sys,tempfile,json,time,threading,copy,re,math,shutil
ROOT=Path(__file__).resolve().parent;sys.dont_write_bytecode=True
BASE=Path(tempfile.mkdtemp(prefix='real-series-performance-',dir=ROOT/'tmp'));os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT/'release/v0.8.2/漫剧工坊/_internal'),str(ROOT/'vendor')];sys.frozen=True
import server as s
assert s.__file__.endswith('.pyd')
token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0);s.licensing.activate(s.DATA,token)
live=json.loads((ROOT/'tmp/customer-download-closure-live.json').read_text('utf-8'));archive=next((Path(live['base'])/'红果').iterdir())
records=json.loads((archive/'下载记录.json').read_text('utf-8'));source=BASE/'source';source.mkdir()
for item in records:shutil.copy2(archive/item['filename'],source/item['filename'])
p=s.scan(str(source))['projects'][0];before={v['path']:s.sha256(v['path']) for v in p['videos']}
cfg=s.validate_config(s.STATE['config']|{'output':str(BASE/'output'),'width':1080,'height':1920,'parallel':2,'gpu':True,'segmentSeconds':40,'regroup':True,
    'autoText':False,'autoCover':False,'autoRecords':False,'autoCost':False,'subtitleAuto':False,'pipelineHighlight':False,'speed':1,'brightness':0,'contrast':1,'saturation':1,'cropPercent':0,'markAI':False})
s.STATE['config']=cfg;checks=[];results={}
def check(name,value=True):assert value,name;checks.append(name)
env=s.environment(force=True);check('actual_gpu_available',env['gpu']['available'])
for version,label in [(1,'legacy_same_gpu'),(2,'single_encode_same_gpu')]:
    jid=s.uuid.uuid4().hex[:12];j={'id':jid,'kind':'transcode','ids':[p['id']],'options':{'encodingPlanVersion':version},'config':copy.deepcopy(cfg),
        'sourceSnapshot':s.source_snapshot([p['id']]),'cancel':threading.Event(),'processes':set(),'checkpoints':{},'completedStages':[],'status':'queued','created':time.time()};s.JOBS[jid]=j
    begun=time.monotonic();worker=threading.Thread(target=s.worker,args=(jid,[p['id']],'transcode',cfg));worker.start();last=None
    while worker.is_alive():
        worker.join(5);now=j.get('stage')
        if now!=last:print(json.dumps({'plan':version,'seconds':round(time.monotonic()-begun,2),'stage':now},ensure_ascii=False),flush=True);last=now
        if time.monotonic()-begun>1800:j['cancel'].set()
    seconds=time.monotonic()-begun
    check(label+'_completed',j['status']=='completed')
    files=s.get_project(p['id'])['finalVideoPaths'];details=[s.probe(f) for f in files];counts=[];audio_deltas=[]
    for f,d in zip(files,details):
        raw=s.ff(['-i',str(f),'-map','0:v:0','-c:v','copy','-an','-progress','pipe:1','-f','null','-']);frames=re.findall(rb'^frame=(\d+)',raw,re.M);counts.append(int(frames[-1]))
        pcm=s.ff(['-i',str(f),'-map','0:a:0','-ac','1','-ar','8000','-f','s16le','-']);audio_deltas.append(abs(len(pcm)/16000-counts[-1]/30))
    expected=sum(round(v['duration']*30) for v in p['videos']);segments=math.ceil(expected/1200)
    check(label+'_all_outputs_have_audio_and_1080p',all(d['audio'] and (d['width'],d['height'])==(1080,1920) for d in details))
    check(label+'_expected_segment_count',len(files)==segments)
    check(label+'_frame_count_within_one_per_input',abs(sum(counts)-expected)<=len(p['videos']))
    check(label+'_audio_alignment',max(audio_deltas)<.12)
    check(label+'_actually_used_same_gpu',j['encoding']['videoEncoder']=='h264_nvenc' and not j.get('gpuFallback'))
    if version==2:
        check('new_plan_reuses_video_stream',j['encoding']['regroupMode']=='video_copy')
        check('new_plan_exact_40_second_boundaries',counts[:-1]==[1200]*(len(counts)-1) and sum(counts)==expected)
        # Decode beginning, middle and end samples; saves actual output stills for visual review.
        samples=[]
        for index in (0,len(files)//2,len(files)-1):
            target=BASE/f'actual-output-{index+1:03}.png';s.ff(['-ss','0.2','-i',files[index],'-frames:v','1',str(target)]);samples.append(str(target))
        results['samples']=samples
    results[label]={'seconds':round(seconds,3),'outputs':len(files),'frames':sum(counts),'framesPerOutput':counts,'maxAudioVideoDeltaSeconds':round(max(audio_deltas),4),'encoding':j['encoding'],'files':files}
    print(json.dumps({'event':'plan_complete','plan':version,'seconds':round(seconds,3),'outputs':len(files)},ensure_ascii=False),flush=True)
check('original_source_hashes_unchanged',all(s.sha256(path)==digest for path,digest in before.items()))
report={'compiled':True,'realSourceClips':len(p['videos']),'fullCustomerSeries':False,'mediaSeconds':round(sum(v['duration'] for v in p['videos']),3),
    'resolution':[1080,1920],'sameHardwareSameSettings':True,'gpu':env['gpu'],'base':str(BASE),'passed':len(checks),'checks':checks,'results':results,
    'timeReductionPercent':round(100*(1-results['single_encode_same_gpu']['seconds']/results['legacy_same_gpu']['seconds']),1)}
(ROOT/'tmp/real-series-performance-compiled.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({k:report[k] for k in ('passed','realSourceClips','mediaSeconds','timeReductionPercent','base')},ensure_ascii=False),flush=True)
