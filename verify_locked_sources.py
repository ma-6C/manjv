"""Explicit source lock markers are distinct from missing links and HTTP failures."""
from pathlib import Path
import sys,json,tempfile,types,threading,copy
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;sys.dont_write_bytecode=True
COMPILED='--compiled' in sys.argv
if COMPILED:sys.path.insert(0,str(ROOT/'release/v0.8.2/漫剧工坊/_internal'))
import hongguo_source as h,source_imports as si
BASE=Path(tempfile.mkdtemp(prefix='locked-source-',dir=ROOT/'tmp'));checks=[];sid='123456';url=h.BASE+'/detail?series_id='+sid
def check(name,value=True):assert value,name;checks.append(name)
def cell(n,marker=''):
    return f'<div class="pc-episode-cell-test pc-episode-item-test"><div class="pc-episode-cell-text-test">{n}</div>{marker}</div>'
for label,marker in [('css','<span class="pc-lock-overlay-test"></span>'),('aria','<span aria-label="已锁定"></span>'),('data','<svg data-lucide="lock"></svg>')]:
    check(label+'_explicit_marker_identified',h.locked_episodes(h.DOM(cell(51,marker)).root)==[51])
check('missing_href_alone_not_called_locked',h.locked_episodes(h.DOM(cell(51)).root)==[])
actual=(ROOT/'tmp/locked-public-page/player.html')
if actual.exists():
    locks=h.locked_episodes(h.DOM(actual.read_text('utf-8')).root)
    check('actual_public_player_snapshot_recognizes_locked_51_to_60',set(range(51,61)).issubset(locks))
check('unrelated_lock_text_does_not_mark_all_episodes',h.locked_episodes(h.DOM('<h1>锁定目标</h1>'+cell(1)).root)==[])
def player(n,locked=False):
    route=h.BASE+f'/player/{sid}/{700000+n}';media=h.BASE+f'/video/public/{700000+n}/360p.mp4'
    return ''.join('<script type="application/ld+json">'+json.dumps(o)+'</script>' for o in [
        {'@type':'TVEpisode','episodeNumber':n,'url':route}, {'@type':'VideoObject','contentUrl':media}])+f'<video src="{media}"></video>'+(cell(n,'<span class="pc-lock-overlay-test"></span>') if locked else '')
try:h.parse_player(player(2,True),sid,2,h.BASE+f'/player/{sid}/700002')
except h.SourceLocked:check('locked_episode_never_returns_video_as_success')
else:raise AssertionError('lock ignored')
class Stream:
    calls=0
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read1(self,n):
        self.calls+=1
        if self.calls>1:raise AssertionError('locked page must not wait for footer')
        return player(2,True).encode()
stream=Stream()
with patch.object(h,'response',return_value=stream):
    try:h.fetch_html(h.BASE+f'/player/{sid}/700002',expected_episode=2)
    except h.SourceLocked:check('streaming_locked_page_exits_once_without_retry',stream.calls==1)
    else:raise AssertionError('source lock swallowed')
meta={'kind':'detail','platform':'hongguo_web','seriesId':sid,'url':url,'title':'锁状态验收','intro':'','coverUrl':'','lockedEpisodes':[],
      'episodes':[{'number':n,'playerUrl':h.BASE+f'/player/{sid}/{700000+n}'} for n in (1,2,3)]}
fetches=[];downloads=[]
def fetch(url,cancel=None,**kwargs):
    fetches.append(url)
    if '/detail?' in url:return ''
    n=int(url.rsplit('/',1)[-1])-700000;return player(n,n==2)
def download(url,path,cancel,progress,image=False):downloads.append(url);path.write_bytes(b'test');progress(4,4)
adapter=types.SimpleNamespace(ACCESS=h.Access(interval=.01),site_url=h.site_url,Cancelled=h.Cancelled,SourceLimited=h.SourceLimited,fetch_html=fetch,
    parse_detail=lambda *a:copy.deepcopy(meta),parse_player=h.parse_player,download=download)
m=si.ImportManager(BASE/'data',lambda *a:'project',lambda p:{'duration':1},adapter);m.start_worker=lambda:None
row=m.get(m.start({'url':url,'directory':str(BASE),'video':True,'episodes':[1,2,3],'batchSize':3,'confirmBatches':False,'downloadConcurrency':2})['id']);m.run()
check('one_locked_episode_does_not_block_other_available',row['done']==2 and row['status']=='failed')
check('locked_episode_not_refetched_or_downloaded',fetches.count(h.BASE+f'/player/{sid}/700002')==1 and all('/700002/' not in u for u in downloads))
check('diagnostic_marks_lock_explicitly',m.report(row['id'])['items'][1]['errorCode']=='source_locked')
meta['lockedEpisodes']=[2];meta['episodes']=[e for e in meta['episodes'] if e['number']!=2];fetches.clear();m.cache.clear();m.control(row['id'],'resume');m.run()
check('known_locked_catalogue_skips_player_request',not any('/player/' in u for u in fetches) and m.report(row['id'])['items'][1]['errorCode']=='source_locked')
report={'compiled':COMPILED,'passed':len(checks),'checks':checks,'explicitMarkerFixtures':True,'realPublicPlayerSnapshot':actual.exists(),'externalUnlockTested':False,'base':str(BASE)}
(ROOT/('tmp/locked-source-compiled.json' if COMPILED else 'tmp/locked-source-source.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
