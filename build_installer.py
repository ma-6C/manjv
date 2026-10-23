"""NSIS per-user installation, prerequisite checks, exact-file uninstall."""
from pathlib import Path
import subprocess,json,argparse,re,sys
parser=argparse.ArgumentParser();parser.add_argument('--version',default='v0.5.0');parser.add_argument('--prepare-script',action='store_true',help='Prepare NSIS input only; never emit an unsigned client installer')
options=parser.parse_args();version=options.version
if not re.fullmatch(r'v\d+\.\d+\.\d+',version):raise ValueError('版本号无效')
ROOT=Path(__file__).resolve().parent;DIST=ROOT/'release'/version/'漫剧工坊';OUT=DIST.parent
def quote(p):return str(p).replace('$','$$').replace('"','$\\"')
files=[p for p in DIST.rglob('*') if p.is_file()]
delete=[]
for p in files:delete.append('Delete "$INSTDIR\\'+str(p.relative_to(DIST))+'"')
for p in sorted([p for p in DIST.rglob('*') if p.is_dir()],key=lambda x:len(x.parts),reverse=True):delete.append('RMDir "$INSTDIR\\'+str(p.relative_to(DIST))+'"')
script=r'''
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
FunctionEnd
Section "主程序（必需）" SEC_MAIN
  SectionIn RO
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  SetRegView 64
  ReadRegDWORD $0 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Installed"
  ReadRegDWORD $2 HKLM "SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64" "Minor"
  ${If} $0 != 1
  ${OrIf} $2 < 40
    File "@TOOLS@\VC_redist.x64.exe"
    DetailPrint "安装 Microsoft Visual C++ 运行库（可能请求管理员权限）"
    ExecShellWait "open" "$PLUGINSDIR\VC_redist.x64.exe" "/install /quiet /norestart" SW_HIDE $1
    ${If} $1 != 0
    ${AndIf} $1 != 1638
    ${AndIf} $1 != 3010
      MessageBox MB_ICONSTOP "Visual C++ 运行库安装失败（$1）。请安装官方 x64 运行库后重试。"
      Abort
    ${EndIf}
  ${EndIf}
  SetRegView 32
  ReadRegStr $0 HKLM "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${If} $0 == ""
    ReadRegStr $0 HKCU "Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  ${EndIf}
  ${If} $0 == ""
  ${OrIf} $0 == "0.0.0.0"
    File "@TOOLS@\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"
    DetailPrint "安装 Microsoft WebView2 桌面运行库"
    ExecWait '"$PLUGINSDIR\MicrosoftEdgeWebView2RuntimeInstallerX64.exe" /silent /install' $1
    ${If} $1 != 0
    ${AndIf} $1 != 3010
      MessageBox MB_ICONSTOP "WebView2 安装失败（$1）。请安装微软官方运行库后重试。"
      Abort
    ${EndIf}
  ${EndIf}
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
script=script.replace('0.5.0',version[1:])
for key,value in {'OUT':OUT,'ROOT':ROOT,'DIST':DIST,'TOOLS':ROOT/'tmp/distribution-tools','DELETE':'\n  '.join(delete)}.items():script=script.replace('@'+key+'@',quote(value) if key!='DELETE' else value)
path=ROOT/('tmp/manju-setup-'+version+'.nsi');path.write_text(script,'utf-8-sig')
if options.prepare_script:
    print('INSTALLER_SCRIPT_PREPARED_ONLY',path);sys.exit(0)
# The installer must never wrap a preparation bundle that will fail the normal
# application's integrity gate. Keep verification enabled before NSIS runs.
import licensing
previous_frozen=getattr(sys,'frozen',None);sys.frozen=True
try:licensing.verify_distribution(DIST)
finally:
    if previous_frozen is None:del sys.frozen
    else:sys.frozen=previous_frozen
subprocess.run([str(ROOT/'tmp/distribution-tools/nsis-3.12/makensis.exe'),'/V3',str(path)],check=True)
