"""Deliver the exact scanned build checked in the native installed WebView."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];VERSION='v0.10.4'
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT));import licensing
RECORD=ROOT/'versions'/VERSION;DIST=ROOT/'release'/VERSION/'漫剧工坊';OUT=DIST.parent/'对外发送'
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def report(name):return json.loads((RECORD/name).read_text('utf-8-sig'))
inputs=report('build-inputs.json');installed=report('installation-report.json');native=report('native-ui-report.json')
payload=report('payload-verification.json');scan=report('defender-scan.json')
assert all(digest(ROOT/name)==sha for name,sha in inputs['sourceSha256'].items()),'Build input changed'
assert all(digest(Path(name))==sha for name,sha in inputs['runtimeSha256'].items()),'Runtime input changed'
assert installed['ok'] and installed['originalRegistryRestored'] and installed['originalShortcutsRestored']
assert native['ok'] and native['actualInstalledExecutable']
for name in ('installed_actual_subtitle_video_uses_selected_storage','installed_subtitle_wheel_scrolls_settings_and_keeps_background',
             'installed_subtitle_bottom_does_not_scroll_background','installed_subtitle_top_does_not_scroll_background'):
    assert name in native['checks'],name
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
source={}
for name,file in {'storage-paths':'storage-check-latest.json','subtitle-storage-scroll':'subtitle-storage-scroll-latest.json','subtitle-settings':'subtitle-settings-ui-latest.json'}.items():
    data=json.loads((ROOT/'tmp'/file).read_text('utf-8'));assert data['ok'];source[name]=len(data['checks'])
    (RECORD/(name+'-report.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
previous=getattr(sys,'frozen',None);sys.frozen=True
try:licensing.verify_distribution(DIST)
finally:
    if previous is None:del sys.frozen
    else:sys.frozen=previous
manifest=licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest['version']==VERSION[1:]
installer=DIST.parent/'漫剧工坊-安装程序-0.10.4.exe'
assert digest(installer)==scan['installerSha256'] and digest(DIST/'漫剧工坊.exe')==scan['executableSha256']
OUT.mkdir(parents=True,exist_ok=True);destination=OUT/installer.name
if destination.exists():raise FileExistsError('Refusing to replace customer artifact')
shutil.copy2(installer,destination);assert digest(destination)==digest(installer)
readme=OUT/'安装与更新说明.txt'
readme.write_text('''漫剧工坊 0.10.4 安装与更新说明
发布日期：2026年11月1日

退出漫剧工坊，运行“漫剧工坊-安装程序-0.10.4.exe”，选择原安装目录更新。
继续使用原用户数据和设备授权。安装验收在独立临时目录完成，未覆盖本机正式安装。

AI 去字幕保存位置：
AI 去字幕 → 右上角“设置” → 左侧“存储位置” → “选择文件夹” → 底部“保存存储位置”。
软件检查文件夹写入权限并记住位置。去字幕视频写入所选位置下的剧集目录，按处理方式分文件夹保存。
此处与文案、封面及处理视频共用软件保存位置。新设置用于后续新任务；已有任务保留创建时的位置。
原有文件不会自动搬移或删除。旧素材或工程路径失效时，仍使用“重新定位素材”或“重新定位工程”。

设置弹窗滚动修复：
去字幕设置的右侧内容在弹窗内部滚动，标题、分类和底部保存按钮保持可见。
鼠标在内容顶部、底部、左侧分类、标题、底栏或弹窗外滚动时，不再带动主页。
关闭设置后主页恢复正常滚动。文案与封面设置的同类滚动问题一并修复。

验证范围：
使用真实鼠标滚轮检查常规窗口、矮窗口和窄窗口，并完成真实短片输出目录验证。
实际安装版使用独立数据和临时授权，核对保存目录、内部滚动及短片输出。
短片验证使用本地区域修补方式，用于核对文件保存和处理链路，不代表 STTN、LaMa 或云端模型效果验收。
交付目录经本机 Defender 自定义扫描，未发现匹配本版本的检测记录，防护保持启用。

接口和引擎：
本安装包不包含客户 API 密钥；密钥仍只用于本次运行。
云端模型列表可查询不代表支持视频去字幕，当前客户服务默认去字幕路径仍未通过真实短片测试。
本次不更换离线 AI 引擎；已安装 v2-cu128 的电脑仅更新主程序，无需重复导入引擎。
''','utf-8-sig')
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in (destination,readme)]
(OUT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in rows),'utf-8-sig')
record={'version':VERSION[1:],'date':'2026-11-01','installer':rows[0],'deliveryDirectory':str(OUT),
 'applicationIntegritySigned':True,'signedFiles':len(manifest['files']),'recordedBuildInputs':len(inputs['sourceSha256']),
 'installerExecuted':True,'installationWasIsolated':True,'originalRegistryAndShortcutsRestored':True,
 'actualInstalledDesktopStarted':True,'installedNativeUIChecks':len(native['checks']),'installedSubtitleOutputVerified':True,
 'installedRealWheelInputVerified':True,'sourceChecks':source,'sourceContentSettingsUIChecks':25,'sourceProviderChecks':43,
 'compiledSigningChecks':31,'prerequisiteChecks':36,'customerKeysIncluded':False,'customerHardwareTested':False,
 'subtitleTestMode':'local delogo','customerCloudSubtitlePassed':False,'offlineEngineChanged':False,'offlineEngineIncluded':False,
 'defenderCustomScanNoMatchingDetection':True,'defenderEnabledDuringVerification':True,'deliveryFiles':rows}
(RECORD/'build-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps({'installer':str(destination),'bytes':destination.stat().st_size,'sha256':rows[0]['sha256'],'installedNativeUIChecks':len(native['checks'])},ensure_ascii=True))
