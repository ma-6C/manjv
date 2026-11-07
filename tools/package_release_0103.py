"""Prepare only the scanned, installed and checked storage-path release."""
from pathlib import Path
import hashlib,json,shutil,sys

ROOT=Path(__file__).resolve().parents[1];VERSION='v0.10.3'
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT));import licensing
RECORD=ROOT/'versions'/VERSION;DIST=ROOT/'release'/VERSION/'漫剧工坊';OUT=DIST.parent/'对外发送'
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
inputs=json.loads((RECORD/'build-inputs.json').read_text('utf-8'))
assert all(digest(ROOT/name)==sha for name,sha in inputs['sourceSha256'].items()),'Build input changed'
assert all(digest(Path(name))==sha for name,sha in inputs['runtimeSha256'].items()),'Runtime input changed'
installed=json.loads((RECORD/'installation-report.json').read_text('utf-8'))
native=json.loads((RECORD/'native-ui-report.json').read_text('utf-8'))
payload=json.loads((RECORD/'payload-verification.json').read_text('utf-8'))
scan=json.loads((RECORD/'defender-scan.json').read_text('utf-8-sig'))
assert installed['ok'] and installed['originalRegistryRestored'] and installed['originalShortcutsRestored']
assert native['ok'] and native['actualInstalledExecutable']
assert 'installed_compiled_backend_saves_and_creates_selected_folders' in native['checks']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
for name in ('storage-check','storage-ui'):
    report=json.loads((ROOT/'tmp'/(name+'-latest.json')).read_text('utf-8'));assert report['ok']
    (RECORD/(name+'-report.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
previous=getattr(sys,'frozen',None);sys.frozen=True
try:licensing.verify_distribution(DIST)
finally:
    if previous is None:del sys.frozen
    else:sys.frozen=previous
manifest=licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest['version']==VERSION[1:]
installer=DIST.parent/'漫剧工坊-安装程序-0.10.3.exe'
assert digest(installer)==scan['installerSha256']
assert digest(DIST/'漫剧工坊.exe')==scan['executableSha256']
OUT.mkdir(parents=True,exist_ok=True);destination=OUT/installer.name
if destination.exists():raise FileExistsError('Refusing to replace customer artifact')
shutil.copy2(installer,destination);assert digest(destination)==digest(installer)
readme=OUT/'安装与更新说明.txt'
readme.write_text('''漫剧工坊 0.10.3 安装与更新说明
发布日期：2026年11月1日

退出漫剧工坊，运行“漫剧工坊-安装程序-0.10.3.exe”。老用户选择原安装目录更新。
项目、任务历史和设备授权继续使用原用户数据位置。本次验收在临时目录安装，未覆盖本机正式安装。

选择保存文件夹：
文案与封面 → 右上角“设置” → “存储位置” → 选择文件夹 → “保存存储位置”。
软件会检查文件夹能否写入，成功后记住位置。文案、封面和处理视频使用“文件保存位置”；
新工程图保存在其“工程图”子文件夹，新剪映工程默认保存在其“剪映工程”子文件夹。
“剪映工程保存位置”可单独指定其他磁盘；留空则跟随文件保存位置。
也可在“剪映工程与截图 → 设置”直接选择保存目录，点击“完成”保存，无需展开高级设置。
已有任务保留创建时的配置；新位置用于后续新任务，原文件不会自动搬移或删除。

原视频已经移动：
文案与封面 → 选择剧集 → “重新定位素材”，选择现在包含该剧完整视频的文件夹。
也可从素材详情操作。软件核对原文件名、大小和视频信息，保留剧名、简介、备注及历史记录。
旧制作任务的素材快照不改写，后续视频制作请重新发起新任务。
AI 改写剧名与简介已移除对原视频文件的依赖，视频路径失效不再阻止纯文案改写。

剪映工程已经移动：
剪映工程与截图 → 对应集的“详情” → “重新定位工程”。
请选择含 manju_project.json、draft_content.json 和 Resources 的完整工程文件夹。
软件校验工程归属和素材完整性，更新任务记录并重连工程内素材。
然后重新导入剪映，手动打开对应草稿后再生成工程图。重连不代表剪映画面已验证。
文件已删除或没有完整副本时，需要找回原文件或重新生成；更换保存目录不会恢复已删除文件。

接口和本地 AI 引擎：
接口设置仍保存在本机，API 密钥只用于本次运行，本安装包不包含客户密钥。
获取模型列表不代表服务支持云端视频去字幕；当前客户服务默认去字幕路径仍未通过真实短片测试。
本次不更换既有离线 AI 引擎。已安装 v2-cu128 的电脑仅更新主程序即可，无需重复导入引擎。

验证范围：
已完成文件/路径回归、页面操作、独立目录实际安装、设备授权及安装版保存目录检查。
已对本次交付目录执行本机 Defender 自定义扫描，未发现匹配本版本的检测记录。
未在客户电脑完成验收；客户原视频和旧工程能否找回取决于实际文件是否仍然存在。
''','utf-8-sig')
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in (destination,readme)]
(OUT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in rows),'utf-8-sig')
record={'version':VERSION[1:],'date':'2026-11-01','installer':rows[0],'deliveryDirectory':str(OUT),
    'applicationIntegritySigned':True,'signedFiles':len(manifest['files']),'recordedBuildInputs':len(inputs['sourceSha256']),
    'installerExecuted':True,'installationWasIsolated':True,'originalRegistryAndShortcutsRestored':True,
    'actualInstalledDesktopStarted':True,'installedStorageSettingsVerified':True,'installedNativeUIChecks':len(native['checks']),
    'sourcePathChecks':26,'sourceStorageUIChecks':16,'sourceContentSettingsUIChecks':25,'sourceProviderChecks':43,
    'projectEvidenceChecks':25,'projectImportChecks':26,'projectCompletionChecks':13,'prerequisiteChecks':36,
    'compiledSigningChecks':31,'customerKeysIncluded':False,'customerHardwareTested':False,'oldFilesMovedBySettings':False,
    'customerCloudSubtitlePassed':False,'offlineEngineChanged':False,'offlineEngineIncluded':False,
    'defenderCustomScanNoMatchingDetection':True,'defenderEnabledDuringVerification':True,'deliveryFiles':rows}
(RECORD/'build-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps({'installer':str(destination),'bytes':destination.stat().st_size,'sha256':rows[0]['sha256'],'installedNativeUIChecks':len(native['checks'])},ensure_ascii=True))
