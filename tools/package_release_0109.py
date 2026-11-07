"""Deliver the verified combined desktop and companion-app installer."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[1];VERSION='v0.10.9'
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT));import licensing
RECORD=ROOT/'versions'/VERSION;DIST=ROOT/'release'/VERSION/'漫剧工坊';OUT=DIST.parent/'对外发送'
def digest(p):
    with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(name):return json.loads((RECORD/name).read_text('utf-8-sig'))
def hashes_match(rows):
    def match(row):return digest(row[0])==row[1]
    with ThreadPoolExecutor(max_workers=8) as pool:return all(pool.map(match,rows))
inputs=read('build-inputs.json');installed=read('installation-report.json');native=read('native-ui-report.json')
payload=read('payload-verification.json');scan=read('defender-scan.json')
upgrade=read('upgrade-scenarios.json')
settings=read('settings-reset-scenarios.json');reset_install=read('installation-reset-report.json')
assert upgrade['ok'] and upgrade['originalRegistryRestored']
assert settings['ok'] and reset_install['ok']
assert installed['upgradeFromVersion']=='v0.10.8' and installed['keepUserConfiguration']
assert reset_install['upgradeFromVersion']=='v0.10.8' and not reset_install['keepUserConfiguration']
assert reset_install['originalRegistryRestored'] and reset_install['originalShortcutsRestored']
assert 'unchecked_keep_configuration_resets_software_settings' in reset_install['checks']
assert 'reset_preserves_project_account_history_and_future_fields' in reset_install['checks']
assert 'configuration_is_preserved_by_default' in installed['checks']
assert 'registered_old_version_removed_before_new_install' in installed['checks']
assert 'old_installation_personal_files_preserved' in installed['checks']
assert hashes_match([(ROOT/name,sha) for name,sha in inputs['sourceSha256'].items()]),'Build source changed'
print('PASS current_build_inputs_unchanged',flush=True)
assert all(digest(Path(name))==sha for name,sha in inputs['runtimeSha256'].items()),'Build runtime changed'
assert installed['ok'] and installed['originalRegistryRestored'] and installed['originalShortcutsRestored']
assert native['ok'] and native['actualInstalledExecutable'] and native['xiaovmiao']['realBundledLaunch']
companion=read('xiaovmiao-reconstructed-startup.json')
assert companion['ok'] and companion['realUserProfileUsed'] is False
assert companion['version']=='3.1.0' and companion['build']==17
assert native['xiaovmiao']['mode']=='local-reconstructed'
assert 'installed_xiaovmiao_persists_profile_for_future_updates' in native['checks']
assert 'installed_xiaovmiao_initializes_its_own_local_database' in native['checks']
assert 'installed_promotion_has_no_retired_publish_stages' in native['checks']
assert not payload['customerKeysFound'] and not payload['privateMaterialsFound']
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled']
manifest=licensing.signed_payload(json.loads((DIST/'integrity.json').read_text('utf-8-sig')))
assert manifest.get('product')=='ManjuStudio' and manifest.get('kind')=='application'
home=DIST.resolve()
def verify_file(item):
    p=(home/item['path']).resolve()
    return p.is_relative_to(home) and p.is_file() and p.stat().st_size==item['bytes'] and digest(p)==item['sha256']
with ThreadPoolExecutor(max_workers=8) as pool:
    assert all(pool.map(verify_file,manifest['files'])),'Signed distribution file changed'
print('PASS signed_distribution_paths_sizes_and_hashes',flush=True)
assert manifest['version']==VERSION[1:]
installer=DIST.parent/'漫剧工坊-安装程序-0.10.9.exe'
assert digest(installer)==scan['installerSha256'] and digest(DIST/'漫剧工坊.exe')==scan['executableSha256']
module=json.loads((DIST/'modules/xiaovmiao/module.json').read_text('utf-8'))
assert installed['xiaovmiaoFiles']==len(module['files'])==native['xiaovmiao']['bundledFiles']
assert hashes_match([(DIST/'modules/xiaovmiao/程序'/name,sha) for name,sha in module['files'].items()])
print('PASS all_companion_files_verified',flush=True)
old=json.loads((ROOT/'versions/v0.10.8/build-record.json').read_text('utf-8'))
assert digest(ROOT/'release/v0.10.8'/old['installer']['file'])==old['installer']['sha256'],'Old installer changed'
OUT.mkdir(parents=True,exist_ok=True);destination=OUT/installer.name
if destination.exists():raise FileExistsError('Refusing to replace delivered installer')
shutil.copy2(installer,destination);assert digest(destination)==digest(installer)
readme=OUT/'安装与更新说明.txt'
readme.write_text('''漫剧工坊 0.10.9（含小v喵）安装与更新说明
发布日期：2026年11月5日

运行“漫剧工坊-安装程序-0.10.9.exe”，即可一并安装漫剧工坊和小v喵程序。
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
本次随附更新后的小v喵3.1.0 build17重建版本（local-reconstructed），入口为vcat-local.exe。
本版使用新版workspace数据布局，已核对程序文件、实际启动、6个IPC通道、43个数据库模型和本地查询。
安装包只包含程序，不携带个人账号、Cookie或数据库。
已有明确选择的数据目录继续保留；新旧数据布局分别使用，不自动合并或清空旧数据库。
真实账号、评论、私信、发布与云同步没有在本次打包中重新验收。
原来已经配置的小v喵路径继续优先使用，不会自动覆盖或迁移那里的本地数据。
不要删除原修复版目录及其中“本地数据”。安装包不含你原来的账号、数据库、缓存或使用记录。
随附程序首次准备还会在当前用户数据目录创建独立的程序运行副本，需额外预留磁盘空间。

本次更新：
1. 将小v喵模块整体更新为当前选定的3.1.0 build17重建版本。
2. 支持解包程序入口、从模块清单读取EXE名，并按新版数据布局准备运行目录。
3. 原配置及数据目录继续使用，旧程序与旧数据保留。

继续保留：
新版安装界面、可选卸载旧版本和默认保留用户配置。
短剧提审、本地剧情识别、高光混剪、成片保存及混剪中断恢复。

本安装包不包含客户API密钥、签发工具或授权私钥。
本次不更换离线AI引擎。已有v2-cu128的电脑仅更新主程序；新电脑使用本地AI功能仍需另外导入引擎包。
安装、启动及功能检查在隔离目录与临时测试数据中完成，未覆盖本机正式安装与现有小v喵数据。
''','utf-8-sig')
rows=[{'file':p.name,'bytes':p.stat().st_size,'sha256':digest(p)} for p in (destination,readme)]
(OUT/'SHA256SUMS.txt').write_text(''.join(r['sha256']+'  '+r['file']+'\n' for r in rows),'utf-8-sig')
record={'version':VERSION[1:],'date':'2026-11-05','installer':rows[0],'deliveryDirectory':str(OUT),
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
    'reconstructedCompanionVersion':companion['version'],'reconstructedCompanionBuild':companion['build'],
    'reconstructedCompanionStartupChecks':len(companion['checks']),
    'xiaovmiaoProfilePersistenceVerified':True,
    'offlineEngineChanged':False,'offlineEngineIncluded':False,'oldInstallerPreserved':True,
    'defenderCustomScanNoMatchingDetection':True,'defenderEnabledDuringVerification':True,'deliveryFiles':rows}
(RECORD/'build-record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n','utf-8')
print(json.dumps({'installer':str(destination),'bytes':destination.stat().st_size,'sha256':rows[0]['sha256'],
    'installedNativeUIChecks':len(native['checks']),'xiaovmiaoFiles':len(module['files'])},ensure_ascii=True))
