"""Fault recovery, selected production and versioned hook inputs; isolated, no network."""
from pathlib import Path
import sys,os,tempfile,copy,json,types,re,threading,time,shutil
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.4';COMPILED='--compiled' in sys.argv
BASE=Path(tempfile.mkdtemp(prefix='workflow-081-',dir=ROOT/'tmp'));os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')));sys.dont_write_bytecode=True
sys.path[:0]=([str(ROOT/'release'/VERSION/'漫剧工坊/_internal')] if COMPILED else [])+[str(ROOT/'vendor')]
if COMPILED:sys.frozen=True
import source_imports as si,server as s
if COMPILED:
    assert s.__file__.endswith('.pyd')
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    s.licensing.activate(s.DATA,token)
checks=[]
def check(name,value=True):assert value,name;checks.append(name)
class Cancelled(Exception):pass
class Limited(ValueError):pass
class Access:
    def configure(self,data):pass
    def snapshot(self):return {}
    def resume(self):pass
meta={'platform':'hongguo_web','seriesId':'123','title':'隔离恢复测试','intro':'test','episodes':[{'number':n,'playerUrl':'https://hongguoduanju.com/player/123/'+str(n)} for n in range(1,7)],'coverUrl':''}
def manager(label,callback=lambda *a:'project'):
    root=BASE/label;root.mkdir()
    def download(url,path,cancel,progress,image=False):path.write_bytes(b'isolated-test-media');progress(19,19)
    h=types.SimpleNamespace(ACCESS=Access(),site_url=lambda v:v,Cancelled=Cancelled,SourceLimited=Limited,
        parse_player=lambda html,sid,n,*args:{'url':'test','episodeId':str(n),'uploadDate':None},download=download)
    m=si.ImportManager(root/'data',callback,lambda path:{'duration':1,'audio':True},h)
    m.resolve=lambda *a,**k:copy.deepcopy(meta);m.html=lambda *a,**k:'';m.start_worker=lambda:None
    return m,root
def start(m,root,numbers,batch=1):
    row=m.start({'url':'https://hongguoduanju.com/detail?series_id=123','directory':str(root),'video':True,'episodes':numbers,'batchSize':batch})
    m.run();return m.get(row['id'])
def resume(m,row):m.control(row['id'],'resume');m.run()
calls=[]
def importer(*args):
    calls.append(str(args[2]))
    if len(calls)==1:raise OSError('injected import failure')
    return 'project'
m,root=manager('import',importer);row=start(m,root,[1]);check('import_failure_not_marked_complete',row['status']=='failed' and row['items'][0]['status']=='failed' and row['done']==0)
resume(m,row);check('import_retry_reuses_complete_file_and_registers',row['status']=='completed' and row['done']==1 and row['projectId']=='project' and len(calls)==2)
m,root=manager('manifest');original=si.write;injected=[]
def fail_once(path,value):
    if path.name=='下载记录.json' and not injected:injected.append(True);raise OSError('injected manifest failure')
    return original(path,value)
with patch.object(si,'write',fail_once):row=start(m,root,[1])
check('commit_intent_survives_manifest_failure',(Path(row['savedDirectory'])/'.下载中/1.commit.json').is_file())
resume(m,row);check('manifest_failure_recovers_without_redownload',row['status']=='completed' and row['done']==1)
check('commit_removed_after_success',not (Path(row['savedDirectory'])/'.下载中/1.commit.json').exists())
m,root=manager('cleanup');original_unlink=Path.unlink
def locked_commit(path,*args,**kwargs):
    if path.name.endswith('.commit.json'):raise PermissionError('injected cleanup lock')
    return original_unlink(path,*args,**kwargs)
with patch.object(Path,'unlink',locked_commit):row=start(m,root,[1])
check('journal_cleanup_failure_does_not_undo_import',row['status']=='completed' and row['done']==1 and row['projectId']=='project' and bool(row['warnings']))
m,root=manager('rename');original_rename=Path.rename;injected=[]
def fail_rename(path,target):
    if path.suffix=='.download' and not injected:injected.append(True);raise OSError('injected rename failure')
    return original_rename(path,target)
with patch.object(Path,'rename',fail_rename):row=start(m,root,[1])
check('verified_temporary_survives_move_failure',(Path(row['savedDirectory'])/'.下载中/1.download').exists())
resume(m,row);check('move_failure_recovers',row['status']=='completed' and row['done']==1)
m,root=manager('links');original_parse=m.h.parse_player
m.h.parse_player=lambda html,sid,n,*a: (_ for _ in ()).throw(ValueError('来源页面读取失败：测试第2集')) if n==2 else original_parse(html,sid,n,*a)
row=start(m,root,[1,2]);assert row['status']=='failed' and row['done']==1
remaining=copy.deepcopy(meta);remaining['episodes']=remaining['episodes'][1:];m.resolve=lambda *a,**k:copy.deepcopy(remaining);m.h.parse_player=original_parse
resume(m,row);check('completed_missing_link_does_not_block_remaining',row['status']=='completed' and row['done']==2)
m,root=manager('batch5');row=start(m,root,[5,1,3,2,4,6],5)
check('legacy_batch_size_does_not_truncate_selected',row['status']=='completed' and row['done']==6 and [x['number'] for x in row['items']]==[5,1,3,2,4,6])
check('legacy_batch_options_removed_from_task','batchSize' not in row and 'confirmBatches' not in row)
m2,root2=manager('continuous')
r2=m2.start({'url':'https://hongguoduanju.com/detail?series_id=123','directory':str(root2),'video':True,'episodes':[6,1,3,2,5,4],'batchSize':1,'confirmBatches':False});m2.run();r2=m2.get(r2['id'])
check('continuous_mode_finishes_all_selected_without_manual_batches',r2['status']=='completed' and r2['done']==6)
m3,root3=manager('snapshot');original_parse3=m3.h.parse_player
m3.h.parse_player=lambda html,sid,n,*a: (_ for _ in ()).throw(ValueError('来源页面读取失败：测试第2集')) if n==2 else original_parse3(html,sid,n,*a)
r3=start(m3,root3,[1,2]);assert r3['status']=='failed' and r3['done']==1
remaining3=copy.deepcopy(meta);remaining3['episodes']=[];m3.resolve=lambda *a,**k:copy.deepcopy(remaining3);m3.h.parse_player=original_parse3
resume(m3,r3);check('public_selected_links_survive_catalogue_changes',r3['status']=='completed' and r3['done']==2)

m4,root4=manager('partial-failure');original_parse=m4.h.parse_player
m4.h.parse_player=lambda html,sid,n,*a: (_ for _ in ()).throw(ValueError('来源网站返回 HTTP 404')) if n==2 else original_parse(html,sid,n,*a)
r4=m4.start({'url':'https://hongguoduanju.com/detail?series_id=123','directory':str(root4),'video':True,'episodes':[1,2,3],'batchSize':1,'confirmBatches':False});m4.run();r4=m4.get(r4['id'])
check('single_unavailable_episode_does_not_block_other_selected',r4['status']=='failed' and r4['done']==2 and r4['items'][1]['status']=='failed')
diagnostic=m4.report(r4['id']);check('download_diagnostic_excludes_full_paths',str(root4) not in json.dumps(diagnostic) and 'directory' not in diagnostic)
m4.h.parse_player=original_parse;resume(m4,r4);check('retry_only_failed_episode_preserves_completed_imports',r4['status']=='completed' and r4['done']==3)
check('archive_records_exact_import_root',json.loads((Path(row['savedDirectory'])/'剧集资料.json').read_text('utf-8'))['importRoot']==str(root.resolve()))
with patch.object(si.shutil,'disk_usage',return_value=types.SimpleNamespace(free=1)):
    try:si.check_storage(root)
    except ValueError:check('insufficient_disk_rejected')
    else:raise AssertionError('disk guard')
manifest=Path(row['savedDirectory'])/'下载记录.json';manifest.write_text('{broken','utf-8')
try:m.records(manifest.parent)
except ValueError:check('corrupt_manifest_not_silently_replaced')
else:raise AssertionError('manifest guard')
# Real FFmpeg production: five selected files, standalone delogo, then final/subtitle hook sources.
source=BASE/'real';source.mkdir();v=source/'第0001集.mp4'
s.ff(['-f','lavfi','-i','testsrc2=s=320x180:r=25:d=2','-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-c:a','aac','-shortest',str(v)])
for n in range(2,6):shutil.copy2(v,source/f'第{n:04}集.mp4')
pid=s.scan(str(source))['projects'][0]['id'];p=s.get_project(pid);p['rights']=True;paths=[v['path'] for v in p['videos']];hashes={path:s.sha256(path) for path in paths}
s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,parallel=1,regroup=False,autoRecords=False,autoCover=False,autoText=False,subtitleAuto=False,subtitleMode='local',subtitleFirst=4)
def create(kind,**kw):
    with patch.object(s,'ensure_runner',lambda:None):r=s.create_job({'kind':kind,'ids':[pid],**kw})
    return s.JOBS[r['id']]
def run(j):s.worker(j['id'],j['ids'],j['kind'],j['config']);assert j['status']=='completed',j.get('error');return j
spec={'kind':'subtitle','ids':[pid],'sourceVideoPaths':{pid:paths}}
pre=s.job_preflight(spec);check('preflight_lists_five_files_and_storage',pre['ok'] and pre['count']==5 and pre['freeBytes']>0)
j=run(create('subtitle',sourceVideoPaths={pid:paths}));repaired=[a for a in p['artifacts'] if a['job']==j['id'] and a['kind']=='字幕处理']
check('selected_five_subtitles_all_really_processed',len(repaired)==5 and all(s.probe(a['path'])['audio'] for a in repaired))
j=run(create('transcode',sourceVideoPaths={pid:paths[:2]}));final=p['finalVideoPaths'][0]
for kind,path in [('subtitle',repaired[0]['path']),('final',final)]:
    j=run(create('hook',sourceKind=kind,sourcePath=path,start=0,seconds=1,title=kind))
    clip=p['promotionClips'][-1];check('real_hook_uses_'+kind,clip['sourcePath']==path and clip['sourceKind']==kind and abs(s.probe(clip['path'])['duration']-1)<.2)
try:create('hook',sourceKind='final',sourcePath=paths[0],seconds=1)
except ValueError:check('foreign_version_hook_rejected')
else:raise AssertionError('version guard')
s.STATE['config'].update(subtitleMode='vsr',vsrRoot=str(BASE/'missing'),vsrPython=str(BASE/'missing.exe'))
check('missing_ai_engine_reported_before_queue',not s.job_preflight(spec)['ok'])
check('original_videos_preserved',all(s.sha256(path)==value for path,value in hashes.items()))
result={'version':VERSION,'compiled':COMPILED,'passed':len(checks),'checks':checks,'network':False,'syntheticImportFaults':True,'realFFmpeg':True,'base':str(BASE)}
(ROOT/(('tmp/workflow-082-compiled.json' if COMPILED else 'tmp/workflow-082-source.json') if VERSION=='v0.8.2' else ('tmp/workflow-081-compiled.json' if COMPILED else 'tmp/workflow-081-source.json'))).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
