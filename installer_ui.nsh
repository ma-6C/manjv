; Shared by the production installer and the harmless UI verification wizard.
; All text stays in native controls; artwork contains no rasterized UI text.
ManifestDPIAware true
SetFont "Microsoft YaHei UI" 10
BrandingText "Manju Studio"
ShowInstDetails show
ShowUninstDetails show
; Keep NSIS's built-in free-space validation and show both figures explicitly.
SpaceTexts "所需空间：" "可用空间："

!define MUI_BGCOLOR "FFFFFF"
!define MUI_TEXTCOLOR "202124"
!define MUI_WELCOMEFINISHPAGE_BITMAP "${MANJU_ROOT}\assets\installer\wizard.bmp"
!define MUI_UNWELCOMEFINISHPAGE_BITMAP "${MANJU_ROOT}\assets\installer\wizard.bmp"
!define MUI_HEADERIMAGE
!define MUI_HEADERIMAGE_RIGHT
!define MUI_HEADERIMAGE_BITMAP "${MANJU_ROOT}\assets\installer\header.bmp"
!define MUI_COMPONENTSPAGE_NODESC
!define MUI_CUSTOMFUNCTION_GUIINIT ManjuFontsInit
!define MUI_CUSTOMFUNCTION_UNGUIINIT un.ManjuFontsInit

!define MUI_WELCOMEPAGE_TITLE "欢迎使用$\r$\n漫剧工坊"
!define MUI_WELCOMEPAGE_TEXT "整理素材、识别剧情、制作成片。$\r$\n$\r$\n安装向导将帮助你选择组件和安装位置，并检查所需的系统运行环境。$\r$\n$\r$\n点击“下一步”开始设置。"
!define MUI_COMPONENTSPAGE_TEXT_TOP "主程序为必选项。离线 AI 引擎也可在安装完成后单独导入。"

; Use antialiased native fonts even when a remote Windows session has font
; smoothing disabled. This affects our controls only, never system settings.
Var ManjuBodyFont
Var ManjuTitleFont
Var ManjuHeaderFont
!macro MANJU_UI_FUNCTIONS
!insertmacro MANJU_UI_FONT_FUNCTIONS ""
!insertmacro MANJU_UI_FONT_FUNCTIONS "un."
Function ManjuStyleWelcome
  Call ManjuStylePage
  SendMessage $mui.WelcomePage.Title ${WM_SETFONT} $ManjuTitleFont 1
FunctionEnd
Function ManjuStyleFinish
  Call ManjuStylePage
  SendMessage $mui.FinishPage.Title ${WM_SETFONT} $ManjuTitleFont 1
FunctionEnd
!macroend

!macro MANJU_UI_FONT_FUNCTIONS PREFIX
Function ${PREFIX}ManjuFontsInit
  Push $0
  Push $1
  Push $2
  System::Call 'user32::GetDC(p $HWNDPARENT)p.r0'
  System::Call 'gdi32::GetDeviceCaps(p r0, i 90)i.r1'
  System::Call 'user32::ReleaseDC(p $HWNDPARENT,p r0)'
  IntOp $2 $1 * -10
  IntOp $2 $2 / 72
  System::Call 'gdi32::CreateFontW(i r2,i 0,i 0,i 0,i 400,i 0,i 0,i 0,i 1,i 0,i 0,i 5,i 0,w "Microsoft YaHei UI")p.s'
  Pop $ManjuBodyFont
  System::Call 'gdi32::CreateFontW(i r2,i 0,i 0,i 0,i 700,i 0,i 0,i 0,i 1,i 0,i 0,i 5,i 0,w "Microsoft YaHei UI")p.s'
  Pop $ManjuHeaderFont
  IntOp $2 $1 * -12
  IntOp $2 $2 / 72
  System::Call 'gdi32::CreateFontW(i r2,i 0,i 0,i 0,i 700,i 0,i 0,i 0,i 1,i 0,i 0,i 5,i 0,w "Microsoft YaHei UI")p.s'
  Pop $ManjuTitleFont
  Pop $2
  Pop $1
  Pop $0
FunctionEnd
Function ${PREFIX}ManjuStylePage
  Push $0
  Push $1
  ; Each page owns its child controls. Keep the OS title bar and user settings.
  System::Call 'user32::GetWindow(p $HWNDPARENT,i 5)p.r0'
  ${DoWhile} $0 P<> 0
    SendMessage $0 ${WM_SETFONT} $ManjuBodyFont 1
    System::Call 'user32::GetWindow(p r0,i 5)p.r1'
    ${DoWhile} $1 P<> 0
      SendMessage $1 ${WM_SETFONT} $ManjuBodyFont 1
      System::Call 'user32::GetWindow(p r1,i 2)p.r1'
    ${Loop}
    System::Call 'user32::GetWindow(p r0,i 2)p.r0'
  ${Loop}
  SendMessage $mui.Header.Text ${WM_SETFONT} $ManjuHeaderFont 1
  Pop $1
  Pop $0
FunctionEnd
!macroend
