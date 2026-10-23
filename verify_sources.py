"""Hongguo parser, download integrity, queue and optional real-network acceptance."""
from pathlib import Path
import argparse
import io
import json
import os
import threading
import time
from unittest.mock import patch
import hongguo_source as h

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'tmp'/('source-acceptance-'+time.strftime('%Y%m%d-%H%M%S'));BASE.mkdir(parents=True)
os.environ['MANJU_DATA']=str(BASE/'data')
import server as s

checks=[]
def check(name,value=True):
    assert value,name
    checks.append(name)
def rejected(fn):
    try:fn()
    except (ValueError,OSError):return True
    return False

def run(live=False):
    for value in ['http://hongguoduanju.com/detail?series_id=123456','https://127.0.0.1/','https://hongguoduanju.com.evil.test/',
        'https://user@hongguoduanju.com/detail?series_id=123456','https://hongguoduanju.com:444/category/comic-drama','https://hongguoduanju.com/category/comic-drama?page=-1']:
        assert rejected(lambda:h.site_url(value)),value
    check('foreign_hosts_credentials_ports_and_invalid_paging_blocked')
    check('share_text_extracts_only_canonical_supported_url',h.site_url('看这个 https://hongguoduanju.com/detail?series_id=123456&token=secret')==h.BASE+'/detail?series_id=123456')
    for url in ['https://localhost/pic.jpg','https://a.byteimg.com.evil.test/pic','file:///C:/a','https://hongguoduanju.com@evil.test/a']:
        assert rejected(lambda:h.resource_url(url,True))
    check('resource_redirect_host_allowlist')
    class R(io.BytesIO):
        def __init__(self,b,total):super().__init__(b);self.headers={'Content-Length':total}
    out=BASE/'cut.mp4';event=threading.Event()
    with patch.object(h,'response',return_value=R(b'abc','20')):
        check('truncated_download_never_promoted',rejected(lambda:h.download(h.BASE+'/video/public/123/360p.mp4',out,event,lambda n,t:None)) and not out.exists() and not out.with_suffix('.mp4.part').exists())
    values=[]
    with patch.object(h,'response',return_value=R(b'abc','')):
        h.download(h.BASE+'/video/public/123/360p.mp4',out,event,lambda n,t:values.append((n,t)))
    check('unknown_length_keeps_total_unknown',values==[(3,None)] and out.read_bytes()==b'abc')
    out.unlink();event.set()
    with patch.object(h,'response',return_value=R(b'abc','3')):
        try:h.download(h.BASE+'/video/public/123/360p.mp4',out,event,lambda n,t:None)
        except h.Cancelled:pass
        else:raise AssertionError('cancel not honored')
    check('cancellation_removes_partial',not out.exists() and not out.with_suffix('.mp4.part').exists())
    control=threading.Event()
    managerdata=BASE/'queue-data';managerdata.mkdir()
    m=h.Manager(managerdata,lambda *a:None,lambda *a:None)
    with patch.object(h,'resolve',side_effect=lambda url:(control.wait(5),{})[1]):
        one=m.start({'url':h.BASE+'/detail?series_id=123456','directory':str(BASE),'video':False})
        # Wait until the first row has actually entered the worker.
        until=time.monotonic()+3
        while m.list()[0]['status']=='queued' and time.monotonic()<until:time.sleep(.01)
        two=m.start({'url':h.BASE+'/detail?series_id=234567','directory':str(BASE),'video':False})
        m.cancel(two['id']);m.cancel(one['id']);thread=m.worker;control.set();thread.join(6)
    check('queued_and_running_cancellation_without_duplicate_files',all(r['status']=='cancelled' for r in m.list()))
    m.rows.append({'id':'restart-test','status':'running','stage':'旧任务'});m.save()
    check('restart_marks_unfinished_tasks_interrupted',h.Manager(managerdata,lambda *a:None,lambda *a:None).list()[-1]['status']=='interrupted')
    snapshots=ROOT/'tmp'
    if (snapshots/'hongguo-category.html').exists():
        catalog=h.parse_catalog((snapshots/'hongguo-category.html').read_text('utf-8'))
        detail=h.parse_detail((snapshots/'hongguo-detail.html').read_text('utf-8'),h.BASE+'/detail?series_id=7697852455970671678')
        player=h.parse_player((snapshots/'hongguo-player.html').read_text('utf-8'),'7697852455970671678')
        check('actual_page_snapshot_24_catalog_entries',len(catalog['entries'])==24)
        check('actual_detail_heat_episode_count_no_fake_plays',detail['totalEpisodes']==193 and detail['webEpisodeLinks']==3 and detail['heat']['display']=='8070万热度' and detail['playCount'] is None and detail['publishedAt'] is None)
        check('public_video_matches_dom_and_structured_data',player['url'].endswith('/360p.mp4'))
    result={'checks':checks,'base':str(BASE),'live':live}
    if live:
        catalog=h.resolve(h.CATALOG);check('live_catalog_read',len(catalog['entries'])>0)
        detail=h.resolve(catalog['entries'][0]['url']);check('live_detail_read',bool(detail['title'] and detail['intro']))
        manager=h.Manager(s.DATA,s.import_source_video,s.probe)
        row=manager.start({'url':detail['url'],'directory':str(BASE),'video':True})
        deadline=time.monotonic()+240; observed=[]
        while time.monotonic()<deadline:
            row=manager.list()[-1];observed.append(row['stage'])
            if row['status'] not in ('queued','running'):break
            time.sleep(.15)
        check('live_download_and_material_import_completed',row['status']=='completed')
        check('live_cover_saved',bool(list(Path(row['savedDirectory']).glob('封面.*'))))
        project=s.get_project(row['projectId']);v=project['videos'][0]
        check('actual_ffmpeg_probe_video_and_audio',v['duration']>0 and v['audio'] and v['codec']=='h264')
        meta=json.loads((Path(row['savedDirectory'])/'剧集资料.json').read_text('utf-8'))
        check('saved_metadata_keeps_scope_and_episode_publish_date',meta['publishedAt'] is None and meta['downloadRecords'][0]['episodeUploadDate'] and meta['downloadRecords'][0]['episode']==1)
        check('temporary_media_url_not_exported','contentUrl' not in json.dumps(meta) and '/video/public/' not in json.dumps(meta))
        check('source_metadata_retained_on_rescan',s.scan(row['savedDirectory'])['projects'][0]['sourceMetadata']['seriesId']==detail['seriesId'])
        check('queue_state_survives_restart',h.Manager(s.DATA,s.import_source_video,s.probe).list()[-1]['status']=='completed')
        # Decode actual video and audio, rather than treating an HTML player as a download proof.
        s.ff(['-i',v['path'],'-f','null','-']);check('real_video_audio_full_decode')
        result.update(catalogCount=len(catalog['entries']),detail=detail,task=row,media=v,observedStages=list(dict.fromkeys(observed)))
    result['checks']=checks
    (ROOT/('tmp/latest-source-acceptance.json' if live else 'tmp/latest-source-unit.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({'passed':len(checks),'live':live,'base':str(BASE)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--live',action='store_true');run(p.parse_args().live)
