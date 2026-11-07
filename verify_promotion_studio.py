"""Isolated local media/API acceptance. LLM and remote publishing are simulated.

No production state, customer keys, platform sessions or real posts are used.
"""
from pathlib import Path
import copy
import http.cookiejar
import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
from unittest.mock import patch

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'tmp'/'promotion-studio-acceptance'/time.strftime('%Y%m%d-%H%M%S')
BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data')
os.environ['FFMPEG_EXE']=str(next((ROOT/'vendor/imageio_ffmpeg/binaries').glob('*.exe')))
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import server as s
import promotion_studio as studio
import promotion_publish as publisher
import local_session

# This regression covers the original native ASR/LLM/FFmpeg compatibility route.
# The fused DramaClip route has its own real-sidecar acceptance fixture.
native_fixture=patch.object(studio.promotion_engines,'local_backend',return_value={
    'localBackend':'native','localBackendReason':'isolated native compatibility acceptance'})
native_fixture.start()

host=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);host.session=local_session.Session()
threading.Thread(target=host.serve_forever,daemon=True).start()
base='http://127.0.0.1:'+str(host.server_address[1])
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
client.open(base+'/launch/'+host.session.launch).read()
checks=[]
def api(path,body=None,error=False):
    try:
        req=urllib.request.Request(base+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json','X-Local-Client':'1'})
        r=client.open(req,timeout=30)
        value=json.loads(r.read())
        if error:raise AssertionError('Expected rejection: '+path)
        return value
    except urllib.error.HTTPError as e:
        value=json.load(e)
        if not error:raise AssertionError((path,e.code,value)) from None
        return value
def wait(jid):
    end=time.time()+180
    while time.time()<end:
        j=s.JOBS[jid]
        if j.get('finished'):
            assert j['status']=='completed',j.get('error');return j
        time.sleep(.1)
    raise AssertionError('Job timed out')
def rejected(fn):
    try:fn()
    except (ValueError,TypeError):return
    raise AssertionError('Expected validation error')

try:
    source=BASE/'source'/'本地智能推广验收';source.mkdir(parents=True)
    for i,color in enumerate(('red','blue')):
        s.ff(['-f','lavfi','-i',f'color=c={color}:s=320x180:r=30:d=6','-f','lavfi','-i',f'sine=frequency={440+i*220}:duration=6',
              '-c:v','libx264','-c:a','aac','-shortest',str(source/f'第{i+1}集.mp4')])
        (source/f'第{i+1}集.srt').write_text('1\n00:00:00,000 --> 00:00:03,000\n你终于回来了。\n\n2\n00:00:03,000 --> 00:00:05,900\n真相究竟是什么？\n','utf-8')
    originals={str(p):s.sha256(p) for p in source.glob('*.mp4')}
    api('config',{'output':str(BASE/'output')})
    pid=api('scan',{'source':str(source)})['projects'][0]['id']
    account=api('accounts',{'name':'LOCAL-TEST-ONLY','type':'切片分发'})
    targets={p:{'enabled':True,'accountId':account['id'],'dramaTitle':'本地验收剧','kind':studio.KINDS[p][0],
                 'value':'https://example.invalid/mini' if p=='douyin' else '本地验收剧'} for p in studio.PLATFORMS}
    opts={'count':1,'seconds':10,'targets':targets,'publishMode':'draft','autoDispatch':True,
          'cta':'精彩剧情即将迎来反转点击观看后续故事'*4}
    api('jobs',{'kind':'promotion_auto','ids':[pid],'studio':opts},error=True)
    checks.append('rights_required')
    api('project',{'id':pid,'rights':True})
    api('promotion/studio-settings',{'projectId':pid,'settings':opts})
    clean=s.get_project(pid)['promotionStudio']
    assert clean['count']==1 and clean['targets']=={} and clean['autoDispatch'] is False
    checks.append('legacy_platform_settings_are_neutralized')
    bad=copy.deepcopy(clean);bad['sourcePaths']=[str(ROOT/'server.py')]
    api('promotion/studio-settings',{'projectId':pid,'settings':bad},error=True)
    checks.append('foreign_source_path_rejected')
    model={'clips':[{'title':'本地测试冲突高光','reason':'只用于模拟台词高光验收','description':'测试文案',
                     'segments':[{'source':0,'start':0,'end':3,'reason':'铺垫'},{'source':1,'start':2,'end':5,'reason':'反转'}]}]}
    with patch.object(studio.ai_providers,'text_generate',return_value={'text':json.dumps(model,ensure_ascii=False),'model':'LOCAL-MOCK-NO-REMOTE-CALL'}):
        jid=api('jobs',{'kind':'promotion_auto','ids':[pid],'studio':opts})['id']
        job=wait(jid)
    p=s.get_project(pid);clip=p['promotionClips'][-1];analysis=p['promotionAnalysis']
    meta=s.probe(clip['path'])
    assert abs(meta['duration']-6)<.3 and meta['width']==320 and meta['height']==180 and meta['audio']
    assert p.get('finalVideoPaths') is None
    checks.extend(['real_ffmpeg_cross_episode_mix','output_duration_dimensions_audio_and_end_decode','full_episode_outputs_preserved'])
    if s.FONT:
        from PIL import ImageFont
        cta=(Path(clip['path']).parent/'cta-0.txt').read_text('utf-8')
        font=ImageFont.truetype(s.FONT,12)
        assert cta.replace('\n','')==opts['cta']
        assert all(font.getlength(line)<=294 for line in cta.splitlines())
        checks.append('long_cta_fits_inside_source_canvas_without_truncation')
    assert not s.STATE['promotionTasks']
    assert job['options']['studio']['targets']=={} and not job['options']['studio']['autoDispatch']
    checks.append('mixing_finishes_without_creating_or_dispatching_platform_tasks')
    api('promotion/fanout',{'projectId':pid,'clipId':clip['id']},error=True)
    api('promotion/receipt',{},error=True)
    api('promotion/dispatch',{},error=True)
    api('jobs',{'kind':'promotion_dispatch','ids':[pid]},error=True)
    checks.append('removed_publish_and_jump_verification_endpoints_rejected')
    # Verify actual pixel order, not only container metadata.
    frames=[]
    for sec in (1,4):
        raw=s.run_process([s.FFMPEG,'-hide_banner','-loglevel','error','-ss',str(sec),'-i',clip['path'],'-frames:v','1','-vf','crop=100:100:110:40,scale=1:1','-pix_fmt','rgb24','-f','rawvideo','-'])
        frames.append(tuple(raw[:3]))
    assert frames[0][0]>frames[0][2]+100 and frames[1][2]>frames[1][0]+100,frames
    checks.append('decoded_pixels_confirm_red_then_blue_source_order')
    # A missing/corrupt output invalidates its checkpoint. Regeneration must
    # refresh the library row, otherwise save/preview sees stale file metadata.
    created=clip['createdAt']
    Path(clip['path']).write_bytes(b'interrupted-or-corrupt-output')
    regenerated=studio.render(s,p,job['config'],jid,analysis)[0]
    stored=next(c for c in p['promotionClips'] if c['id']==clip['id'])
    assert len(p['promotionClips'])==1 and stored['createdAt']==created
    assert all(stored[key]==regenerated[key] for key in ('bytes','mtimeNs','sha256'))
    assert stored['mtimeNs']==Path(stored['path']).stat().st_mtime_ns
    checks.append('corrupt_output_regeneration_refreshes_existing_library_metadata')
    # A file can be replaced by a downloader/editor after the render starts.
    # Do not register a finished clip against an obsolete source snapshot.
    mutation_jid=jid+'-source-mutation'
    s.JOBS[mutation_jid]=dict(job,id=mutation_jid,status='running',cancel=threading.Event(),processes=set(),checkpoints={})
    source_video=Path(analysis['sources'][0]['path'])
    original_bytes=source_video.read_bytes();source_stat=source_video.stat();mutated=[]
    actual_ff=s.ff
    def mutate_during_render(args,jobid=None):
        value=actual_ff(args,jobid)
        if jobid==mutation_jid and not mutated and any(str(arg).endswith('part_00_00.mp4') for arg in args):
            source_video.write_bytes(original_bytes+b'changed-during-encoding')
            mutated.append(True)
        return value
    try:
        with patch.object(s,'ff',side_effect=mutate_during_render):
            rejected(lambda:studio.render(s,p,job['config'],mutation_jid,analysis))
        assert mutated and len(p['promotionClips'])==1
    finally:
        source_video.write_bytes(original_bytes)
        os.utime(source_video,ns=(source_stat.st_atime_ns,source_stat.st_mtime_ns))
        s.JOBS[mutation_jid].update(status='failed',finished=time.time())
    checks.append('source_replacement_during_encode_stops_before_registering_stale_clip')
    for mutation in ('overlap','bounds','nan','count'):
        raw=copy.deepcopy(model)
        if mutation=='overlap':raw['clips'][0]['segments'].append({'source':0,'start':1,'end':2})
        if mutation=='bounds':raw['clips'][0]['segments'][0]['end']=10000
        if mutation=='nan':raw['clips'][0]['segments'][0]['start']=float('nan')
        if mutation=='count':raw['clips']*=2
        rejected(lambda:studio.validate_plans(raw,analysis['sources'],1,10))
    checks.append('hallucinated_overlapping_nonfinite_and_duplicate_plans_rejected')
    rejected(lambda:studio.decode_json('no JSON; run commands'))
    checks.append('invalid_model_output_has_no_random_fallback')
    assert originals=={str(p):s.sha256(p) for p in source.glob('*.mp4')}
    checks.append('source_media_unchanged')
    # Rescan must retain all new state, including reviewed analysis and target snapshots.
    api('scan',{'source':str(source)})
    assert s.get_project(pid)['promotionAnalysis']['id']==analysis['id'] and s.get_project(pid)['promotionStudio']==clean
    checks.append('rescan_preserves_analysis_and_settings')
    subtitle=source/'第1集.srt';subtitle.write_text(subtitle.read_text('utf-8')+'\n','utf-8')
    api('jobs',{'kind':'promotion_render','ids':[pid],'studio':opts},error=True)
    checks.append('changed_subtitle_invalidates_analysis')
    report={'ok':True,'checks':checks,'base':str(BASE),'projectId':pid,'clip':clip['path'],'frames':frames,
            'llm':'simulated','asr':'real_srt_input','encoding':'real_ffmpeg','remotePublishing':False}
    (ROOT/'tmp/promotion-studio-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('PROMOTION_STUDIO_ACCEPTANCE_OK',len(checks),json.dumps(frames))
finally:
    s.shutdown_jobs();host.shutdown();host.server_close();native_fixture.stop()
