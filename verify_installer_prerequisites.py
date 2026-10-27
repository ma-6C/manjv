"""Exercise prerequisite decisions without installing or changing system software."""
from pathlib import Path
import json,os,subprocess,tempfile
import build_installer as installer

ROOT=Path(__file__).resolve().parent
BASE=Path(tempfile.mkdtemp(prefix='installer-prerequisites-',dir=ROOT/'tmp'))
checks=[]
def check(name,value=True):
    assert value,name
    checks.append(name)

# Render against disposable files. No customer installation or registry is used.
dist=BASE/'release/v9.9.9/漫剧工坊'
(dist/'_internal').mkdir(parents=True)
(dist/'漫剧工坊.exe').write_bytes(b'not an executable; renderer fixture')
(dist/'_internal/payload.txt').write_text('fixture','utf-8')
script=installer.render_script('v9.9.9',BASE)
check('version_applied_to_installer', '漫剧工坊-安装程序-9.9.9.exe' in script and '0.5.0' not in script)
check('per_user_installer_preserved','RequestExecutionLevel user' in script and 'HKCU "Software\\ManjuStudio"' in script)
check('vc_checked_before_install',script.index('--check-vc --silent')<script.index('--install-vc'))
check('webview_checked_before_install',script.index('--check-webview --silent')<script.index('--install-webview'))
check('missing_component_only_triggers_install',script.count('${If} $0 == 10')==2)
check('old_unbounded_hidden_shell_removed','ExecShellWait' not in script and '/install /quiet' not in script)
check('bounded_supervisor_payload_used',script.count('ManjuPrerequisites.exe')==5)
check('installer_silent_flag_forwarded',script.count('$PrerequisiteSilent')==4 and 'IfSilent 0 +2' in script)
check('reboot_codes_recorded',script.count('SetRebootFlag true')==2)
check('prerequisite_failure_aborts_before_payload',script.index('Abort',script.index('--install-webview'))<script.index('File /r'))
check('diagnostic_location_reported','ManjuStudio\\install-logs' in script)
check('same_directory_offline_v1_import_retained','--install-engine "$EXEDIR\\漫剧工坊-AI离线引擎-v1.zip"' in script)
check('uninstall_exact_file_list', 'Delete "$INSTDIR\\_internal\\payload.txt"' in script and 'RMDir /r' not in script)
check('personal_data_not_deleted','Delete "$INSTDIR\\data' not in script and 'Delete "$LOCALAPPDATA' not in script)
try:installer.render_script('../v1.0.0',BASE)
except ValueError:check('unsafe_version_rejected')
else:raise AssertionError('unsafe version accepted')

# Actual C# compilation validates the shipped supervisor source and resource pins.
# The entry point below calls only pure decision methods, never Main or Worker.
helper=installer.prepare_prerequisites()
check('actual_supervisor_compiles',helper.is_file())
harness=BASE/'PrerequisiteHarness.cs'
harness.write_text(r'''
using System;
internal static class PrerequisiteHarness {
    static int n;
    static void Check(bool v,string name){if(!v)throw new Exception(name);n++;}
    static int Main(){
        Check(PrerequisiteRunner.AtLeast("v14.50.35717.0","14.50.35717.0"),"equal version");
        Check(!PrerequisiteRunner.AtLeast("14.40.0.0","14.50.35717.0"),"older version");
        Check(PrerequisiteRunner.EvaluateVC(false,"",new[]{"14.50.35717.0","14.50.35717.0","14.50.35717.0"}),"dll ready without stale registry");
        Check(!PrerequisiteRunner.EvaluateVC(true,"14.50.35717.0",new[]{"14.50.35717.0","","14.50.35717.0"}),"damaged dll not ready");
        Check(PrerequisiteRunner.Classify(0,true)==0,"success ready");
        Check(PrerequisiteRunner.Classify(0,false)==5101,"success but absent");
        Check(PrerequisiteRunner.Classify(1638,true)==0,"already installed ready");
        Check(PrerequisiteRunner.Classify(1638,false)==5101,"already installed damaged");
        Check(PrerequisiteRunner.Classify(3010,false)==3010,"reboot required");
        Check(PrerequisiteRunner.Classify(1641,false)==3010,"restart initiated");
        Check(PrerequisiteRunner.Classify(1223,false)==1602,"uac declined");
        Check(PrerequisiteRunner.Classify(unchecked((int)0x80070642),false)==1602,"hresult cancelled");
        Check(PrerequisiteRunner.Classify(1618,false)==1618,"busy installer");
        Check(PrerequisiteRunner.Classify(1603,false)==1603,"failure retained");
        Check(PrerequisiteRunner.Supervise(()=>true,()=>0,()=>false,TimeSpan.Zero,()=>{})==0,"completed wait");
        Check(PrerequisiteRunner.Supervise(()=>false,()=>0,()=>true,TimeSpan.FromSeconds(1),()=>{})==1602,"cancel wait");
        Check(PrerequisiteRunner.Supervise(()=>false,()=>0,()=>false,TimeSpan.Zero,()=>{})==1460,"bounded timeout");
        Check(PrerequisiteRunner.Explain(1460).Contains("10分钟"),"timeout explained");
        Console.WriteLine(n);return 0;
    }
}
''','utf-8')
compiler=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
target=BASE/'PrerequisiteHarness.exe'
subprocess.run([str(compiler),'/nologo','/target:exe','/platform:x64','/main:PrerequisiteHarness',
                '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll','/reference:System.Web.Extensions.dll',
                '/out:'+str(target),str(ROOT/'PrerequisiteRunner.cs'),str(harness)],check=True,timeout=60)
native=int(subprocess.check_output([str(target)],timeout=10).decode().strip())
check('pure_supervisor_decision_checks',native==18)
check('supervisor_wait_is_bounded','TimeSpan.FromMinutes(10)' in (ROOT/'PrerequisiteRunner.cs').read_text('utf-8'))
report={'passed':len(checks)+native,'pythonChecks':checks,'csharpDecisionChecks':native,'base':str(BASE),
        'actualMicrosoftInstallAttempted':False,'systemRegistryModified':False,'customerDataUsed':False,'productInstallerBuilt':False}
(BASE/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
(ROOT/'tmp/installer-prerequisites-latest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
print(json.dumps({'passed':report['passed'],'base':str(BASE),'actualMicrosoftInstallAttempted':False},ensure_ascii=False))
