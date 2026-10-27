"""NSIS per-user installation, prerequisite checks, exact-file uninstall."""
from pathlib import Path
import subprocess,json,argparse,re,sys
ROOT=Path(__file__).resolve().parent

def quote(p):return str(p).replace('$','$$').replace('"','$\\"')

def prepare_prerequisites(root=ROOT):
    """Compile the visible, bounded supervisor and verify its pinned payloads."""
    import hashlib,os
    root=Path(root);source=root/'PrerequisiteRunner.cs';tools=root/'tmp/distribution-tools'
    text=source.read_text('utf-8')
    for constant,name in [('VCHash','VC_redist.x64.exe'),('EdgeHash','MicrosoftEdgeWebView2RuntimeInstallerX64.exe')]:
        match=re.search(r'const string '+constant+r'="([a-f0-9]{64})"',text)
        if not match:raise RuntimeError('运行库校验配置缺失：'+constant)
        path=tools/name
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=match.group(1):raise RuntimeError('运行库安装资源哈希不匹配：'+name)
    compiler=Path(os.environ.get('WINDIR','C:/Windows'))/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    if not compiler.is_file():raise RuntimeError('缺少 .NET Framework 4 x64 C# 编译器')
    target=tools/'ManjuPrerequisites.exe'
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
                    '/reference:System.Windows.Forms.dll','/reference:System.Drawing.dll',
                    '/reference:System.Web.Extensions.dll','/out:'+str(target),str(source)],check=True,timeout=60)
    if not target.is_file():raise RuntimeError('环境检查组件编译未生成输出')
    return target

def render_script(version,root=ROOT):
    if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号无效')
    root=Path(root);dist=root/'release'/version/'漫剧工坊';out=dist.parent
    files=[p for p in dist.rglob('*') if p.is_file()]
    delete=[]
    for p in files:delete.append('Delete "$INSTDIR\\'+str(p.relative_to(dist))+'"')
    for p in sorted([p for p in dist.rglob('*') if p.is_dir()],key=lambda x:len(x.parts),reverse=True):delete.append('RMDir "$INSTDIR\\'+str(p.relative_to(dist))+'"')
    script=SCRIPT.replace('0.5.0',version[1:])
    for key,value in {'OUT':out,'ROOT':root,'DIST':dist,'TOOLS':root/'tmp/distribution-tools','DELETE':'\n  '.join(delete)}.items():script=script.replace('@'+key+'@',quote(value) if key!='DELETE' else value)
    return script

SCRIPT=r'''
Unicode true
!include "MUI2.nsh"
!include "x64.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"
Name "漫剧工坊 0.5.0"
OutFile "@OUT@\漫剧工坊-安装程序-0.5.0.exe"
InstallDir "$LOCALAPPDATA\Programs\ManjuStudio"
InstallDirRegKey HKCU "Software\ManjuStudio" "InstallDir"
RequestExecutionLevel user
SetCompressor zlib
Var PrerequisiteSilent
VIProductVersion "0.5.0.0"
VIAddVersionKey /LANG=2052 "ProductName" "漫剧工坊"
VIAddVersionKey /LANG=2052 "FileDescription" "漫剧工坊 Windows 安装程序"
VIAddVersionKey /LANG=2052 "FileVersion" "0.5.0"
VIAddVersionKey /LANG=2052 "LegalCopyright" "ManjuStudio"
!define MUI_ICON "@ROOT@\assets\app.ico"
!define MUI_UNICON "@ROOT@\assets\app.ico"
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\漫剧工坊.exe"
!define MUI_FINISHPAGE_RUN_NOTCHECKED
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"
Function .onInit
  ${IfNot} ${RunningX64}
    MessageBox MB_ICONSTOP "需要 64 位 Windows 10 或 Windows 11。"
    Abort
  ${EndIf}
  ${IfNot} ${AtLeastWin10}
    MessageBox MB_ICONSTOP "需要 Windows 10 或 Windows 11。"
    Abort
  ${EndIf}
  SetShellVarContext current
  StrCpy $PrerequisiteSilent ""
  IfSilent 0 +2
    StrCpy $PrerequisiteSilent "--silent"
FunctionEnd
Section "主程序（必需）" SEC_MAIN
  SectionIn RO
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File "@TOOLS@\ManjuPrerequisites.exe"
  DetailPrint "检查已安装的 Visual C++ x64 与 WebView2，已就绪时跳过安装"
  ExecWait '"$PLUGINSDIR\ManjuPrerequisites.exe" --check-vc --silent' $0
  ${If} $0 == 10
    File "@TOOLS@\VC_redist.x64.exe"
    DetailPrint "准备 Microsoft Visual C++；可查看安装进度，最长等待10分钟"
    ExecWait '"$PLUGINSDIR\ManjuPrerequisites.exe" --install-vc "$PLUGINSDIR\VC_redist.x64.exe" $PrerequisiteSilent' $1
    ${If} $1 == 3010
      SetRebootFlag true
      DetailPrint "Visual C++ 已安装；请重启电脑后运行软件"
    ${ElseIf} $1 != 0
      MessageBox MB_ICONSTOP "Visual C++ 运行库尚未就绪（$1）。诊断记录：$LOCALAPPDATA\ManjuStudio\install-logs。请处理后重新运行安装包。"
      Abort
    ${EndIf}
  ${ElseIf} $0 != 0
    MessageBox MB_ICONSTOP "环境检查失败（$0）。诊断记录：$LOCALAPPDATA\ManjuStudio\install-logs。"
    Abort
  ${EndIf}
  ExecWait '"$PLUGINSDIR\ManjuPrerequisites.exe" --check-webview --silent' $0
  ${If} $0 == 10
    File "@TOOLS@\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    DetailPrint "安装 Microsoft WebView2；最长等待10分钟"
    ExecWait '"$PLUGINSDIR\ManjuPrerequisites.exe" --install-webview "$PLUGINSDIR\MicrosoftEdgeWebView2RuntimeInstallerX64.exe" $PrerequisiteSilent' $1
    ${If} $1 == 3010
      SetRebootFlag true
      DetailPrint "WebView2 已安装；请重启电脑后运行软件"
    ${ElseIf} $1 != 0
      MessageBox MB_ICONSTOP "WebView2 尚未就绪（$1）。诊断记录：$LOCALAPPDATA\ManjuStudio\install-logs。请处理后重新运行安装包。"
      Abort
    ${EndIf}
  ${ElseIf} $0 != 0
    MessageBox MB_ICONSTOP "WebView2 检查失败（$0）。诊断记录：$LOCALAPPDATA\ManjuStudio\install-logs。"
    Abort
  ${EndIf}
  SetRegView 32
  SetOutPath "$INSTDIR"
  File /r "@DIST@\*"
  WriteUninstaller "$INSTDIR\卸载漫剧工坊.exe"
  WriteRegStr HKCU "Software\ManjuStudio" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "DisplayName" "漫剧工坊"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "DisplayVersion" "0.5.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "DisplayIcon" "$INSTDIR\漫剧工坊.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "UninstallString" '$\"$INSTDIR\卸载漫剧工坊.exe$\"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "NoRepair" 1
  CreateDirectory "$SMPROGRAMS\漫剧工坊"
  CreateShortcut "$SMPROGRAMS\漫剧工坊\漫剧工坊.lnk" "$INSTDIR\漫剧工坊.exe"
  CreateShortcut "$SMPROGRAMS\漫剧工坊\卸载.lnk" "$INSTDIR\卸载漫剧工坊.exe"
  CreateShortcut "$DESKTOP\漫剧工坊.lnk" "$INSTDIR\漫剧工坊.exe"
SectionEnd
Section /o "可选：导入同目录的离线 AI 引擎包（约 8 GB）" SEC_AI
  IfFileExists "$EXEDIR\漫剧工坊-AI离线引擎-v1.zip" found missing
  found:
    DetailPrint "校验签名并导入离线 AI 引擎，请稍候…"
    ExecWait '"$INSTDIR\漫剧工坊.exe" --install-engine "$EXEDIR\漫剧工坊-AI离线引擎-v1.zip"' $0
    ${If} $0 != 0
      MessageBox MB_ICONEXCLAMATION "离线 AI 引擎导入未完成。可在软件的“授权与组件”中重试。"
    ${EndIf}
    Goto end
  missing:
    MessageBox MB_ICONINFORMATION "未找到同目录离线 AI 引擎包。主程序仍可使用，之后可从“授权与组件”导入。"
  end:
SectionEnd
Section "Uninstall"
  SetShellVarContext current
  @DELETE@
  Delete "$INSTDIR\卸载漫剧工坊.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\漫剧工坊\漫剧工坊.lnk"
  Delete "$SMPROGRAMS\漫剧工坊\卸载.lnk"
  RMDir "$SMPROGRAMS\漫剧工坊"
  Delete "$DESKTOP\漫剧工坊.lnk"
  SetRegView 32
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio"
  DeleteRegKey HKCU "Software\ManjuStudio"
  ; Personal projects, licenses, models and exports are deliberately preserved.
SectionEnd
'''
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',default='v0.5.0');parser.add_argument('--prepare-script',action='store_true',help='Prepare NSIS input only; never emit an unsigned client installer')
    options=parser.parse_args();version=options.version
    if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号无效')
    dist=ROOT/'release'/version/'漫剧工坊'
    if not dist.is_dir():raise RuntimeError('找不到发行目录，请先完成编译与签名')
    prepare_prerequisites()
    path=ROOT/('tmp/manju-setup-'+version+'.nsi');path.write_text(render_script(version),'utf-8-sig')
    if options.prepare_script:
        print('INSTALLER_SCRIPT_PREPARED_ONLY',path);return
    # Never wrap a preparation bundle that will fail the application integrity gate.
    import licensing
    previous_frozen=getattr(sys,'frozen',None);sys.frozen=True
    try:licensing.verify_distribution(dist)
    finally:
        if previous_frozen is None:del sys.frozen
        else:sys.frozen=previous_frozen
    subprocess.run([str(ROOT/'tmp/distribution-tools/nsis-3.12/makensis.exe'),'/V3',str(path)],check=True)

if __name__=='__main__':main()
