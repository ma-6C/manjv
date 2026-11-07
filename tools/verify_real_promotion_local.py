"""Real local ASR and mix acceptance, without remote LLM or platform requests."""
from pathlib import Path
import argparse,copy,json,os,sys,threading,time,hashlib,subprocess,re
ROOT=Path(__file__).resolve().parents[1]
sys.stdout.reconfigure(encoding='utf-8')
parser=argparse.ArgumentParser()
parser.add_argument('--phase',choices=['transcribe','render'],default='transcribe')
parser.add_argument('--plan',type=Path)
parser.add_argument('--resume',action='store_true',help='Verify restoration of existing render checkpoints in a new process')
args=parser.parse_args()
pointer=ROOT/'tmp/real-promotion-local-latest.json'
if args.phase=='transcribe':
    BASE=ROOT/'output'/('真实混剪验收-'+time.strftime('%Y%m%d-%H%M%S'))
    BASE.mkdir(parents=True)
    state=json.loads((ROOT/'data/state.json').read_text('utf-8'))
    project=copy.deepcopy(next(p for p in state['projects'] if p['id']=='dd061476f4204e87'))
    original_hashes={v['path']:hashlib.file_digest(Path(v['path']).open('rb'),'sha256').hexdigest() for v in project['videos']}
    seed={'base':str(BASE),'project':project,'originalHashes':original_hashes,'asrOptions':state.get('jianyingOptions',{})}
    (BASE/'input-manifest.json').write_text(json.dumps(seed,ensure_ascii=False,indent=2),'utf-8')
    pointer.write_text(json.dumps({'base':str(BASE)},ensure_ascii=False),'utf-8')
else:
    BASE=Path(json.loads(pointer.read_text('utf-8'))['base'])
    seed=json.loads((BASE/'input-manifest.json').read_text('utf-8'));project=seed['project']
os.environ['MANJU_DATA']=str(BASE/'isolated-data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s,promotion_studio as studio
restored_project=next((p for p in s.STATE['projects'] if p['id']==project['id']),None)
restored_job=copy.deepcopy({k:v for k,v in s.JOBS.get('real-local-render',{}).items() if k not in ('cancel','processes')})
if args.resume:
    if args.phase!='render' or not restored_project or not restored_job:raise ValueError('没有可恢复的真实混剪验收任务')
    project=restored_project
else:
    project['artifacts']=[];project['promotionClips']=[]
cfg=s.validate_config(copy.deepcopy(s.DEFAULT)|{'output':str(BASE/'成片'),'gpu':False})
s.STATE['projects']=[project];s.STATE['jianyingOptions']=seed['asrOptions'];s.STATE['config']=cfg
opts=studio.settings(project,{'count':2,'seconds':60,'cta':'精彩剧情，未完待续'},[])
sources=studio.checked_sources(project,opts)
jid='real-local-'+args.phase
s.JOBS[jid]={'id':jid,'kind':'promotion_analyse' if args.phase=='transcribe' else 'promotion_render','ids':[project['id']],
 'status':'running','stage':'真实素材本地验收','progress':0,'cancel':threading.Event(),'processes':set(),
 'config':cfg,'options':{'studio':opts},'checkpoints':{},'created':time.time(),'telemetry':{'rows':[]},'accountIds':[]}
if args.resume:
    s.JOBS[jid].update(restored_job,status='running',cancel=threading.Event(),processes=set())
s.save()
report_path=BASE/('转写验收.json' if args.phase=='transcribe' else '混剪验收.json')
if args.resume:report_path=BASE/'缓存恢复验收.json'
report={'phase':args.phase,'project':project['name'],'base':str(BASE),'remoteLLMCalled':False,'platformPublished':False,
        'sourceSeconds':round(sum(v['duration'] for v in sources),3)}
begun=time.monotonic()
try:
    if args.phase=='transcribe':
        work=BASE/'真实台词';work.mkdir(exist_ok=True)
        print('REAL_ASR_START '+json.dumps({'episodes':len(sources),'seconds':report['sourceSeconds']},ensure_ascii=False),flush=True)
        cues=studio.transcripts(s,project,cfg,jid,sources,work)
        result={'sources':sources,'cues':cues}
        (BASE/'转写台词.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
        lines=[]
        for i,rows in enumerate(cues):
            lines.append('\n### '+sources[i]['name'])
            lines.extend(f"[{r['start']:.2f} - {r['end']:.2f}] {r['text']}" for r in rows)
        (BASE/'台词审阅.txt').write_text('\n'.join(lines),'utf-8')
        report.update(ok=True,episodeCueCounts=[len(c) for c in cues],transcript=str(BASE/'转写台词.json'))
        report['runtimeAttempts']=[json.loads(p.read_text('utf-8')) for p in work.glob('*/AI任务/asr-attempts.json')]
    else:
        if not args.plan and not args.resume:raise ValueError('请提供依据真实台词核选的计划')
        transcript=json.loads((BASE/'转写台词.json').read_text('utf-8'))
        sources=transcript['sources'];studio.check_sources(sources)
        if args.resume:
            analysis=json.loads((BASE/'核选方案.json').read_text('utf-8'))
            before_media={str(p):(s.sha256(p),p.stat().st_mtime_ns) for p in (BASE/'成片').rglob('*.mp4')}
        else:
            raw=json.loads(args.plan.read_text('utf-8'))
            plans=studio.validate_plans(raw,sources,2,60)
            analysis={'id':'real-transcript-reviewed-plan','sources':sources,'clips':plans,'settings':opts,
                      'basis':'real_asr_reviewed_by_assistant','model':'not_product_text_api','createdAt':time.time()}
            (BASE/'核选方案.json').write_text(json.dumps(analysis,ensure_ascii=False,indent=2),'utf-8')
        clips=studio.render(s,project,cfg,jid,analysis)
        if args.resume:
            after_media={str(p):(s.sha256(p),p.stat().st_mtime_ns) for p in (BASE/'成片').rglob('*.mp4')}
            assert before_media==after_media,'Restored render unexpectedly re-encoded media'
            report.update(checkpointsRestored=len(restored_job['checkpoints']),mediaFilesUnchanged=True)
        probes=[]
        for clip in clips:
            meta=s.probe(clip['path'])
            s.ff(['-i',clip['path'],'-map','0:v:0','-map','0:a:0','-f','null','-'],jid)
            measured=subprocess.run([s.FFMPEG,'-hide_banner','-i',clip['path'],'-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-vn','-sn','-dn','-f','null','-'],capture_output=True,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            metrics=json.loads(re.findall(r'\{\s*"input_i".*?\}',measured.stderr.decode('utf-8','replace'),re.S)[-1])
            meta['audioLoudness']=metrics
            if not -18<=float(metrics['input_i'])<=-14:raise ValueError('成片响度偏离目标')
            if float(metrics['input_tp'])>0:raise ValueError('成片音频存在峰值超限')
            probes.append(meta)
        assert not s.STATE.get('promotionTasks'), 'Unexpected publishing tasks'
        report.update(ok=True,clips=clips,metadata=probes,allFramesDecoded=True,
                      planBasis='Assistant reviewed real local ASR transcript; product text API not exercised')
        review_sources=[dict(meta,path=clip['path'],name=clip['title'],stat=studio.snapshot(clip['path']),subtitleStat=None) for clip,meta in zip(clips,probes)]
        review_dir=BASE/'成片台词复核';review_dir.mkdir(exist_ok=True)
        reviewed=studio.transcripts(s,project,cfg,jid,review_sources,review_dir)
        (BASE/'成片台词复核.json').write_text(json.dumps(reviewed,ensure_ascii=False,indent=2),'utf-8')
        lines=[]
        for i,rows in enumerate(reviewed):
            lines.append('\n### '+clips[i]['title'])
            lines.extend(f"[{r['start']:.2f} - {r['end']:.2f}] {r['text']}" for r in rows)
        (BASE/'成片台词复核.txt').write_text('\n'.join(lines),'utf-8')
    after={path:s.sha256(path) for path in seed['originalHashes']}
    assert after==seed['originalHashes'],'Source media changed'
    report['sourceUnchanged']=True
    s.JOBS[jid].update(status='completed',progress=100,stage='真实本地验收完成')
except Exception as error:
    report.update(ok=False,error=s.diagnostic_text(str(error)))
    s.JOBS[jid].update(status='failed',error=s.diagnostic_text(str(error)))
    raise
finally:
    report['seconds']=round(time.monotonic()-begun,3)
    report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    s.save()
    print('REAL_LOCAL_REPORT '+json.dumps({'ok':report.get('ok'),'phase':args.phase,'seconds':report['seconds'],'report':str(report_path)},ensure_ascii=False),flush=True)
