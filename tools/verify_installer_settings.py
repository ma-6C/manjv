"""Exercise the actual native settings helper using disposable user data only."""
from pathlib import Path
import ctypes,hashlib,json,os,subprocess,tempfile
ROOT=Path(__file__).resolve().parents[1]
BASE=Path(tempfile.mkdtemp(prefix='installer-settings-',dir=ROOT/'tmp'))
HELPER=ROOT/'tmp/distribution-tools/ManjuSettings.exe';DATA=BASE/'user data'
DATA.mkdir();checks=[]
def check(name,value=True):
    assert value,name
    checks.append(name);print('PASS '+name,flush=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(mode,home=DATA):
    output=BASE/('report-'+str(len(checks))+'.json')
    result=subprocess.run([str(HELPER),mode,'--report',str(output)],env={**os.environ,'MANJU_DATA':str(home)},
                          timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    return result.returncode,json.loads(output.read_text('utf-8'))
state={'config':{'parallel':7,'source':'fixture source','output':'fixture output','aiConnections':[{'name':'fixture-only'}]},
       'trackSheetOptions':{'layout':'fixture'},'aiConnectionTests':{'fixture':{'ok':True}},
       'projects':[{'id':'keep','name':'中文项目','duration':123.456789123,'size':1234567890123456789,
                    'artifacts':[{'path':'D:/fixture/keep.mp4'}]}],
       'accounts':[{'name':'fixture account'}],'logs':[{'message':'fixture history'}],
       'promotionTasks':[{'id':'saved'}],'futureUnknownField':{'keep':[1,None,True,'原样保留']}}
original=json.dumps(state,ensure_ascii=False,indent=2).encode('utf-8');path=DATA/'state.json';path.write_bytes(original)
protected={}
for name in ['jobs.json','license.bin','license-clock.bin','xiaovmiao.json','models/keep.bin','components/xiaovmiao/本地数据/vcat.db','engines/active.json']:
    p=DATA/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(('protected fixture '+name).encode());protected[p]=sha(p)
code,report=run('--check');check('preflight_accepts_valid_state',code==0 and report['ready'])
check('preflight_does_not_change_state_bytes',path.read_bytes()==original)
check('preflight_does_not_create_backup',not list((DATA/'settings-backups').glob('*.json')))
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel.CreateMutexW.restype=ctypes.c_void_p
kernel.CloseHandle.argtypes=[ctypes.c_void_p]
name='Local\\ManjuStudio.'+hashlib.sha256(str(DATA.resolve()).encode()).hexdigest()[:24]
handle=kernel.CreateMutexW(None,False,name);assert handle
try:
    check('preflight_rejects_running_desktop_mutex',run('--check')[0]==20)
    check('reset_rejects_running_desktop_mutex',run('--reset')[0]==20)
    check('live_application_settings_remain_unchanged',path.read_bytes()==original)
finally:kernel.CloseHandle(handle)
code,report=run('--reset');check('explicit_reset_succeeds',code==0 and report['changed'])
updated=json.loads(path.read_text('utf-8'))
check('only_software_settings_are_reset',updated['config']=={} and 'trackSheetOptions' not in updated and 'aiConnectionTests' not in updated)
check('projects_accounts_logs_and_future_fields_preserved',
      {k:v for k,v in updated.items() if k!='config'}=={k:v for k,v in state.items() if k not in ('config','trackSheetOptions','aiConnectionTests')})
check('backup_is_byte_identical_to_previous_state',Path(report['backup']).read_bytes()==original)
check('task_license_model_and_xiaovmiao_files_unchanged',all(sha(p)==value for p,value in protected.items()))
check('temporary_replacement_files_removed',not list(DATA.glob('state-reset-*.tmp')))
missing=BASE/'not-created'
code,report=run('--reset',missing);check('missing_settings_are_a_noop',code==0 and not report['changed'] and not missing.exists())
for broken,label in [(b'{"config":','invalid_json'),(b'{"config":{},"name":"\xff"}','invalid_utf8'),(b'[]','non_object_root')]:
    path.write_bytes(broken);before=len(list((DATA/'settings-backups').glob('*.json')))
    check(label+'_preflight_fails_closed',run('--check')[0]==20 and path.read_bytes()==broken)
    check(label+'_reset_preserves_original',run('--reset')[0]==20 and path.read_bytes()==broken)
    check(label+'_does_not_create_backup',len(list((DATA/'settings-backups').glob('*.json')))==before)
blocked=BASE/'backup blocked';blocked.mkdir();(blocked/'state.json').write_bytes(original);(blocked/'settings-backups').write_bytes(b'blocked')
check('unwritable_backup_location_blocks_preflight',run('--check',blocked)[0]==20 and (blocked/'state.json').read_bytes()==original)
check('unwritable_backup_location_blocks_reset',run('--reset',blocked)[0]==20 and (blocked/'state.json').read_bytes()==original)
check('drive_root_is_rejected',run('--reset',Path(BASE.anchor))[0]==20)
report={'ok':True,'checks':checks,'base':str(BASE),'nativeHelperExecuted':True,'customerDataUsed':False}
(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
(ROOT/'tmp/installer-settings-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print('INSTALLER_SETTINGS_CHECKS_OK',len(checks))
