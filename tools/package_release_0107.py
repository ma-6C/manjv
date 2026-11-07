"""Deliver the verified combined desktop and companion-app installer."""
from pathlib import Path
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];VERSION='v0.10.7'
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT));import licensing
RECORD=ROOT/'versions'/VERSION;DIST=ROOT/'release'/VERSION/'漫剧工坊';OUT=DIST.parent/'对外发送'
def digest(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(name):return json.loads((RECORD/name).read_text('utf-8-sig'))
inputs=read('build-inputs.json');installed=read('installation-report.json');native=read('native-ui-report.json')
payload=read('payload-verification.json');scan=read('defender-scan.json')
upgrade=read('upgrade-scenarios.json')
settings=read('settings-reset-scenarios.json');reset_install=read('installation-reset-report.json')
assert upgrade['ok'] and upgrade['originalRegistryRestored']
assert settings['ok'] and reset_install['ok']
assert installed['upgradeFromVersion']=='v0.10.6' and installed['keepUserConfiguration']
assert reset_install['upgradeFromVersion']=='v0.10.6' and not reset_install['keepUserConfiguration']
assert reset_install['originalRegistryRestored'] and reset_install['originalShortcutsRestored']
assert 'unchecked_keep_configuration_resets_software_settings' in reset_install['checks']
assert 'reset_preserves_project_account_history_and_future_fields' in reset_install['checks']
assert 'configuration_is_preserved_by_default' in installed['checks']
assert 'registered_old_version_removed_before_new_install' in installed['checks']
assert 'old_installation_personal_files_preserved' in installed['checks']
assert all(digest(ROOT/name)==sha for name,sha in inputs['sourceSha256'].items()),'Build source changed'
assert all(digest(Path(name))==sha for name,sha in inputs['runtimeSha256'].items()),'Build runtime changed'
assert installed['ok'] and installed['originalRegistryRestored'] and installed['originalShortcutsRestored']
assert native['ok'] and native['actualInstalledExecutable'] and native['xiaovmiao']['realBundledLaunch']
assert 'installed_xiaovmiao_initializes_its_own_local_database' in native['checks']
assert 'installed_promotion_has_no_retired_publish_stages' in native['checks']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
previous=getattr(sys,'frozen',None);sys.frozen=True
try:licensing.verify_distribution(DIST)
finally:
    if previous is None:del sys.frozen
    else:sys.frozen=previous
manifest=licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest['version']==VERSION[1:]
installer=DIST.parent/'漫剧工坊-安装程序-0.10.7.exe'
assert digest(installer)==scan['installerSha256'] and digest(DIST/'漫剧工坊.exe')==scan['executableSha256']
module=json.loads((DIST/'modules/xiaovmiao/module.json').read_text('utf-8'))
assert installed['xiaovmiaoFiles']==len(module['files'])==native['xiaovmiao']['bundledFiles']
assert all(digest(DIST/'modules/xiaovmiao/程序'/name)==sha for name,sha in module['files'].items())
old=json.loads((ROOT/'versions/v0.10.6/build-record.json').read_text('utf-8'))
assert digest(ROOT/'release/v0.10.6'/old['installer']['file'])==old['installer']['sha256'],'Old installer changed'
OUT.mkdir(parents=True,exist_ok=True);destination=OUT/installer.name
if destination.exists():raise FileExistsError('Refusing to replace delivered installer')
shutil.copy2(installer,destination);assert digest(destination)==digest(installer)
readme=OUT/'安装与更新说明.txt'
readme.write_text('''漫剧工坊 0.10.7（含小v喵）安装与更新说明
发布日期：2026年11月4日

运行“漫剧工坊-安装程序-0.10.7.exe”，即可一并安装漫剧工坊和小v喵程序。
升级前退出正在运行的漫剧工坊，选择原安装目录更新；原用户数据和设备授权继续保留。
新版安装界面显示所需空间、目标磁盘可用空间，空间不足时不允许安装。

可选卸载旧版本：
检测到当前用户通过安装包注册的旧版时，会显示“发现已安装版本”，列出版本号及旧安装目录。
勾选“安装新版本前，先卸载旧版本”，点击“安装”后先移除旧程序，再安装新版。
不勾选时直接更新。首次安装会跳过此页。
“卸载旧版本时保留用户配置”默认勾选，仅在选择卸载旧版本时可以更改。
保持勾选会沿用原软件设置；取消勾选会先备份state.json，再只重置其中的软件设置字段。
项目记录、账号备注、历史记录、任务、授权、模型文件和小v喵本地数据不因取消此选项而清除。
原配置备份保存在用户数据目录的settings-backups中。
卸载旧版保留项目、成片、授权、模型和小v喵本地数据；仅按旧卸载清单移除程序文件。
旧程序文件被占用或卸载失败时停止安装，请退出旧程序并重试。
未注册的便携版不自动识别或清理。

小v喵的使用：
进入漫剧工坊后，点击左侧“小v喵”，会直接打开独立窗口。
新电脑无需再单独寻找或下载小v喵程序。首次打开会校验并准备本用户可写的运行目录，可能需要稍等。
本次随附小v喵本地修复版（offline-local），不是已验证全部联网发布功能的版本。
本次已验证随包启动、程序文件校验与独立本地数据库初始化；未验收账号登录、平台发布或云同步。
原来已经配置的小v喵路径继续优先使用，不会自动覆盖或迁移那里的本地数据。
不要删除原修复版目录及其中“本地数据”。安装包不含你原来的账号、数据库、缓存或使用记录。
随附程序首次准备还会在当前用户数据目录占用约692MiB空间，不计入安装目录程序文件的大小。

本次同时包含：
1. 简化后的“短剧提审”页面。
2. 识别剧情 → AI高光与混剪 → 生成推广视频，保留本地制作和成片保存。
3. 移除三平台发布挂载、点击跳转核对两个环节。
4. 混剪逐片段保存完成检查点，突然关闭后可恢复并复用已完成片段。

本安装包不包含客户API密钥、签发工具或授权私钥。
本次不更换离线AI引擎。已有v2-cu128的电脑仅更新主程序；新电脑使用本地AI功能仍需另外导入引擎包。
安装、启动及功能检查在隔离目录与临时测试数据中完成，未覆盖本机正式安装与现有小v喵数据。
''','utf-8-sig')
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in (destination,readme)]
(OUT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in rows),'utf-8-sig')
record={'version':VERSION[1:],'date':'2026-11-04','installer':rows[0],'deliveryDirectory':str(OUT),
    'applicationIntegritySigned':True,'signedFiles':len(manifest['files']),
    'recordedBuildInputs':len(inputs['sourceSha256']),'compiledModules':len(payload['compiledModules']),
    'installerExecuted':True,'installationWasIsolated':True,'originalRegistryAndShortcutsRestored':True,
    'actualInstalledDesktopStarted':True,'installedNativeUIChecks':len(native['checks']),
    'optionalOldVersionRemoval':True,'upgradeFromVersion':installed['upgradeFromVersion'],
    'oldVersionActuallyUninstalled':True,'oldPersonalFilesPreserved':True,'upgradeScenarioChecks':len(upgrade['checks']),
    'keepUserConfigurationDefaultChecked':True,'defaultConfigurationPreserved':True,
    'uncheckedConfigurationResetVerified':True,'settingsResetScenarioChecks':len(settings['checks']),
    'resetInstallationChecks':len(reset_install['checks']),
    'xiaovmiaoBundled':True,'xiaovmiaoFiles':len(module['files']),'xiaovmiaoMode':module['mode'],
    'realBundledXiaovmiaoLaunchVerified':True,'xiaovmiaoLocalDatabaseInitialized':True,
    'xiaovmiaoPlatformPublishingTested':False,'customerKeysIncluded':False,'customerHardwareTested':False,
    'offlineEngineChanged':False,'offlineEngineIncluded':False,'oldInstallerPreserved':True,
    'defenderCustomScanNoMatchingDetection':True,'defenderEnabledDuringVerification':True,'deliveryFiles':rows}
(RECORD/'build-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps({'installer':str(destination),'bytes':destination.stat().st_size,'sha256':rows[0]['sha256'],
    'installedNativeUIChecks':len(native['checks']),'xiaovmiaoFiles':len(module['files'])},ensure_ascii=True))
