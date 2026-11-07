"""Run the production old-version detection/removal against tiny NSIS fixtures.

Only disposable workspace installations may be removed. Original registration
is restored even when a scenario fails. No customer application is uninstalled.
"""
from pathlib import Path
import ctypes,hashlib,json,os,re,subprocess,sys,tempfile,winreg
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import build_installer as build
BASE=Path(tempfile.mkdtemp(prefix='installer-upgrade-',dir=ROOT/'tmp'))
COMPILER=ROOT/'tmp/distribution-tools/nsis-3.12/makensis.exe'
VIEWS=[winreg.KEY_WOW64_32KEY,winreg.KEY_WOW64_64KEY]
KEYS=[r'Software\ManjuStudio',r'Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio']
checks=[];report={'base':str(BASE),'realNsisUninstaller':True,'customerInstallationRemoved':False}
USERDATA=BASE/'user settings';USERDATA.mkdir()
user_state={'config':{'parallel':7,'output':'fixture-output'},'projects':[{'id':'keep-project'}],
            'accounts':[{'name':'keep-account'}],'logs':[{'message':'keep-log'}]}
user_original=json.dumps(user_state,ensure_ascii=False,indent=2).encode();(USERDATA/'state.json').write_bytes(user_original)
def check(name,value=True):
    assert value,name
    checks.append(name);print('PASS '+name,flush=True)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def snapshot():
    saved={}
    for view in VIEWS:
        for name in KEYS:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,name,0,winreg.KEY_READ|view) as k:
                    if winreg.QueryInfoKey(k)[0]:raise RuntimeError('Unexpected registry subkeys; leaving original installation untouched')
                    saved[(view,name)]=[winreg.EnumValue(k,n) for n in range(winreg.QueryInfoKey(k)[1])]
            except FileNotFoundError:saved[(view,name)]=None
    return saved
original=snapshot()
def clear_registration():
    for view in VIEWS:
        for name in KEYS:
            try:winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER,name,view,0)
            except FileNotFoundError:pass
def restore():
    clear_registration()
    for (view,name),values in original.items():
        if values is not None:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,name,0,winreg.KEY_WRITE|view) as k:
                for field,value,kind in values:winreg.SetValueEx(k,field,0,kind,value)
def register(folder):
    assert folder.resolve().is_relative_to(BASE.resolve()),'Only fixture installation may be registered'
    for name,values in [(KEYS[0],{'InstallDir':str(folder)}),(KEYS[1],{
            'DisplayVersion':'0.10.5','UninstallString':'"'+str(folder/'卸载漫剧工坊.exe')+'"'})]:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,name,0,winreg.KEY_WRITE|winreg.KEY_WOW64_32KEY) as k:
            for field,value in values.items():winreg.SetValueEx(k,field,0,winreg.REG_SZ,value)
def compile_script(name,text):
    p=BASE/(name+'.nsi');p.write_text(text,'utf-8-sig')
    result=subprocess.run([str(COMPILER),'/V2',str(p)],capture_output=True,timeout=60)
    (BASE/(name+'-compiler.log')).write_bytes(result.stdout+result.stderr)
    assert result.returncode==0,'Fixture compile failed: '+name
def run(exe,target,remove=None,keep=None):
    assert target.resolve().is_relative_to(BASE.resolve()),'Install target escapes test workspace'
    # NSIS requires /D= to be last and unquoted even for a spaced path. Python's
    # automatic list quoting would quote that whole argument and lose /D=.
    command=subprocess.list2cmdline([str(exe),'/S',*(['/REMOVEOLD='+str(remove)] if remove is not None else []),
                                    *(['/KEEPCONFIG='+str(keep)] if keep is not None else [])])+' /D='+str(target)
    code=subprocess.run(command,timeout=45,env={**os.environ,'MANJU_DATA':str(USERDATA)},creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).returncode
    print('FIXTURE_RESULT',target.name,code,flush=True)
    return code

try:
    # Exact production pages, initialization and upgrade helper, with the large
    # payload section replaced by a harmless marker for fast scenario coverage.
    prefix=build.render_script('v9.9.9').split('Section "漫剧工坊（必需）" SEC_MAIN',1)[0]
    prefix=re.sub(r'^OutFile .*$',lambda _: 'OutFile "'+str(BASE/'new.exe')+'"',prefix,flags=re.M)
    prefix='\n'.join(line for line in prefix.splitlines() if not line.startswith('!define MUI_FINISHPAGE_RUN'))+'\n'
    compile_script('new',prefix+r'''
Section "漫剧工坊（必需）" SEC_MAIN
  SectionIn RO
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "@SETTINGS_HELPER@"
  Call ManjuCheckSettingsReset
  Call ManjuRemoveOld
  Call ManjuApplySettingsReset
  SetOutPath "$INSTDIR"
  FileOpen $0 "$INSTDIR\new-installed.txt" w
  FileWrite $0 "new payload written"
  FileClose $0
SectionEnd
Section "Uninstall"
SectionEnd
'''.replace('@SETTINGS_HELPER@',str(ROOT/'tmp/distribution-tools/ManjuSettings.exe')))
    old_source=BASE/'old-main.cs';old_source.write_text('class Fixture { static int Main() { return 17; } }','utf-8')
    csc=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    fail_exe=BASE/'fixture.exe'
    subprocess.run([str(csc),'/nologo','/target:winexe','/out:'+str(fail_exe),str(old_source)],check=True,timeout=30)
    compile_script('old',r'''
Unicode true
RequestExecutionLevel user
Name "Disposable old installation"
OutFile "@BASE@\old.exe"
Section
  SetOutPath "$INSTDIR"
  File /oname=漫剧工坊.exe "@BASE@\fixture.exe"
  FileOpen $0 "$INSTDIR\integrity.json" w
  FileWrite $0 "fixture manifest marker"
  FileClose $0
  FileOpen $0 "$INSTDIR\old-only.txt" w
  FileWrite $0 "owned old program file"
  FileClose $0
  WriteUninstaller "$INSTDIR\卸载漫剧工坊.exe"
SectionEnd
Section "Uninstall"
  FileOpen $0 "$INSTDIR\uninstaller-called.txt" w
  FileWrite $0 "real NSIS uninstaller ran"
  FileClose $0
  Delete "$INSTDIR\漫剧工坊.exe"
  Delete "$INSTDIR\integrity.json"
  Delete "$INSTDIR\old-only.txt"
  Delete "$INSTDIR\卸载漫剧工坊.exe"
  RMDir "$INSTDIR"
  SetRegView 32
  DeleteRegKey HKCU "Software\ManjuStudio"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio"
SectionEnd
'''.replace('@BASE@',str(BASE)))
    new=BASE/'new.exe';old=BASE/'old.exe'
    clear_registration()
    target=BASE/'fresh install'
    check('fresh_install_skips_old_removal',run(new,target)==0 and (target/'new-installed.txt').is_file())
    check('explicit_removal_without_old_installation_aborts',run(new,BASE/'no-old',1)==2 and not (BASE/'no-old').exists())
    olddir=BASE/'旧版本 with spaces';check('old_fixture_installed',run(old,olddir)==0)
    keep={}
    for name in ['data/state.json','data/license.bin','models/model.bin','成片/keep.mp4','本地数据/vcat.db','personal.txt']:
        p=olddir/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('preserve '+name).encode());keep[name]=digest(p)
    register(olddir)
    check('default_upgrade_does_not_run_uninstaller',run(new,BASE/'default update')==0
          and (olddir/'漫剧工坊.exe').exists() and not (olddir/'uninstaller-called.txt').exists())
    register(olddir)
    check('explicit_keep_does_not_run_uninstaller',run(new,BASE/'keep update',0)==0
          and (olddir/'漫剧工坊.exe').exists() and not (olddir/'uninstaller-called.txt').exists())
    register(olddir)
    check('invalid_remove_option_aborts',run(new,BASE/'invalid option','wrong')==2 and not (BASE/'invalid option').exists())
    check('invalid_keep_config_option_aborts',run(new,BASE/'invalid keep',1,'wrong')==2 and not (BASE/'invalid keep').exists())
    check('reset_without_uninstall_is_rejected',run(new,BASE/'reset without uninstall',0,0)==2 and not (BASE/'reset without uninstall').exists())
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.restype=ctypes.c_void_p
    kernel.CreateFileW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.CreateFileW(str(olddir/'漫剧工坊.exe'),0x80000000,1,None,3,0,None)
    assert handle!=ctypes.c_void_p(-1).value
    try:check('locked_old_program_aborts_before_uninstall',run(new,BASE/'locked target',1,0)==2 and not (olddir/'uninstaller-called.txt').exists())
    finally:kernel.CloseHandle(handle)
    check('locked_program_does_not_write_new_payload',not (BASE/'locked target').exists())
    check('locked_program_keeps_settings_unchanged',(USERDATA/'state.json').read_bytes()==user_original)
    old_uninstaller=olddir/'卸载漫剧工坊.exe';saved=old_uninstaller.read_bytes()
    old_uninstaller.write_bytes(fail_exe.read_bytes())
    try:check('uninstaller_failure_stops_new_installation',run(new,BASE/'failed target',1,0)==2 and not (BASE/'failed target').exists())
    finally:old_uninstaller.write_bytes(saved)
    check('uninstaller_failure_keeps_settings_unchanged',(USERDATA/'state.json').read_bytes()==user_original)
    (USERDATA/'state.json').write_text('{invalid-json','utf-8')
    check('invalid_settings_block_before_old_uninstall',run(new,BASE/'invalid settings',1,0)==2 and not (olddir/'uninstaller-called.txt').exists())
    (USERDATA/'state.json').write_bytes(user_original)
    old_uninstaller.rename(olddir/'uninstaller-backup.exe')
    try:check('missing_uninstaller_aborts_explicit_removal',run(new,BASE/'missing target',1)==2 and not (BASE/'missing target').exists())
    finally:(olddir/'uninstaller-backup.exe').rename(old_uninstaller)
    register(olddir);target=BASE/'new version with spaces'
    check('selected_old_version_is_actually_uninstalled',run(new,target,1)==0 and (olddir/'uninstaller-called.txt').is_file()
          and not (olddir/'漫剧工坊.exe').exists() and not (olddir/'old-only.txt').exists())
    check('new_installation_written_after_old_uninstall',(target/'new-installed.txt').is_file())
    check('all_personal_data_survives_old_uninstall',all(digest(olddir/name)==sha for name,sha in keep.items()))
    check('settings_are_preserved_by_default_during_uninstall',(USERDATA/'state.json').read_bytes()==user_original)
    same=BASE/'same path';check('second_old_fixture_installed',run(old,same)==0)
    (same/'personal.txt').write_text('preserve-me','utf-8');register(same)
    check('same_directory_upgrade_after_uninstall_succeeds',run(new,same,1,0)==0 and (same/'new-installed.txt').is_file())
    check('same_directory_upgrade_preserves_personal_files',(same/'personal.txt').read_text('utf-8')=='preserve-me')
    updated=json.loads((USERDATA/'state.json').read_text('utf-8'))
    check('explicit_unchecked_keep_config_resets_only_settings',updated==dict(user_state,config={}))
    check('explicit_reset_keeps_original_configuration_backup',any(p.read_bytes()==user_original for p in (USERDATA/'settings-backups').glob('*.json')))
    report['ok']=True
finally:
    restore();report['originalRegistryRestored']=snapshot()==original
    if report['originalRegistryRestored']:checks.append('original_installation_registration_restored')
    report['checks']=checks
    (BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    (ROOT/'tmp/installer-upgrade-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
assert report['originalRegistryRestored'],'original_installation_registration_restored'
print('INSTALLER_UPGRADE_CHECKS_OK',len(checks),str(BASE))
