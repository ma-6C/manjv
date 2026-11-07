"""Install into an isolated workspace folder and restore existing shell integration."""
from pathlib import Path
import argparse,ctypes,hashlib,json,os,subprocess,sys,tempfile,winreg

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--version',required=True)
parser.add_argument('--upgrade-from-version');parser.add_argument('--reset-user-settings',action='store_true');args=parser.parse_args()
if args.reset_user_settings and not args.upgrade_from_version:raise ValueError('Settings reset requires an isolated upgrade')
if not __import__('re').fullmatch(r'v\d+\.\d+\.\d+',args.version):raise ValueError('Invalid version')
sys.path.insert(0,str(ROOT));import licensing
BASE=Path(tempfile.mkdtemp(prefix='installer-smoke-'+args.version+'-',dir=ROOT/'tmp'))
TARGET=BASE/'installed';TARGET.mkdir()
USERDATA=BASE/'user configuration';USERDATA.mkdir()
original_state={'config':{'parallel':7,'source':'fixture-source','output':'fixture-output'},
                'projects':[{'id':'preserved-project','name':'原项目'}],'accounts':[{'name':'fixture-account'}],
                'logs':[{'message':'fixture history'}],'unknownFutureField':{'keep':True}}
state_bytes=json.dumps(original_state,ensure_ascii=False,indent=2).encode('utf-8')
(USERDATA/'state.json').write_bytes(state_bytes)
protected_user_files={}
for name in ['jobs.json','license.bin','models/keep.bin','components/xiaovmiao/本地数据/vcat.db','xiaovmiao.json']:
    p=USERDATA/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('preserved fixture '+name).encode());protected_user_files[p]=hashlib.sha256(p.read_bytes()).hexdigest()
if not TARGET.resolve().is_relative_to((ROOT/'tmp').resolve()):raise ValueError('Unexpected install directory')
installer=ROOT/'release'/args.version/('漫剧工坊-安装程序-'+args.version[1:]+'.exe')
scan=json.loads((ROOT/'versions'/args.version/'defender-scan.json').read_text('utf-8-sig'))
assert scan['noMatchingDetection'] and scan['antivirusEnabled'] and scan['realTimeProtectionEnabled'],'Candidate scan not clear'
with installer.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==scan['installerSha256'],'Installer changed after scan'
report={'version':args.version,'base':str(BASE),'installationDirectory':str(TARGET),'checks':[]}
def install(executable,target,remove=False,reset=False):
    if not target.resolve().is_relative_to(BASE.resolve()):raise ValueError('Install target escapes isolated test directory')
    command=subprocess.list2cmdline([str(executable),'/S',*(['/REMOVEOLD=1'] if remove else []),*(['/KEEPCONFIG=0'] if reset else [])])+' /D='+str(target)
    return subprocess.run(command,timeout=300,env={**os.environ,'MANJU_DATA':str(USERDATA)},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
def check(name,value=True):
    if not value:raise AssertionError(name)
    report['checks'].append(name);print('PASS '+name,flush=True)
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def special_folder(folder):
    buffer=ctypes.create_unicode_buffer(32768)
    if ctypes.windll.shell32.SHGetFolderPathW(None,folder,None,0,buffer):raise OSError('Cannot resolve shell folder')
    return Path(buffer.value)

views=[winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY]
keys=[r'Software\ManjuStudio',r'Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio']
def snapshot_registry():
    saved={}
    for view in views:
        for name in keys:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,name,0,winreg.KEY_READ|view) as key:
                    values={}
                    for index in range(winreg.QueryInfoKey(key)[1]):
                        field,value,kind=winreg.EnumValue(key,index);values[field]=(value,kind)
                    saved[(view,name)]=values
            except FileNotFoundError:saved[(view,name)]=None
    return saved
original_registry=snapshot_registry()
desktop=special_folder(0x10);menu=special_folder(0x02)/'漫剧工坊'
menu_existed=menu.exists()
links=[desktop/'漫剧工坊.lnk',menu/'漫剧工坊.lnk',menu/'卸载.lnk']
original_links={p:p.read_bytes() if p.exists() else None for p in links}
def restore_integrations():
    for (view,name),values in original_registry.items():
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,name,0,winreg.KEY_READ|winreg.KEY_SET_VALUE|view) as key:
                current=[winreg.EnumValue(key,index)[0] for index in range(winreg.QueryInfoKey(key)[1])]
                for field in current:
                    if values is None or field not in values:winreg.DeleteValue(key,field)
                for field,(value,kind) in (values or {}).items():winreg.SetValueEx(key,field,0,kind,value)
            if values is None:
                try:winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,name,view,0)
                except OSError:pass
        except FileNotFoundError:
            if values is not None:raise
    for p,data in original_links.items():
        if data is None:p.unlink(missing_ok=True)
        else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    if not menu_existed and menu.exists() and not any(menu.iterdir()):menu.rmdir()

try:
    helper=ROOT/'tmp/distribution-tools/ManjuPrerequisites.exe'
    for flag in ['--check-vc','--check-webview']:
        result=subprocess.run([str(helper),flag,'--silent'],timeout=30)
        check('prerequisite_ready_'+flag.removeprefix('--check-'),result.returncode==0)
    preserved={};previous_target=None
    if args.upgrade_from_version:
        if not __import__('re').fullmatch(r'v\d+\.\d+\.\d+',args.upgrade_from_version):raise ValueError('Invalid previous version')
        old_installer=ROOT/'release'/args.upgrade_from_version/('漫剧工坊-安装程序-'+args.upgrade_from_version[1:]+'.exe')
        old_scan=json.loads((ROOT/'versions'/args.upgrade_from_version/'defender-scan.json').read_text('utf-8-sig'))
        check('previous_installer_matches_verified_scan',old_scan['noMatchingDetection'] and sha(old_installer)==old_scan['installerSha256'])
        previous_target=BASE/'previous version'
        check('previous_version_installed_in_isolation',install(old_installer,previous_target).returncode==0)
        for name in ['data/upgrade-preserve.json','data/license-upgrade-preserve.bin','models/upgrade-preserve.bin',
                     '成片/upgrade-preserve.mp4','本地数据/existing-vcat-test.db']:
            p=previous_target/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('preserve fixture '+name).encode())
            preserved[p]=sha(p)
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\ManjuStudio',0,winreg.KEY_READ|winreg.KEY_WOW64_32KEY) as key:
            registered=Path(winreg.QueryValueEx(key,'InstallDir')[0]).resolve()
        check('only_isolated_old_installation_registered_for_removal',registered==previous_target.resolve() and registered.is_relative_to(BASE.resolve()))
        report.update(upgradeFromVersion=args.upgrade_from_version,oldInstallationDirectory=str(previous_target))
    result=install(installer,TARGET,remove=bool(previous_target),reset=args.reset_user_settings)
    report['installerExitCode']=result.returncode;check('installer_exits_successfully',result.returncode==0)
    if previous_target:
        check('registered_old_version_removed_before_new_install',not (previous_target/'漫剧工坊.exe').exists()
              and not (previous_target/'卸载漫剧工坊.exe').exists())
        check('old_installation_personal_files_preserved',all(p.is_file() and sha(p)==value for p,value in preserved.items()))
    if args.reset_user_settings:
        updated=json.loads((USERDATA/'state.json').read_text('utf-8'))
        check('unchecked_keep_configuration_resets_software_settings',updated['config']=={})
        check('reset_preserves_project_account_history_and_future_fields',updated==dict(original_state,config={}))
        check('reset_has_byte_identical_previous_configuration_backup',any(p.read_bytes()==state_bytes for p in (USERDATA/'settings-backups').glob('*.json')))
    else:
        check('configuration_is_preserved_by_default',(USERDATA/'state.json').read_bytes()==state_bytes)
    check('task_license_model_and_xiaovmiao_user_files_preserved',all(sha(p)==value for p,value in protected_user_files.items()))
    report.update(keepUserConfiguration=not args.reset_user_settings,userConfigurationDirectory=str(USERDATA))
    check('installed_executable_present',(TARGET/'漫剧工坊.exe').is_file())
    check('installed_uninstaller_present',(TARGET/'卸载漫剧工坊.exe').is_file())
    previous=getattr(sys,'frozen',None);sys.frozen=True
    try:licensing.verify_distribution(TARGET)
    finally:
        if previous is None:del sys.frozen
        else:sys.frozen=previous
    check('installed_payload_signature_and_hashes_valid')
    manifest=licensing.signed_payload(json.loads((TARGET/'integrity.json').read_text('utf-8-sig')))
    check('installed_manifest_version_correct',manifest['version']==args.version[1:])
    report['signedFiles']=len(manifest['files'])
    for name in ['connections.js','connections.css','workflow.js','subtitle_settings.css','app.js','index.html',
                 'xiaovmiao.js','promotion_studio.js','publishing.js']:
        check('installed_web_matches_source_'+name,sha(TARGET/'_internal/web'/name)==sha(ROOT/'web'/name))
    for name in ['ai_providers','api_connections','server','xiaovmiao','promotion_studio']:
        check('compiled_core_present_'+name,bool(list((TARGET/'_internal').glob(name+'.cp312-win_amd64.pyd'))))
    bundle=TARGET/'modules/xiaovmiao'
    module=json.loads((bundle/'module.json').read_text('utf-8'))
    expected_module=json.loads((ROOT/'modules/xiaovmiao/module.json').read_text('utf-8'))
    check('xiaovmiao_program_bundled',module['mode']==expected_module['mode'] and bool(module['files']))
    check('all_xiaovmiao_files_match_manifest',all(sha(bundle/'程序'/name)==value for name,value in module['files'].items()))
    check('xiaovmiao_user_profiles_not_packaged',not (bundle/'本地数据').exists()
          and not any(p.name in ('vcat.db','xiaovmiao.json') for p in bundle.rglob('*')))
    report['xiaovmiaoFiles']=len(module['files'])
    report['xiaovmiaoProgramBytes']=sum((bundle/'程序'/name).stat().st_size for name in module['files'])
    report['ok']=True
finally:
    restore_integrations()
    report['originalRegistryRestored']=snapshot_registry()==original_registry
    report['originalShortcutsRestored']=all((p.read_bytes() if p.exists() else None)==data for p,data in original_links.items())
    report['systemPrerequisiteInstallationAttempted']=False
    (BASE/'installation-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    target=ROOT/'versions'/args.version/('installation-reset-report.json' if args.reset_user_settings else 'installation-report.json');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/installer-smoke-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
check('existing_shell_integration_restored',report['originalRegistryRestored'] and report['originalShortcutsRestored'])
print(json.dumps({'ok':report.get('ok',False),'base':str(BASE),'checks':len(report['checks'])},ensure_ascii=True))
