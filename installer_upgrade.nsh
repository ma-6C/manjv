; Optional removal of the one current-user installation registered by our NSIS
; installer. Never execute a registry-supplied command line or recursively wipe.
!include "FileFunc.nsh"
!include "nsDialogs.nsh"
Var OldInstallDir
Var OldVersion
Var OldFound
Var OldRemove
Var OldCheckbox
Var KeepConfig
Var KeepConfigCheckbox

!macro MANJU_UPGRADE_FUNCTIONS
Function ManjuDetectOld
  StrCpy $OldFound 0
  StrCpy $OldRemove 0
  StrCpy $KeepConfig 1
  StrCpy $OldInstallDir ""
  SetRegView 32
  ReadRegStr $OldInstallDir HKCU "Software\ManjuStudio" "InstallDir"
  ${If} $OldInstallDir == ""
    Return
  ${EndIf}
  GetFullPathName $OldInstallDir "$OldInstallDir"
  ; Only a local drive directory, never a filesystem root or reparse point.
  StrCpy $0 $OldInstallDir 1 1
  ${If} $0 != ":"
    Return
  ${EndIf}
  ${GetRoot} "$OldInstallDir" $0
  ${If} $OldInstallDir == "$0\"
    Return
  ${EndIf}
  System::Call 'kernel32::GetFileAttributesW(w "$OldInstallDir")i.r0'
  IntOp $0 $0 & 0x400
  ${If} $0 != 0
    Return
  ${EndIf}
  IfFileExists "$OldInstallDir\漫剧工坊.exe" 0 old_not_found
  IfFileExists "$OldInstallDir\integrity.json" 0 old_not_found
  IfFileExists "$OldInstallDir\卸载漫剧工坊.exe" 0 old_not_found
  ReadRegStr $0 HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "UninstallString"
  ${If} $0 != '$\"$OldInstallDir\卸载漫剧工坊.exe$\"'
    Return
  ${EndIf}
  ReadRegStr $OldVersion HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\ManjuStudio" "DisplayVersion"
  ${If} $OldVersion == ""
    StrCpy $OldVersion "（版本号未知）"
  ${EndIf}
  StrCpy $OldFound 1
  old_not_found:
FunctionEnd

Function ManjuUpgradeOptions
  ; Silent upgrades preserve the old installation unless explicitly requested.
  ${GetParameters} $0
  ClearErrors
  ${GetOptions} $0 "/REMOVEOLD=" $1
  ${IfNot} ${Errors}
    ${If} $1 != "0"
    ${AndIf} $1 != "1"
      MessageBox MB_ICONSTOP|MB_OK "卸载旧版本选项无效，请重新运行安装程序。" /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
    StrCpy $OldRemove $1
    ${If} $OldRemove == 1
    ${AndIf} $OldFound != 1
      MessageBox MB_ICONSTOP|MB_OK "未找到可卸载的已注册旧版本，尚未安装新版本。" /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
  ${EndIf}
  ClearErrors
  ${GetOptions} $0 "/KEEPCONFIG=" $1
  ${IfNot} ${Errors}
    ${If} $1 != "0"
    ${AndIf} $1 != "1"
      MessageBox MB_ICONSTOP|MB_OK "保留用户配置选项无效，请重新运行安装程序。" /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
    StrCpy $KeepConfig $1
    ${If} $KeepConfig == 0
    ${AndIf} $OldRemove != 1
      MessageBox MB_ICONSTOP|MB_OK "仅在选择卸载旧版本时才能重置用户配置。" /SD IDOK
      SetErrorLevel 2
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

Function ManjuUpgradePage
  ${If} $OldFound != 1
    Abort
  ${EndIf}
  !insertmacro MUI_HEADER_TEXT "发现已安装版本" "选择是否在安装新版本前卸载旧程序。"
  nsDialogs::Create 1018
  Pop $0
  ${If} $0 == error
    Abort
  ${EndIf}
  ${NSD_CreateLabel} 0 0 100% 14u "已安装：漫剧工坊 $OldVersion"
  Pop $0
  ${NSD_CreateLabel} 0 21u 100% 12u "旧版本安装位置"
  Pop $0
  ${NSD_CreateText} 0 35u 100% 19u "$OldInstallDir"
  Pop $0
  ${NSD_Edit_SetReadOnly} $0 1
  ${NSD_CreateCheckbox} 0 65u 100% 17u "安装新版本前，先卸载旧版本"
  Pop $OldCheckbox
  ${NSD_SetState} $OldCheckbox $OldRemove
  ${NSD_OnClick} $OldCheckbox ManjuUpgradeToggle
  ${NSD_CreateCheckbox} 10u 85u 95% 17u "卸载旧版本时保留用户配置"
  Pop $KeepConfigCheckbox
  ${NSD_SetState} $KeepConfigCheckbox $KeepConfig
  ${NSD_OnClick} $KeepConfigCheckbox ManjuKeepConfigToggle
  EnableWindow $KeepConfigCheckbox $OldRemove
  ${NSD_CreateLabel} 0 108u 100% 23u "取消保留将备份并重置软件设置；项目、成片、授权、模型和小v喵本地数据保留。"
  Pop $0
  Call ManjuStylePage
  nsDialogs::Show
FunctionEnd

Function ManjuUpgradeToggle
  Pop $0
  ${NSD_GetState} $OldCheckbox $OldRemove
  EnableWindow $KeepConfigCheckbox $OldRemove
FunctionEnd

Function ManjuKeepConfigToggle
  Pop $0
  ${NSD_GetState} $KeepConfigCheckbox $KeepConfig
FunctionEnd

Function ManjuUpgradeLeave
  ${NSD_GetState} $OldCheckbox $OldRemove
  ${NSD_GetState} $KeepConfigCheckbox $KeepConfig
FunctionEnd

Function ManjuCheckSettingsReset
  ${If} $OldRemove != 1
    Return
  ${EndIf}
  ${If} $KeepConfig != 0
    Return
  ${EndIf}
  ClearErrors
  ExecWait '$\"$PLUGINSDIR\ManjuSettings.exe$\" --check --report $\"$PLUGINSDIR\settings-check.json$\"' $0
  ${If} ${Errors}
    Goto settings_check_failed
  ${EndIf}
  ${If} $0 != 0
    Goto settings_check_failed
  ${EndIf}
  Return
  settings_check_failed:
    MessageBox MB_ICONSTOP|MB_OK "无法安全重置用户配置。请先退出漫剧工坊并检查配置文件和目录权限；旧版本尚未卸载。" /SD IDOK
    SetErrorLevel 2
    Abort
FunctionEnd

Function ManjuApplySettingsReset
  ${If} $OldRemove != 1
    Return
  ${EndIf}
  ${If} $KeepConfig != 0
    Return
  ${EndIf}
  ClearErrors
  ExecWait '$\"$PLUGINSDIR\ManjuSettings.exe$\" --reset --report $\"$PLUGINSDIR\settings-reset.json$\"' $0
  ${If} ${Errors}
    Goto settings_reset_failed
  ${EndIf}
  ${If} $0 != 0
    Goto settings_reset_failed
  ${EndIf}
  DetailPrint "已备份并重置软件设置；项目、授权、模型与小v喵数据保留"
  Return
  settings_reset_failed:
    MessageBox MB_ICONSTOP|MB_OK "用户配置未能重置，原配置已保留，新版本尚未写入。请关闭软件后重试。" /SD IDOK
    SetErrorLevel 2
    Abort
FunctionEnd

Function ManjuRemoveOld
  ${If} $OldRemove != 1
    Return
  ${EndIf}
  ; The checkbox only takes effect here, after prerequisites are ready and the
  ; user has pressed Install. Fail closed if the old executable is in use.
  System::Call 'kernel32::CreateFileW(w "$OldInstallDir\漫剧工坊.exe",i 0x40000000,i 7,p 0,i 3,i 0,p 0)p.r0'
  ${If} $0 P= -1
    MessageBox MB_ICONSTOP|MB_OK "旧程序正在使用或无法访问。请退出旧版漫剧工坊后重新安装；尚未卸载旧版本。" /SD IDOK
    SetErrorLevel 2
    Abort
  ${EndIf}
  System::Call 'kernel32::CloseHandle(p r0)'
  DetailPrint "正在卸载旧版漫剧工坊 $OldVersion，保留个人数据"
  ClearErrors
  ; _?= must be the final unquoted parameter so ExecWait waits for the real
  ; uninstaller rather than its temporary relauncher (NSIS command-line docs).
  ExecWait '$\"$OldInstallDir\卸载漫剧工坊.exe$\" /S _?=$OldInstallDir' $0
  ${If} ${Errors}
    Goto old_remove_failed
  ${EndIf}
  ${If} $0 != 0
    Goto old_remove_failed
  ${EndIf}
  IfFileExists "$OldInstallDir\漫剧工坊.exe" old_remove_failed
  ; The uninstaller cannot delete itself when using _?=. Remove that exact
  ; file afterwards; RMDir succeeds only when no personal files remain.
  Delete "$OldInstallDir\卸载漫剧工坊.exe"
  RMDir "$OldInstallDir"
  Return
  old_remove_failed:
    MessageBox MB_ICONSTOP|MB_OK "旧版本卸载未完成，新版本尚未写入。请退出旧程序并重试。个人数据不会由安装程序清理。" /SD IDOK
    SetErrorLevel 2
    Abort
FunctionEnd
!macroend
