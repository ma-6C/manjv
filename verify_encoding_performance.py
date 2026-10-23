"""Legacy/two-pass versus new/single-video-encode, exact decoded frames and audio."""
from pathlib import Path
import os,sys,tempfile,json,copy,time,threading,math
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;VERSION='v0.8.2';COMPILED='--compiled' in sys.argv;sys.dont_write_bytecode=True
BASE=Path(tempfile.mkdtemp(prefix='encoding-082-',dir=ROOT/'tmp'));os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=([str(ROOT/'release'/VERSION/'漫剧工坊/_internal')] if COMPILED else [])+[str(ROOT/'vendor')]
if COMPILED:sys.frozen=True
import server as s
if COMPILED:
    import re
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0);s.licensing.activate(s.DATA,token)
fixture=json.loads((ROOT/'tmp/single-encode-prototype-report.json').read_text('utf-8'));p=s.scan(str(Path(fixture['base'])/'source'))['projects'][0]
cfg=s.STATE['config']|{'output':str(BASE/'output'),'width':640,'height':360,'parallel':2,'gpu':False,'segmentSeconds':3,'regroup':True,'autoText':False,'autoCover':False,'autoRecords':False,'speed':1}
s.STATE['config']=s.validate_config(cfg);before={v['path']:s.sha256(v['path']) for v in p['videos']};checks=[];results={}
def check(name,value=True):assert value,name;checks.append(name)
def hashes(path):
    raw=s.ff(['-i',str(path),'-map','0:v:0','-f','framemd5','-']).decode()
    return [line.rsplit(',',1)[-1].strip() for line in raw.splitlines() if line and not line.startswith('#')]
def job(version):
    jid=s.uuid.uuid4().hex[:12];j={'id':jid,'kind':'transcode','ids':[p['id']],'options':{'encodingPlanVersion':version},'config':copy.deepcopy(cfg),'sourceSnapshot':s.source_snapshot([p['id']]),'cancel':threading.Event(),'processes':set(),'checkpoints':{},'completedStages':[],'status':'queued','created':time.time()};s.JOBS[jid]=j
    with patch.object(s.shutil,'rmtree',lambda path:None):
        begun=time.monotonic();s.worker(jid,[p['id']],'transcode',cfg);seconds=time.monotonic()-begun
    assert j['status']=='completed',j.get('error')
    return j,seconds
for version,label in [(1,'legacy'),(2,'single_video_encode')]:
    j,seconds=job(version);files=p['finalVideoPaths'];frames=[hashes(f) for f in files]
    result={'seconds':round(seconds,3),'outputCount':len(files),'framesPerOutput':[len(x) for x in frames],'frames':sum(map(len,frames)),'encoding':j.get('encoding')};results[label]=result
    check(label+'_all_segments_have_audio',all(s.probe(f)['audio'] for f in files))
    check(label+'_precise_frame_boundaries',result['framesPerOutput']==[90]*14+[18])
    if version==2:
        normalized=[s.cached(j['id'],f'{p["id"]}:encode-v2:{i}')[0] for i in range(26)]
        check('new_plan_uses_video_copy',j['encoding']['regroupMode']=='video_copy')
        check('no_video_frame_loss_or_second_generation_change',[x for f in normalized for x in hashes(f)]==[x for part in frames for x in part])
        audio_deltas=[]
        for f,n in zip(files,result['framesPerOutput']):
            pcm=s.ff(['-i',f,'-map','0:a:0','-ac','1','-ar','8000','-f','s16le','-']);audio_deltas.append(abs(len(pcm)/16000-n/30))
        check('segment_audio_matches_video_within_aac_frame_tolerance',max(audio_deltas)<.09)
        stamps={str(f):f.stat().st_mtime_ns for f in normalized};j['checkpoints'].pop(f'{p["id"]}:video');j['checkpoints'].pop(f'{p["id"]}:project-done')
        with patch.object(s.shutil,'rmtree',lambda path:None):s.worker(j['id'],[p['id']],'transcode',cfg)
        check('resume_reuses_prepared_video_and_frame_plan',j['status']=='completed' and all(Path(f).stat().st_mtime_ns==stamp for f,stamp in stamps.items()))
check('original_files_unchanged',all(s.sha256(path)==digest for path,digest in before.items()))
check('legacy_tasks_keep_legacy_plan',results['legacy']['encoding']['planVersion']==1)
report={'version':VERSION,'compiled':COMPILED,'checks':checks,'passed':len(checks),'base':str(BASE),'syntheticClips':26,'mediaSeconds':42.6,'results':results,'timeReductionPercent':round((1-results['single_video_encode']['seconds']/results['legacy']['seconds'])*100,1)}
(ROOT/('tmp/encoding-082-compiled.json' if COMPILED else 'tmp/encoding-082-source.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(report,ensure_ascii=False,indent=2))
