"""Independent final-artifact manager acceptance, with video and metadata only."""
from pathlib import Path
import argparse,copy,hashlib,json,math,os,re,sys,tempfile,time,datetime

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--engine-dir',type=Path,required=True)
parser.add_argument('--expected-sha',required=True)
parser.add_argument('--expected-version',required=True)
parser.add_argument('--compiled',action='store_true')
parser.add_argument('--release-version',default='v0.10.12')
args=parser.parse_args()
engine=args.engine_dir.resolve()
if not engine.is_relative_to((ROOT/'tmp').resolve()):raise ValueError('Use a final-engine mirror inside workspace tmp')
BASE=Path(tempfile.mkdtemp(prefix='native-final-manager-',dir=ROOT/'tmp'))
os.environ['MANJU_DATA']=str(BASE/'data');sys.dont_write_bytecode=True
sys.path[:0]=([str(ROOT/'release'/args.release_version/'漫剧工坊/_internal')] if args.compiled else [])+[str(ROOT),str(ROOT/'vendor')]
import server as s,source_imports as si,guoapp_source as native

TARGETS=[
 {'seriesId':'7697470547197709336','episode':26,'videoId':'7697475425370377241','expectedSeconds':57.54,'referenceSha256':'d817e11376fe780de5f141aff7d67b1606a3a9cbf0a2923b6e2a13e2da32fa5e'},
 {'seriesId':'7697470547197709336','episode':37,'videoId':'7697474908812495897','expectedSeconds':54.289,'referenceSha256':'b368eda025b6b0054f88544d9158259c5553d82ed62af42d8e79b3b6ef0975ce'},
 {'seriesId':'7660103833745378328','episode':1,'videoId':'7660106334662052888','expectedSeconds':167.138,'referenceSha256':'3c97154bf7c3edb8fbfb4dc3fee96267c5788e5d723ac805b34eb86123ca6b74'},
]
report={'date':'2026-11-07','checkedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ok':False,'base':str(BASE),'data':str(BASE/'data'),'sourceRoot':str(BASE/'素材'),'engineDir':str(engine),'expectedEngineSha256':args.expected_sha,
 'expectedEngineVersion':args.expected_version,'compiled':args.compiled,'moduleOrigins':{m.__name__:m.__file__ for m in (s,si,native)},
 'realAccountsUsed':False,'paidCalls':False,'sourceImagesRequested':0,'oldUserTasksModified':False,
 'normalExistingMaterializer':True,'newKeyDerivationOrAccessBypass':False,'checks':[],'targets':[],
 'wholeSeriesVerified':False,'vipNotMapped':True,'rightsUnknown':True,
 'rightsProvenance':'Native VIP defaults are not entitlement proof. This test exercises only normal server-provided plans under the user-authorized existing download workflow.'}
latest=ROOT/'tmp'/('native-packaged-manager-'+args.release_version+'-latest.json')
def flush():
 text=json.dumps(report,ensure_ascii=False,indent=2)
 latest.write_text(text,'utf-8');(BASE/'report.json').write_text(text,'utf-8')
def check(name,condition,record=None):
 if not condition:raise AssertionError(name)
 (record if record is not None else report)['checks'].append(name);flush();print('PASS '+name,flush=True)
def safe_error(error):return re.sub(r'https?://[^\s\"<>]+','[URL hidden]',s.diagnostic_text(error))
manager=None;started=time.monotonic()
try:
 check('compiled_modules_match_selected_mode',not args.compiled or all(m.__file__.endswith('.pyd') for m in (s,si,native)))
 manifest=json.loads((engine/'manifest.json').read_text('utf-8'));engine_file=engine/'duanju_core.dll'
 check('final_dll_hash_and_manifest_match',s.sha256(engine_file)==args.expected_sha==manifest['sha256'])
 check('final_dll_version_matches',manifest['version']==args.expected_version)
 report['component']={key:manifest.get(key) for key in ('version','sourceCommit','sha256','protectedPreviewBlocked','expectedDurationBridge','validationScope')}
 s.STATE['config']['output']=str(BASE/'outputs');(BASE/'素材').mkdir()
 manager=s.source_manager();manager.core.root=engine
 original_call=manager.core.call
 def metadata_and_video_call(payload):
  if payload.get('action') in ('cover','prepareCover'):
   report['sourceImagesRequested']+=1;raise AssertionError('Source image actions are disabled for acceptance')
  return original_call(payload)
 manager.core.call=metadata_and_video_call;manager.core.load()
 settings=manager.core.call({'action':'resourceSettings'})
 settings={key:value for key,value in settings.items() if key in ('proxyMode','proxyURL','proxyUrl','catalogConcurrency','catalogIntervalMs','downloadConcurrency','downloadBySource')}
 settings.update(proxyMode='direct',proxyURL='',proxyUrl='',downloadConcurrency=1)
 manager.core.call({'action':'saveResourceSettings','settings':settings})
 original_resolve=manager.resolve
 def no_images(*a,**k):
  result=copy.deepcopy(original_resolve(*a,**k))
  if result.get('kind')=='detail':result['coverUrl']=''
  return result
 manager.resolve=no_images
 original_download=manager.h.download
 def video_only(url,path,cancel,progress,image=False):
  if image:
   report['sourceImagesRequested']+=1;raise AssertionError('Source images are disabled for acceptance')
  return original_download(url,path,cancel,progress,image)
 manager.h.download=video_only
 original_fetch=manager.h.fetch_media
 captured_plans=[]
 def capture_plan(url,cancel,progress):
  plan=original_fetch(url,cancel,progress)
  captured_plans.append({'expectedDurationSeconds':plan.get('expectedDurationSeconds'),'hasKey':bool(plan.get('decryptionKey')),
   'local':bool(plan.get('local')),'quality':plan.get('quality'),'transferMode':plan.get('transferMode')})
  return plan
 manager.h.fetch_media=capture_plan
 for target in TARGETS:
  item={**target,'checks':[],'ok':False};report['targets'].append(item);flush()
  detail=manager.resolve('guoapp://hongguo/detail/'+target['seriesId'])
  entry=next(row for row in detail['episodes'] if row['number']==target['episode'])
  check('series_and_episode_match_independent_reference',detail['seriesId']==target['seriesId'] and entry['number']==target['episode'] and entry['nativeChapter']['id']=='hongguo:'+target['seriesId']+':'+target['videoId'],item)
  item.update(title=detail['title'],catalogEpisodeCount=detail['totalEpisodes'],rawNativeVip=entry['nativeChapter'].get('vip'),vipNotMapped=True,rightsUnknown=True)
  plans_before=len(captured_plans)
  task=manager.start({'url':detail['url'],'directory':str(BASE/'素材'),'video':True,'episodes':[target['episode']],
   'downloadConcurrency':1,'segmentedDownload':False,'adaptiveDownloads':False})
  item['taskId']=task['id'];flush();deadline=time.monotonic()+90
  while time.monotonic()<deadline:
   row=next(value for value in manager.list() if value['id']==task['id'])
   if row['status'] not in ('queued','running'):break
   time.sleep(.2)
  else:
   manager.cancel(task['id']);raise TimeoutError('Final manager target did not finish within 90 seconds')
  item['task']={key:row.get(key) for key in ('status','stage','done','savedDirectory','projectId')}
  item['errors']=[{'episode':i['number'],'error':safe_error(i['error'])} for i in row['items'] if i.get('error')]
  check('actual_manager_download_and_import_completed',row['status']=='completed' and row.get('done')==1 and bool(row.get('projectId')),item)
  check('download_plan_retains_declared_full_duration',len(captured_plans)==plans_before+1 and captured_plans[-1]['local'] and isinstance(captured_plans[-1]['expectedDurationSeconds'],(int,float)) and math.isfinite(captured_plans[-1]['expectedDurationSeconds']) and abs(captured_plans[-1]['expectedDurationSeconds']-target['expectedSeconds'])<=.05,item)
  item['plan']=captured_plans[-1]
  project=s.get_project(row['projectId']);videos=[v for v in project['videos'] if v.get('sourceEpisode')==target['episode']]
  check('imported_identity_matches_requested_video',len(videos)==1 and str(videos[0].get('sourceEpisodeId'))==target['videoId'],item)
  path=Path(videos[0]['path']);checksum=s.sha256(path)
  records=json.loads((Path(row['savedDirectory'])/'下载记录.json').read_text('utf-8'))
  matching=[r for r in records if r['episode']==target['episode']]
  check('manifest_identity_and_sha_match_real_file',len(matching)==1 and matching[0]['episodeId']==target['videoId'] and matching[0]['sha256']==checksum,item)
  record=matching[0]
  check('manifest_records_full_duration_verification',record.get('fullDurationVerified') is True and abs(record['expectedDurationSeconds']-target['expectedSeconds'])<=.05,item)
  metadata=json.loads((Path(row['savedDirectory'])/'剧集资料.json').read_text('utf-8'))
  check('saved_metadata_retains_requested_series',metadata['seriesId']==target['seriesId'] and metadata['platform']=='guoapp_hongguo',item)
  info=s.probe(path);item['media']={**info,'path':str(path),'sha256':checksum,'bytes':path.stat().st_size}
  check('media_has_video_audio_and_matches_full_declared_duration',bool(info.get('audio')) and info.get('width',0)>0 and info.get('height',0)>0 and abs(info['duration']-target['expectedSeconds'])<=max(.5,min(2,target['expectedSeconds']*.02)),item)
  s.ff(['-xerror','-err_detect','explode','-i',str(path),'-map','0:v:0','-map','0:a:0','-f','null','-'])
  check('all_video_and_audio_frames_decode_without_error',True,item)
  check('full_decode_preserves_file_sha256',s.sha256(path)==checksum,item)
  item['matchesIndependentReferenceSha256']=checksum==target['referenceSha256'];item['ok']=True;flush()
 check('all_three_samples_completed_in_one_fresh_manager',len(report['targets'])==3 and all(t['ok'] for t in report['targets']))
 check('all_three_original_hashes_remain_unchanged_after_queue',all(s.sha256(Path(t['media']['path']))==t['media']['sha256'] for t in report['targets']))
 all_videos=[v for p in s.STATE['projects'] for v in p['videos']]
 check('isolated_state_contains_only_requested_three_videos',len(all_videos)==3 and {(v.get('sourceEpisode'),str(v.get('sourceEpisodeId'))) for v in all_videos}=={(t['episode'],t['videoId']) for t in TARGETS})
 check('final_artifact_unchanged_through_acceptance',s.sha256(engine_file)==args.expected_sha)
 check('no_source_images_requested_or_saved',report['sourceImagesRequested']==0 and not any(p.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.heic','.avif','.gif') for p in BASE.rglob('*') if p.is_file()))
 check('no_publication_tasks_created',not s.STATE.get('promotionTasks'))
 report['ok']=True
except Exception as error:
 report['error']=safe_error(error)
finally:
 if manager:
  try:manager.shutdown()
  except Exception as error:report['shutdownError']=safe_error(error)
 try:s.shutdown_jobs()
 except Exception as error:report['jobsShutdownError']=safe_error(error)
 report['elapsedSeconds']=round(time.monotonic()-started,3);flush()
 if report['ok']:
  pointer={key:report[key] for key in ('date','base','data','sourceRoot','ok','sourceImagesRequested','wholeSeriesVerified')}
  pointer.update(version=args.expected_version,dllSha256=args.expected_sha,engineDir=str(engine),report=str(BASE/'report.json'),
   projectIds=list(dict.fromkeys(t['task']['projectId'] for t in report['targets'])),
   checks=report['checks']+[str(t['episode'])+':'+c for t in report['targets'] for c in t['checks']],
   videos=[{'projectId':t['task']['projectId'],'seriesId':t['seriesId'],'videoId':t['videoId'],'episode':t['episode'],
    'path':t['media']['path'],'sha256':t['media']['sha256'],'expectedSeconds':t['plan']['expectedDurationSeconds'],
    'actualSeconds':t['media']['duration'],'audio':t['media']['audio'],'bytes':t['media']['bytes'],
    'width':t['media']['width'],'height':t['media']['height'],'fullAvDecodePassed':True} for t in report['targets']])
  (ROOT/'tmp'/('packaged-hongguo-collection-'+args.release_version+'.json')).write_text(json.dumps(pointer,ensure_ascii=False,indent=2),'utf-8')
 print(json.dumps(report,ensure_ascii=False),flush=True)
sys.exit(0 if report['ok'] else 1)
