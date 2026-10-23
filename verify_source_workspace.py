"""Real public-episode imports, persistent selections and production regressions."""
from pathlib import Path
import os,sys,json,time,threading,copy,shutil,urllib.error,email.message,re
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;BASE=ROOT/'tmp'/('source-workspace-'+time.strftime('%Y%m%d-%H%M%S'));BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data')
COMPILED='--compiled' in sys.argv;REPLAY='--replay' in sys.argv;VERSION=sys.argv[sys.argv.index('--version')+1] if '--version' in sys.argv else 'v0.8.0'
sys.dont_write_bytecode=True
if COMPILED:
    sys.path[:0]=[str(ROOT/'release'/VERSION/'漫剧工坊/_internal'),str(ROOT/'vendor')];sys.frozen=True
import hongguo_source as h,episode_selection as es,server as s
if COMPILED:
    assert s.__file__.endswith('.pyd')
    token=re.search(r'MJ1\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8-sig')).group(0)
    s.licensing.activate(s.DATA,token)
real_fetch=h.fetch_html;real_download=h.download
if REPLAY:
    recording=json.loads((ROOT/'tmp/source-workspace-acceptance.json').read_text('utf-8'))
    sources={v['sourceEpisodeId']:Path(v['path']) for v in recording['media']}
    def recorded_html(url,cancel=None,**kwargs):
        if '/detail?' in url:return (ROOT/'tmp/hongguo-detail-current.html').read_text('utf-8')
        ids={'7697855365819419673':2,'7697855263528733721':3}
        number=ids.get(url.rsplit('/',1)[-1],1)
        name='hongguo-player.html' if number==1 else f'hongguo-player-{number}.html'
        return (ROOT/'tmp'/name).read_text('utf-8')
    def recorded_download(url,path,cancel,progress,image=False):
        src=ROOT/'实际视频测试/红果网页采集-20261020/封面.jpg' if image else sources[url.split('/')[-2]]
        if cancel.is_set():raise h.Cancelled()
        path.with_suffix(path.suffix+'.part').unlink(missing_ok=True);shutil.copy2(src,path);progress(path.stat().st_size,path.stat().st_size)
    h.fetch_html=recorded_html;h.download=recorded_download
checks=[]
def check(name,value=True):assert value,name;checks.append(name)
def rejects(fn):
    try:fn()
    except (ValueError,PermissionError):return True
    return False
def wait(manager,jid,status=None):
    until=time.monotonic()+240
    while time.monotonic()<until:
        row=next(r for r in manager.list() if r['id']==jid)
        if status and row['status']==status:return row
        if row['status'] not in ('queued','running'):return row
        time.sleep(.1)
    raise AssertionError('采集超时')
check('non_contiguous_expression_preserves_order',es.normalize('3,1,3,8-10')==[3,1,8,9,10])
check('numeric_order_optional',es.normalize([3,1,2],order='number')==[1,2,3])
check('invalid_selection_rejected',all(rejects(lambda v=v:es.normalize(v)) for v in [[],[True],[0],[-1],'2-1','1.5','bad']))
for n in [1,2,3]:
    name='hongguo-player.html' if n==1 else f'hongguo-player-{n}.html'
    text=(ROOT/'tmp'/name).read_text('utf-8')
    info=h.parse_player(text,'7697852455970671678',n)
    assert info['url'].endswith('/360p.mp4')
    if n!=1:assert rejects(lambda:h.parse_player(text,'7697852455970671678',1))
check('three_real_player_snapshots_require_exact_episode_identity')
m=h.Manager(s.DATA,s.import_source_video,s.probe);url=h.BASE+'/detail?series_id=7697852455970671678'
meta=m.resolve(url);check('live_detail_exposes_only_linked_episodes',{1,2,3}.issubset({e['number'] for e in meta['episodes']}) and all(e['playerUrl'].startswith(h.BASE+'/player/'+meta['seriesId']) for e in meta['episodes']))
prepared=m.directory(str(BASE),meta);stale=prepared/'.下载中';stale.mkdir(exist_ok=True)
(stale/'7697855263528733721.download.part').write_bytes(b'old interrupted chunk')
(stale/'unrelated.part').write_bytes(b'keep unrelated temporary file')
(prepared/'封面.image.part').write_bytes(b'old interrupted cover')
first=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[3,1],'batchSize':1})
row=wait(m,first['id']);check('actual_non_contiguous_selection_stops_after_first_batch',row['status']=='awaiting_confirmation' and row['done']==1 and row['items'][0]['number']==3)
project=s.get_project(row['projectId']);pid=project['id'];directory=Path(row['savedDirectory']);check('first_download_is_requested_episode_three_only',[v['sourceEpisode'] for v in project['videos']]==[3])
check('stale_episode_partial_recovers_without_removing_other_files',not (stale/'7697855263528733721.download.part').exists() and (stale/'unrelated.part').read_bytes()==b'keep unrelated temporary file' and not (prepared/'封面.image.part').exists())
project.update(name='用户自定义剧名',rights=True,notes='保留用户备注')
m.control(row['id'],'resume');row=wait(m,row['id']);check('confirmation_downloads_remaining_selected_episode',row['status']=='completed' and row['done']==2)
project=s.get_project(pid);check('appended_episodes_merge_into_same_project',len(s.STATE['projects'])==1 and [v['sourceEpisode'] for v in project['videos']]==[1,3])
check('merge_preserves_user_edits_and_rights',project['name']=='用户自定义剧名' and project['rights'] and project['notes']=='保留用户备注')
before={v['path']:(Path(v['path']).stat().st_mtime_ns,Path(v['path']).stat().st_size) for v in project['videos']}
again=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[3,1],'batchSize':3});done=wait(m,again['id'])
check('verified_duplicate_episodes_skipped_without_rewrite',done['status']=='completed' and all(i['status']=='skipped' for i in done['items']) and all((Path(p).stat().st_mtime_ns,Path(p).stat().st_size)==stat for p,stat in before.items()))
second=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[2],'batchSize':1});done2=wait(m,second['id'])
check('episode_two_appends_to_same_directory',done2['status']=='completed' and done2['savedDirectory']==str(directory) and done2['projectId']==pid)
project=s.get_project(pid);check('all_three_files_have_real_video_and_audio',len(project['videos'])==3 and all(v['audio'] and v['duration']>0 for v in project['videos']))
records=json.loads((directory/'下载记录.json').read_text('utf-8'));check('manifest_retains_source_ids_hashes_and_episode_dates',[r['episode'] for r in records]==[1,2,3] and all(r['episodeId'] and r['sha256'] and r['episodeUploadDate'] for r in records))
export=json.loads((directory/'剧集资料.json').read_text('utf-8'));check('no_signed_media_urls_in_export','/video/public/' not in json.dumps(export) and export['playCount'] is None)
unsupported=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[99,1],'batchSize':3});bad=wait(m,unsupported['id'])
check('unsupported_episode_never_falls_back_to_episode_one',bad['status']=='failed' and bad.get('done',0)==0 and '99' in bad['stage'])
ordered=m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[3,2,1],'batchSize':1});pending=wait(m,ordered['id']);assert pending['status']=='awaiting_confirmation'
check('queue_rejects_phantom_episode_reorder',rejects(lambda:m.control(ordered['id'],'reorder',[8,1])))
m.control(ordered['id'],'reorder',[1,2]);m.control(ordered['id'],'resume');pending=wait(m,ordered['id']);check('remaining_queue_reorder_applied',[i['number'] for i in pending['items']]==[3,1,2] and pending['done']==2)
m.control(ordered['id'],'resume');assert wait(m,ordered['id'])['status']=='completed'
reopened=h.Manager(s.DATA,s.import_source_video,s.probe);check('same_drama_directory_and_history_survive_restart',reopened.index==m.index and reopened.list()[-1]['status']=='completed')
h.fetch_html=real_fetch;h.download=real_download
# Simulate a server throttle without deliberately triggering a real website limit.
headers=email.message.Message();headers['Retry-After']='120'
error=urllib.error.HTTPError(url,429,'test throttle',headers,None)
class Failing:
    def open(self,*a,**k):raise error
with patch.object(h.urllib.request,'build_opener',return_value=Failing()):assert rejects(lambda:h.fetch_html(url))
check('429_pauses_source_with_retry_after',h.ACCESS.snapshot()['paused'] and h.ACCESS.snapshot()['retryAt']>time.time()+100)
check('cannot_resume_before_server_wait_expires',rejects(h.ACCESS.resume))
restored=h.Access();restored.configure(s.DATA);check('source_throttle_survives_restart',restored.snapshot()['paused'])
h.ACCESS.control={};h.ACCESS.save()
# Actual video processing uses only selected files in the requested order.
s.STATE['config'].update(output=str(BASE/'output'),width=320,height=180,parallel=1,regroup=False,autoRecords=False,autoCover=False,autoText=False,subtitleAuto=False)
paths=[v['path'] for n in [3,1] for v in project['videos'] if v['sourceEpisode']==n]
with patch.object(s,'ensure_runner',lambda:None):job=s.create_job({'kind':'transcode','ids':[pid],'sourceVideoPaths':{pid:paths}})
j=s.JOBS[job['id']];snapshot=copy.deepcopy(j['sourceSnapshot'])
fixture=BASE/'后续补集本地样片.mp4';shutil.copy2(paths[0],fixture)
project['videos'].append({'path':str(fixture),'name':fixture.name,'bytes':fixture.stat().st_size,'mtime':fixture.stat().st_mtime,**s.probe(fixture)})
check('new_local_material_does_not_change_existing_selection_snapshot',s.source_snapshot([pid],j['options']['sourceVideoPaths'])==snapshot)
s.worker(j['id'],j['ids'],j['kind'],j['config']);check('actual_selected_video_processing_completes',j['status']=='completed')
check('only_two_selected_sources_processed_in_order',len(project['finalVideoPaths'])==2 and all(abs(s.probe(out)['duration']-s.probe(src)['duration'])<.2 for out,src in zip(project['finalVideoPaths'],paths)))
check('processing_metadata_writes_back_without_replacing_library_videos',project['status']=='部分集已处理' and len(project['videos'])==4)
with patch.object(s,'ensure_runner',lambda:None):check('foreign_video_selection_rejected',rejects(lambda:s.create_job({'kind':'transcode','ids':[pid],'sourceVideoPaths':{pid:['C:/not-registered.mp4']}})))
result={'compiled':COMPILED,'liveNetwork':not REPLAY,'transport':'recorded_actual_responses_and_media' if REPLAY else 'live','version':VERSION[1:],'checks':checks,'passed':len(checks),'base':str(BASE),'realSource':url,'projectId':pid,'directory':str(directory),'media':[v for v in project['videos'] if v.get('sourceEpisode')], 'selectedJob':{'id':j['id'],'status':j['status'],'sourceOrder':[3,1]}}
(ROOT/('tmp/source-workspace-082-acceptance.json' if VERSION=='v0.8.2' else 'tmp/source-workspace-081-acceptance.json' if VERSION=='v0.8.1' else ('tmp/source-workspace-compiled-acceptance.json' if COMPILED else 'tmp/source-workspace-acceptance.json'))).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'base':str(BASE)},ensure_ascii=False),flush=True)
