"""Real-media local acceptance; never logs into or publishes to any platform."""
from pathlib import Path
import sys,os,time,json,threading,urllib.request,urllib.error,http.cookiejar,zipfile,hashlib,subprocess,re,argparse
ROOT=Path(__file__).resolve().parent;parser=argparse.ArgumentParser();parser.add_argument('--compiled',action='store_true');args=parser.parse_args()
BASE=ROOT/'tmp/promotion-acceptance'/time.strftime('%Y%m%d-%H%M%S');BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data');os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
if args.compiled:sys.path.insert(0,str(ROOT/'release/v0.6.0/漫剧工坊/_internal'));sys.frozen=True
sys.path.append(str(ROOT/'vendor'))
import server as s,promotions,licensing,local_session
if args.compiled:
    assert s.__file__.endswith('.pyd');licensing.verify_distribution(ROOT/'release/v0.6.0/漫剧工坊')
    licensing.activate(s.DATA,(ROOT/'授权管理/本机长期授权码.txt').read_text('utf-8'))
service=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);service.session=local_session.Session();threading.Thread(target=service.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(service.server_address[1]);client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
client.open(base+'/launch/'+service.session.launch).read();checks=[]
def api(path,body=None,error=None):
    try:
        r=client.open(urllib.request.Request(base+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-Local-Client':'1'}),timeout=30);data=r.read()
        if error:raise AssertionError('Expected rejection: '+path)
        return json.loads(data) if 'application/json' in r.headers.get('Content-Type','') else data
    except urllib.error.HTTPError as e:
        data=json.load(e)
        if error:assert e.code==error,(e.code,data);return data
        raise AssertionError((path,e.code,data)) from None
def job(kind,**options):
    jid=api('jobs',{'kind':kind,'ids':[pid],**options})['id'];end=time.time()+120
    while time.time()<end:
        j=s.JOBS[jid]
        if j.get('finished'):break
        time.sleep(.1)
    assert j['status']=='completed',j.get('error');return j
try:
    source=BASE/'source'/'本地推广验收';source.mkdir(parents=True);original=source/'第1集.mp4'
    s.ff(['-f','lavfi','-i','testsrc2=s=320x180:r=30:d=6','-f','lavfi','-i','sine=frequency=440:duration=6','-c:v','libx264','-c:a','aac','-shortest',str(original)])
    before=s.sha256(original);api('config',{'output':str(BASE/'output')});pid=api('scan',{'source':str(source)})['projects'][0]['id']
    api('jobs',{'kind':'hook','ids':[pid],'seconds':2},400);checks.append('unauthorized_rights_hook_rejected')
    api('project',{'id':pid,'rights':True});a=api('accounts',{'name':'本地验收账号','type':'切片分发'})
    api('jobs',{'kind':'hook','ids':[pid],'start':5,'seconds':3},400)
    j=job('hook',videoIndex=0,start=1,seconds=2,title='本地验收钩子',cta='点击下方入口看全集')
    p=s.get_project(pid);clip=p['promotionClips'][0];assert abs(s.probe(clip['path'])['duration']-2)<.15 and s.probe(clip['path'])['audio'];assert s.sha256(original)==before
    assert not p.get('finalVideoPaths');checks.extend(['real_ffmpeg_hook_with_audio','source_original_unchanged','hook_does_not_replace_full_episodes'])
    native={'type':'native','dramaTitle':'本地验收剧','dramaId':'LOCAL-NATIVE-1'}
    mini={'type':'mini_program','dramaTitle':'本地验收剧','appId':'wx0123456789abcdef','pagePath':'pages/play/index?drama_id=LOCAL'}
    third={'type':'third_party','dramaTitle':'本地验收剧','dramaId':'LOCAL-PARTNER-1','provider':'本地测试平台','backendUrl':'https://example.invalid/publisher'}
    rows=[]
    for value in [native,mini,third]:
        api('promotion/entry',{'projectId':pid,'entry':value});t=api('promotion/task',{'projectId':pid,'clipId':clip['id'],'accountId':a['id']});rows.append(t)
        assert t['mountStatus']=='pending';checks.append(value['type']+'_entry_and_task')
    assert api('promotion/task',{'projectId':pid,'clipId':clip['id'],'accountId':a['id']})['id']==rows[-1]['id'];checks.append('duplicate_preparation_idempotent')
    assert rows[0]['entry']['dramaId']=='LOCAL-NATIVE-1' and s.STATE['promotionTasks'][0]['entry']['type']=='native';checks.append('immutable_entry_snapshot')
    api('promotion/entry',{'projectId':pid,'entry':{**third,'backendUrl':'javascript:alert(1)'}},400);checks.append('unsafe_backend_scheme_rejected')
    task=rows[0];pack=job('promotion_package',promotionTaskId=task['id']);archive=pack['result']['path']
    with zipfile.ZipFile(archive) as z:
        value=json.loads(z.read('挂载任务.json'));assert value['entry']['dramaId']=='LOCAL-NATIVE-1' and value['platformResult'] is None
        assert hashlib.sha256(z.read('钩子短视频.mp4')).hexdigest()==clip['sha256']
    assert s.STATE['promotionTasks'][0]['mountStatus']=='pending';checks.append('real_promotion_package_and_no_fake_mount_success')
    api('promotion/dispatch',{'taskId':task['id']});assert s.STATE['promotionTasks'][0]['mountStatus']=='pending';checks.append('open_backend_does_not_confirm_mount')
    api('promotion/revenue',{'taskId':task['id'],'date':'2026-10-20','revenue':'1.23'},400)
    api('promotion/receipt',{'taskId':task['id'],'status':'mounted','checked':False,'postId':'LOCAL','note':'本地虚拟核对'},400)
    api('promotion/receipt',{'taskId':task['id'],'status':'mounted','checked':True,'note':'本地虚拟核对'},400);checks.append('manual_mount_proof_required')
    api('promotion/receipt',{'taskId':task['id'],'status':'mounted','checked':True,'postId':'LOCAL-NOT-REAL-POST','note':'仅为本地验收数据，未向任何平台发布'})
    api('promotion/revenue',{'taskId':task['id'],'date':'2026-10-20','views':100,'clicks':10,'unlocks':5,'revenue':'1.23','note':'本地测试金额'})
    assert api('state')['promotionSummary']['revenueCents']==123
    csv=f'taskId,date,views,clicks,unlocks,revenue,note\n{task["id"]},2026-10-20,200,20,8,5.67,本地测试更新\n'
    api('promotion/revenue-import',{'csv':csv});api('promotion/revenue-import',{'csv':csv});summary=api('state')['promotionSummary'];assert summary['revenueCents']==567 and summary['rows']==1;checks.append('decimal_money_and_idempotent_csv_update')
    api('promotion/revenue-import',{'csv':csv+'not-found,2026-10-20,1,1,1,1000,bad\n'},400);assert api('state')['promotionSummary']['revenueCents']==567;checks.append('invalid_csv_import_is_atomic')
    exported=api('promotion/revenue-export').decode('utf-8-sig');assert '5.67' in exported
    api('scan',{'source':str(source)});p=s.get_project(pid);assert p['promotionEntry']['type']=='third_party' and len(p['promotionEntries'])==3 and p['promotionClips'][0]['id']==clip['id'];checks.append('rescan_preserves_all_three_entries_clips_and_tasks')
    disk=json.loads((s.DATA/'state.json').read_text('utf-8'));assert disk['promotionTasks'][0]['mountStatus']=='user_confirmed' and disk['promotionRevenue'][0]['revenueCents']==567;checks.append('task_receipts_and_revenue_persisted')
    report={'ok':True,'compiled':args.compiled,'checks':checks,'base':str(BASE),'core':s.__file__,'clip':clip['path'],'package':archive,'sourceUnchanged':True,'externalPlatformPublished':False}
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');(ROOT/'tmp/latest-promotion-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('PROMOTION_ACCEPTANCE_OK',len(checks),'compiled='+str(args.compiled),flush=True)
finally:s.shutdown_jobs();service.shutdown();service.server_close()
