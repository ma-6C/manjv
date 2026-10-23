"""HTTP boundaries, thirty real outputs, active recovery and user-clip acceptance."""
from pathlib import Path
import hashlib,http.cookiejar,io,json,os,time,urllib.error,urllib.parse,urllib.request,zipfile

ROOT=Path(__file__).resolve().parent;meta=json.loads((ROOT/'tmp/tracks-ui-host.json').read_text('utf-8'))
BASE=Path(meta['base']);checks=[]
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
client.open(meta['launch']).read()
def request(path,body=None,headers=None,auth=True,raw=False):
    data=json.dumps(body).encode() if body is not None else None
    h={'Content-Type':'application/json','X-Local-Client':'1'} if body is not None else {}
    h.update(headers or {});req=urllib.request.Request(meta['url']+path,data=data,headers=h)
    try:
        with (client if auth else urllib.request.build_opener()).open(req,timeout=30) as r:
            value=r.read();return r.status,value if raw else json.loads(value)
    except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
def api(path,body=None):
    status,value=request('/api/'+path,body)
    if status!=200:raise AssertionError((path,status,value))
    return value
def check(name,value=True):assert value,name;checks.append(name);print(name,flush=True)
def wait_job(jid,test,timeout=90):
    start=time.monotonic()
    while time.monotonic()-start<timeout:
        j=next(j for j in api('state')['jobs'] if j['id']==jid)
        if test(j):return j
        time.sleep(.1)
    raise AssertionError('job timeout '+jid)
def body_for(videos,paths=None,**opts):
    selected=paths or [v['path'] for v in videos];mapping={}
    for path in selected:
        v=next(v for v in videos if v['path']==path);mapping.setdefault(v['projectId'],[]).append(path)
    return {'kind':'track_sheet','ids':list(mapping),'sourceVideoPaths':mapping,'trackOrder':selected,
            'trackSheet':{'device':'cpu','width':1920,'output':str(BASE/'HTTP输出'),**opts}}

check('rejects_missing_local_session',request('/api/tracks/devices',{},auth=False)[0]==403)
check('rejects_cross_origin',request('/api/tracks/devices',{},headers={'Origin':'https://foreign.example'})[0]==403)
check('rejects_missing_client_header',request('/api/tracks/devices',{},headers={'X-Local-Client':''})[0]==403)
check('rejects_unregistered_local_file',request('/api/file?path='+urllib.parse.quote(str(ROOT/'server.py')))[0] in (400,403))
check('rejects_more_than_thirty_before_import',request('/api/tracks/import',{'paths':meta['bulkFiles']+[meta['bulkFiles'][0]]})[0]==400)
videos=api('tracks/import',{'paths':meta['bulkFiles']})['videos'];before={v['path']:hashlib.sha256(Path(v['path']).read_bytes()).hexdigest() for v in videos}
body=body_for(videos,tracks=9,threshold=31);plan=api('tracks/plan',body)
check('thirty_file_preflight_reports_exact_count',plan['ok'] and plan['count']==30)
started=time.monotonic();jid=api('jobs',body)['id'];j=wait_job(jid,lambda j:j['status'] in ['completed','failed']);elapsed=round(time.monotonic()-started,3)
check('thirty_selected_videos_produce_thirty_valid_pngs',j['status']=='completed' and len(j['trackResults'])==30)
check('identical_source_analysis_reused_across_episodes',sum(r['cacheHit'] for r in j['trackResults'])==29)
check('all_batch_outputs_are_unique',len({r['path'] for r in j['trackResults']})==30)
for row in j['trackResults']:
    assert hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()==row['imageSHA256']
    record=json.loads(Path(row['manifest']).read_text('utf-8'));assert record['tracks']==9 and record['width']==1920
check('thirty_image_hashes_and_layout_manifests_valid')
check('all_source_hashes_unchanged',all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in before.items()))
exported=api('tracks/export',{'id':jid});status,archive=request('/api/file?path='+urllib.parse.quote(exported['path']),raw=True)
with zipfile.ZipFile(io.BytesIO(archive)) as z:
    check('protected_download_zip_contains_exactly_png_and_analysis',status==200 and len(z.namelist())==60 and all(n.endswith(('.png','.json')) for n in z.namelist()))
row=j['trackResults'][0]
for field,label in [('path','image'),('manifest','analysis')]:
    path=Path(row[field]);original=path.read_bytes();st=path.stat()
    try:
        path.write_bytes(original+b' ')
        check('modified_'+label+'_cannot_be_exported',request('/api/tracks/export',{'id':jid})[0]==400)
    finally:path.write_bytes(original);os.utime(path,ns=(st.st_atime_ns,st.st_mtime_ns))
check('failed_exports_leave_no_partial_zip',not list((BASE/'data/exports').glob('*.part')))

fixtures=api('tracks/import',{'paths':meta['files']})['videos'];second=next(v for v in fixtures if v['path']==meta['files'][1])
cancel_body=body_for([second],reuse=False,threshold=41)
cancel_id=api('jobs',cancel_body)['id']
wait_job(cancel_id,lambda j:j['status']=='running' and '解码与抽帧' in j['stage'])
api('jobs/control',{'id':cancel_id,'action':'pause'});paused=wait_job(cancel_id,lambda j:j['status']=='paused')
check('active_process_pause_saves_resumable_job',paused.get('resumable') and not paused.get('trackResults'))
source=Path(second['path']);original=source.read_bytes();st=source.stat()
try:
    source.write_bytes(original+b'changed')
    check('changed_source_is_rejected_on_resume',request('/api/jobs/control',{'id':cancel_id,'action':'resume'})[0]==400)
finally:source.write_bytes(original);os.utime(source,ns=(st.st_atime_ns,st.st_mtime_ns))
api('jobs/control',{'id':cancel_id,'action':'cancel'});check('stopped_task_remains_visible',next(j for j in api('state')['jobs'] if j['id']==cancel_id)['status']=='cancelled')
check('interrupted_frame_work_is_cleaned',not list((BASE/'data/track-sheet-cache').glob('work-*')))

real_results=[];real_elapsed=None
if meta.get('realFile'):
    source=Path(meta['realFile']);real_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    real=api('tracks/import',{'paths':[str(source)]})['videos']
    real_body=body_for(real,device='auto',tracks=8,width=2560,output=str(BASE/'真实视频工程图'))
    started=time.monotonic();real_id=api('jobs',real_body)['id'];real_job=wait_job(real_id,lambda j:j['status'] in ['completed','failed'])
    check('user_supplied_subtitled_video_generates_actual_eight_track_png',real_job['status']=='completed' and len(real_job['trackResults'])==1)
    real_results=real_job['trackResults'];real_elapsed=round(time.monotonic()-started,3)
    check('user_video_original_is_preserved',hashlib.sha256(source.read_bytes()).hexdigest()==real_hash)
    image=real_results[0];record=json.loads(Path(image['manifest']).read_text('utf-8'))
    check('real_clip_contains_actual_scene_segments_and_source_pts',len(record['segments'])>1 and len(record['samples'])>1 and record['sourceSHA256']==real_hash)
    second_body=body_for(real,device='auto',tracks=3,width=2560,output=str(BASE/'真实视频工程图'))
    real_id2=api('jobs',second_body)['id'];real_job2=wait_job(real_id2,lambda j:j['status'] in ['completed','failed'])
    check('real_clip_three_track_layout_reuses_eight_track_analysis',real_job2['status']=='completed' and real_job2['trackResults'][0]['cacheHit'])
    real_results+=real_job2['trackResults']
report={'sourceOnly':not meta.get('compiled'),'compiled':bool(meta.get('compiled')),'version':meta.get('version'),'signedDistributionVerified':bool(meta.get('signedDistributionVerified')),'passed':len(checks),'checks':checks,'base':str(BASE),'batchCount':30,'batchSeconds':elapsed,
        'batchFixture':'30 copies of the same 3-second synthetic clip; tests throughput and cache, not 30 real drama episodes',
        'realVideoSeconds':real[0]['duration'] if real_results else None,'realWallSeconds':real_elapsed,'realResults':real_results,
        'network':'loopback only','userVideoPreserved':True}
(ROOT/'tmp/tracks-integration-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':len(checks),'batchSeconds':elapsed,'realWallSeconds':real_elapsed}),flush=True)
