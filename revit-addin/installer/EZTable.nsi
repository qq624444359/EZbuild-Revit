; EZTable for Revit -- Windows installer.
;
; Installs the same EZTable.bundle the App Store gets, into the current user's
; ApplicationPlugins folder, where Revit 2026 and 2027 pick it up on start. It
; needs no administrator rights, and registers an uninstaller under Windows
; Settings > Apps.
;
; Build (on Windows or Linux, NSIS 3):
;   makensis -DVERSION=1.0.0 -DBUNDLE=dist/EZTable.bundle -DOUTFILE=EZTable-Setup.exe revit-addin/installer/EZTable.nsi
; BUNDLE is the folder CI assembles; VERSION must be its AppVersion.

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!ifndef VERSION
  !error "Pass the version: -DVERSION=1.2.3"
!endif
!ifndef BUNDLE
  !error "Pass the assembled bundle: -DBUNDLE=path/to/EZTable.bundle"
!endif
!ifndef OUTFILE
  !define OUTFILE "EZTable-Setup.exe"
!endif

!define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\EZTable"
!define UNINSTALLER "Uninstall EZTable.exe"

Name "EZTable for Revit"
OutFile "${OUTFILE}"
RequestExecutionLevel user
InstallDir "$APPDATA\Autodesk\ApplicationPlugins\EZTable.bundle"
SetCompressor /SOLID lzma
BrandingText "EZTable ${VERSION}"

VIProductVersion "${VERSION}.0"
VIAddVersionKey "ProductName" "EZTable for Revit"
VIAddVersionKey "CompanyName" "Pitayadesign"
VIAddVersionKey "FileDescription" "EZTable for Revit installer"
VIAddVersionKey "FileVersion" "${VERSION}"
VIAddVersionKey "ProductVersion" "${VERSION}"
VIAddVersionKey "LegalCopyright" "(c) 2026 EZbuild"

!define MUI_ICON "EZTable.ico"
!define MUI_UNICON "EZTable.ico"
!define MUI_ABORTWARNING

!define MUI_WELCOMEPAGE_TITLE "EZTable ${VERSION} for Revit"
!define MUI_WELCOMEPAGE_TEXT "This installs EZTable, which draws Excel worksheets into Revit drafting views, for Revit 2026 and Revit 2027.$\r$\n$\r$\nPlease close Revit before you continue.$\r$\n$\r$\nEZTable is installed for your Windows account only, so no administrator rights are needed."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "${BUNDLE}/LICENSE.txt"
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_TITLE "EZTable is installed"
!define MUI_FINISHPAGE_TEXT "Start Revit 2026 or Revit 2027. The commands are on the EZbuild tab, in the Table panel. Press F1 over any of them for help.$\r$\n$\r$\nEZTable is not code-signed yet, so Revit may ask whether to load it the first time. Choose Always Load."
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

; Revit holds the add-in's DLLs open while it runs, so they cannot be replaced
; or removed until it closes. Ask rather than fail halfway.
!macro WAIT_FOR_REVIT un
  Function ${un}WaitForRevit
    check:
      nsExec::ExecToStack 'cmd /c tasklist /FI "IMAGENAME eq Revit.exe" /NH | find /I "Revit.exe"'
      Pop $0
      Pop $1
      StrCmp $0 "0" 0 done
      MessageBox MB_RETRYCANCEL|MB_ICONEXCLAMATION "Revit is running. Close Revit, then click Retry." IDRETRY check
      Abort
    done:
  FunctionEnd
!macroend
!insertmacro WAIT_FOR_REVIT ""
!insertmacro WAIT_FOR_REVIT "un."

Section "EZTable"
  Call WaitForRevit
  ; A clean copy every time, so nothing from an older version lingers -- this
  ; also replaces a bundle that was copied in by hand
  RMDir /r "$INSTDIR"
  SetOutPath "$INSTDIR"
  File /r "${BUNDLE}/*.*"
  WriteUninstaller "$INSTDIR\${UNINSTALLER}"

  WriteRegStr HKCU "${UNINST_KEY}" "DisplayName" "EZTable for Revit"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${UNINST_KEY}" "Publisher" "Pitayadesign"
  WriteRegStr HKCU "${UNINST_KEY}" "DisplayIcon" "$INSTDIR\${UNINSTALLER}"
  WriteRegStr HKCU "${UNINST_KEY}" "UninstallString" '"$INSTDIR\${UNINSTALLER}"'
  WriteRegStr HKCU "${UNINST_KEY}" "QuietUninstallString" '"$INSTDIR\${UNINSTALLER}" /S'
  WriteRegStr HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${UNINST_KEY}" "URLInfoAbout" "https://www.ezbuild.co.nz/for-revit.html"
  WriteRegStr HKCU "${UNINST_KEY}" "HelpLink" "https://www.ezbuild.co.nz/for-revit-help.html"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD HKCU "${UNINST_KEY}" "EstimatedSize" "$0"
SectionEnd

Section "Uninstall"
  Call un.WaitForRevit
  ; Tables already drawn stay in users' models: they are ordinary Revit elements
  RMDir /r "$INSTDIR"
  DeleteRegKey HKCU "${UNINST_KEY}"
SectionEnd
