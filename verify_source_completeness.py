"""Actual truncated public media plus deterministic real-FFmpeg import acceptance."""
from pathlib import Path
from unittest.mock import patch
import copy,hashlib,json,os,shutil,sys,tempfile,threading,types
ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='source-duration-check-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'server-data');sys.dont_write_bytecode=True
COMPILED='--compiled' in sys.argv
VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.10.11'
sys.path[:0]=([str(ROOT/'release'/VERSION/'漫剧工坊/_internal')] if COMPILED else [])+[str(ROOT),str(ROOT/'vendor')]
import server as s,hongguo_source as h,source_imports as si,guoapp_source as native
if COMPILED:assert all(module.__file__.endswith('.pyd') for module in (s,si,native))
checks=[]
def check(name,condition):
    assert condition,name
    checks.append(name);print('PASS '+name,flush=True)

evidence=ROOT/'tmp/public-native-episode-completeness-20261107.json'
real_media=False
if evidence.is_file():
    recorded=json.loads(evidence.read_text('utf-8'));short=Path(recorded['download']['path'])
    real_media=short.is_file()
if not real_media:
    short=BASE/'ten-second-fixture.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=s=160x240:r=25:d=10.08','-f','lavfi','-i','sine=frequency=330:duration=10.08',
        '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(short)])
before=hashlib.sha256(short.read_bytes()).hexdigest()
real_info={'episodeId':'7660106334662052888','url':h.BASE+'/video/public/7660106334662052888/360p.mp4',
    'uploadDate':None,'duration':'PT2M47.138S'}
check('source_declaration_parses_full_167_point_138_seconds',si.declared_media_seconds(real_info)==167.138)
complete=BASE/'complete-fixture.mp4'
s.ff(['-f','lavfi','-i','testsrc2=s=160x240:r=20:d=12','-f','lavfi','-i','sine=frequency=440:duration=12',
    '-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(complete)])
core=native.Core(BASE/'native-plan');cached=core.data/'downloads'/'fixture.mp4';cached.parent.mkdir(parents=True);shutil.copy2(complete,cached)
drama={'id':'hongguo:123456','sourceId':'123456','source':'hongguo','title':'fixture'}
chapter={'id':'hongguo:123456:1234567','currentEpisode':1}
job_id=hashlib.sha256((drama['id']+'\0'+str(1)).encode()).hexdigest()[:32]
def native_call(payload):
    if payload['action']=='enqueueDownloads':return {'added':1}
    if payload['action']=='downloads':return {'jobs':[{'id':job_id,'state':'completed','bytes':cached.stat().st_size,'total':cached.stat().st_size}]}
    if payload['action']=='localPlayback':return {'local':True,'url':str(cached),'expectedDurationSeconds':167.138}
    raise AssertionError(payload['action'])
adapter=native.Adapter(core);adapter.media['guoapp-media:fixture']=(drama,chapter,1,0,1)
with patch.object(core,'call',side_effect=native_call):plan=adapter.fetch_media('guoapp-media:fixture',threading.Event(),lambda *args:None)
check('real_python_adapter_preserves_native_declared_duration',plan['expectedDurationSeconds']==167.138)
with patch.object(core,'call',return_value={'local':True,'url':str(cached)}):unknown=core.prepare_download(drama,1)
check('legacy_plan_without_duration_stays_unknown','expectedDurationSeconds' not in unknown)
with patch.object(core,'call',return_value={'local':True,'url':str(cached),'expectedDurationSeconds':float('nan')}):
    try:core.prepare_download(drama,1)
    except ValueError:pass
    else:raise AssertionError('invalid native declared duration accepted')
check('invalid_native_duration_cannot_pass_to_import',True)

def run(label,media,declared=None,native=False,info=None):
    directory=BASE/label;directory.mkdir();imported=[]
    sid='7660103833745378328' if info else '123456'
    url=('guoapp://hongguo/detail/'+sid) if native else h.BASE+'/detail?series_id='+sid
    meta={'kind':'detail','platform':'guoapp_hongguo' if native else 'hongguo_web','seriesId':sid,'url':url,'title':label,
        'intro':'duration test','coverUrl':'','episodes':[{'number':1,'playerUrl':h.BASE+'/player/'+sid}]}
    details=copy.deepcopy(info) if info else {'episodeId':'1234567','url':'https://hongguoduanju.com/video/public/1234567/360p.mp4','uploadDate':None}
    if not native and declared is not None:details['duration']=declared
    def download(address,target,cancel,progress,*a,**k):shutil.copy2(media,target);progress(target.stat().st_size,target.stat().st_size)
    def fetch(address,cancel,progress):
        progress(media.stat().st_size,media.stat().st_size)
        return {'local':True,'url':str(media),'expectedDurationSeconds':declared}
    def materialize(plan,target,cancel):shutil.copy2(media,target)
    def importer(*args):imported.append(args[2]);return 'fixture-project'
    adapter=types.SimpleNamespace(ACCESS=h.Access(interval=0),site_url=lambda value:value,Cancelled=h.Cancelled,SourceLimited=h.SourceLimited,
        valid_episode_entry=lambda *args:True,parse_player=lambda *args:copy.deepcopy(details),download=download,
        resolve_episode=lambda *args:copy.deepcopy(details),fetch_media=fetch,materialize_media=materialize)
    manager=si.ImportManager(directory/'data',importer,s.probe,adapter);manager.resolve=lambda *a,**k:copy.deepcopy(meta);manager.html=lambda *a,**k:'';manager.start_worker=lambda:None
    row=manager.get(manager.start({'url':url,'directory':str(directory),'video':True,'episodes':[1]})['id'])
    manager.run();return manager,row,imported

manager,row,imported=run('real-public-truncation',short,info=real_info)
check('real_10_second_preview_is_failed_not_completed',row['status']=='failed' and row['done']==0 and row['items'][0]['status']=='failed')
check('real_preview_never_calls_import_callback',not imported)
folder=Path(row['savedDirectory'])
check('real_preview_never_commits_or_registers_as_episode',not list(folder.glob('*.mp4')) and not list(folder.rglob('*.commit.json')) and not (folder/'下载记录.json').exists())
check('failure_explains_declared_actual_duration_and_preview_risk','167.138' in row['items'][0]['error'] and '10.' in row['items'][0]['error'] and '未入库' in row['items'][0]['error'])
_,native_row,imported=run('native-declared-plan',short,167.138,True)
check('native_plan_expected_duration_also_blocks_truncation',native_row['status']=='failed' and native_row['done']==0 and not imported)
_,conflict,imported=run('conflicting-native-duration',short,10.08,True,info=real_info)
check('short_native_plan_cannot_override_full_source_declaration',conflict['status']=='failed' and conflict['done']==0 and not imported and si.declared_media_seconds(real_info,{'expectedDurationSeconds':10.08})==167.138)
manager,good,imported=run('full-synthetic',complete,'PT12S')
check('complete_real_ffmpeg_media_imports_once',good['status']=='completed' and good['done']==1 and len(imported)==1)
manifest=Path(good['savedDirectory'])/'下载记录.json';records=json.loads(manifest.read_text('utf-8'))
check('validated_duration_is_recorded_for_future_resume',records[0]['expectedDurationSeconds']==12 and records[0]['fullDurationVerified'] is True)
records[0]['expectedDurationSeconds']=167.138;manifest.write_text(json.dumps(records),'utf-8')
new=manager.get(manager.start({'url':good['url'],'directory':good['directory'],'video':True,'episodes':[1]})['id']);manager.run()
check('cached_existing_file_is_rechecked_before_import',new['status']=='failed' and new['done']==0 and len(imported)==1)
for raw in (True,'NaN','Infinity','-1','PT','bad'):
    try:si.declared_media_seconds({'duration':raw})
    except ValueError:pass
    else:raise AssertionError('invalid declared duration accepted: '+str(raw))
check('invalid_declared_durations_cannot_disable_validation',True)
check('short_clip_tolerance_does_not_allow_two_second_loss',si.require_complete_media({'duration':12},{'duration':11.7})==12)
try:si.require_complete_media({'duration':12},{'duration':10.08})
except ValueError:check('short_clip_missing_sixteen_percent_is_rejected',True)
else:raise AssertionError('short clip truncation accepted')
check('original_real_public_media_hash_unchanged',hashlib.sha256(short.read_bytes()).hexdigest()==before)
report={'date':'2026-11-07','ok':True,'passed':len(checks),'checks':checks,'base':str(BASE),
    'compiled':COMPILED,'moduleOrigins':{module.__name__:module.__file__ for module in (s,si,native)},
    'externalCalls':False,'realTruncatedPublicMedia':real_media,'realFFmpeg':True,
    'nativeExpectedDurationTransport':'actual Python Adapter/Core contract with simulated native IPC; native Go has separate field tests',
    'unknownDurations':'No completeness is invented when the source has no reliable duration declaration.'}
(ROOT/'tmp/source-completeness-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False),flush=True)
