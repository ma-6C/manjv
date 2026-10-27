"""Native picker contracts and real PowerShell discovery with an empty PATH."""
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import json,os,subprocess,sys,tempfile
import file_picker as f
ROOT=Path(__file__).resolve().parent;BASE=Path(tempfile.mkdtemp(prefix='file-picker-',dir=ROOT/'tmp'))
checks=[]
def check(name,value):assert value,name;checks.append(name);print('PASS '+name,flush=True)
with patch.object(f.subprocess,'run',side_effect=AssertionError('native route must not spawn PowerShell')):
    seen=[]
    def native(spec):seen.append(spec);return ['D:/测试环境/引擎/python.exe']
    check('native_python_picker_returns_unicode_path',f.choose({'mode':'python'},native)['path']=='D:/测试环境/引擎/python.exe')
    check('python_picker_uses_executable_file_filter',seen[-1]['filter'][1]=='*.exe' and not seen[-1]['folder'])
    check('native_folder_selection',f.choose({'mode':'folder'},lambda spec:['D:/素材'])=={'path':'D:/素材'})
    check('native_cancel_is_empty_not_failure',f.choose({'mode':'python'},lambda spec:None)=={'path':''})
    check('video_single_selection_retains_paths_contract',f.choose({'mode':'videos','multiple':False},lambda spec:['D:/一.mp4'])=={'paths':['D:/一.mp4']})
    check('attachments_allow_multiple',f.specification({'mode':'images'})['multiple'])
    try:f.choose({'mode':'invalid'},native)
    except ValueError:check('invalid_modes_rejected_before_dialog',True)
f.LOCK.acquire()
try:
    try:f.choose({'mode':'folder'},lambda spec:None)
    except ValueError as error:check('duplicate_dialog_reports_existing_window','已有文件选择窗口' in str(error))
finally:f.LOCK.release()
with patch.dict(os.environ,{'PATH':''}):
    try:subprocess.run(['powershell','-NoProfile','-Command','exit 0'],capture_output=True,timeout=10)
    except FileNotFoundError as error:check('old_command_reproduces_customer_winerror_2',getattr(error,'winerror',None)==2)
    else:raise AssertionError('Expected missing bare PowerShell command with empty PATH')
    executable=f.powershell_executable()
    check('empty_path_resolves_absolute_system_powershell',Path(executable).is_absolute() and Path(executable).is_file())
    actual=subprocess.run([executable,'-NoProfile','-Command',"[Console]::Write('FILE_PICKER_SYSTEM_OK')"],capture_output=True,timeout=20,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    check('system_powershell_runs_with_path_removed',actual.returncode==0 and b'FILE_PICKER_SYSTEM_OK' in actual.stdout)
for mode in f.FILTERS:
    response=SimpleNamespace(returncode=0,stdout=json.dumps(['D:/样例']).encode(),stderr=b'')
    with patch.object(f.subprocess,'run',return_value=response) as called:
        result=f.choose({'mode':mode})
        check('fallback_contract_'+mode,bool(result.get('path') or result.get('paths')) and Path(called.call_args.args[0][0]).is_absolute())
with patch.object(f.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout=b'',stderr=b'dialog backend failed')):
    try:f.choose({'mode':'python'})
    except RuntimeError as error:check('dialog_backend_error_is_not_treated_as_cancel','dialog backend failed' in str(error))
with patch.object(f.subprocess,'run',side_effect=FileNotFoundError()):
    try:f.choose({'mode':'python'})
    except RuntimeError as error:check('startup_error_names_missing_executable','powershell.exe' in str(error) and '粘贴路径' in str(error))
report={'ok':True,'passed':len(checks),'checks':checks}
(ROOT/'tmp/file-picker-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
