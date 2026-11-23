; SPDX-License-Identifier: GPL-3.0-or-later
; SPDX-FileCopyrightText: 2026 John Goodman
;
; Windows installer (Inno Setup 6). Built by package.py:
;   ISCC /DAppVersion=0.9.0 /DSource=<package folder> /DOutput=<folder> windows-installer.iss
;
; Installs for all users into Program Files, because Windows speech (SAPI)
; voices are registered machine-wide. Adds a Start menu entry (and an optional
; desktop shortcut). Uninstalling quits Akousousin, restores the speech
; settings it changed and removes the program; downloaded voices, dictation
; models and settings stay (Advanced → Remove Akousousin completely removes them).

#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef Source
  #define Source "..\build\standalone-package\Akousousin"
#endif
#ifndef Output
  #define Output "..\standalone-dist"
#endif

[Setup]
AppId={{44568792-AC37-4B60-B64A-463764780809}
AppName=Akousousin
AppVersion={#AppVersion}
AppVerName=Akousousin {#AppVersion}
AppPublisher=Akousousin
AppPublisherURL=https://github.com/jg00dman/akousousin
AppSupportURL=https://github.com/jg00dman/akousousin/issues
AppUpdatesURL=https://github.com/jg00dman/akousousin/releases
DefaultDirName={autopf}\Akousousin
DisableDirPage=auto
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#Output}
OutputBaseFilename=Akousousin-Windows-x86_64-Setup
SetupIconFile=resources\akousousin.ico
UninstallDisplayIcon={app}\akousousin.exe
UninstallDisplayName=Akousousin
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
; Only the per-user start-at-login value is touched in HKCU, on uninstall.
UsedUserAreasWarning=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "pt"; MessagesFile: "compiler:Languages\Portuguese.isl"
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Akousousin"; Filename: "{app}\akousousin.exe"; Comment: "Natural voices and dictation, on this computer"
Name: "{autodesktop}\Akousousin"; Filename: "{app}\akousousin.exe"; Tasks: desktopicon

[Registry]
; Created by Akousousin itself when "Start at login" is on; removed with the program.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueName: "Akousousin"; ValueType: none; Flags: uninsdeletevalue dontcreatekey

[Run]
; After an upgrade, point registered Windows voices at the new engine.
Filename: "{app}\akousousin.exe"; Parameters: "--refresh-registrations"; Flags: runhidden waituntilterminated; StatusMsg: "Updating registered voices..."
Filename: "{app}\akousousin.exe"; Description: "{cm:LaunchProgram,Akousousin}"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{app}\akousousin.exe"; Parameters: "--quit"; Flags: runhidden waituntilterminated; RunOnceId: "Quit"
Filename: "{app}\akousousin.exe"; Parameters: "--uninstall"; Flags: runhidden waituntilterminated; RunOnceId: "RestoreSpeech"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  // Quit a running copy (tray, speech service) so its files can be replaced.
  if FileExists(ExpandConstant('{app}\akousousin.exe')) then
    ExecAsOriginalUser(ExpandConstant('{app}\akousousin.exe'), '--quit', '', SW_HIDE,
                       ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  // Backups of replaced speech settings are only needed until they are restored.
  // If restoring failed, keep them (and the record) for manual recovery.
  if (CurUninstallStep = usPostUninstall) and
     not FileExists(ExpandConstant('{app}\install-state.json')) then
  begin
    DelTree(ExpandConstant('{app}\backups'), True, True, True);
    DelTree(ExpandConstant('{app}\compat'), True, True, True);
    RemoveDir(ExpandConstant('{app}'));
  end;
end;
