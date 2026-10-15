; Inno Setup 6 script for the Nuitka standalone tree.
; Compile this after `build/psm.dist` exists. Do not ship PSM.ini or psm_baseline.dat:
; those are written beside the executable on the machine that runs it.
;
; PYTHONPATH=src python -m nuitka --standalone --windows-console-mode=disable
;   --windows-icon-from-ico=assets/icon.ico --enable-plugin=tk-inter
;   --include-package=dxcam --include-package=comtypes
;   --include-package-data=dxcam --include-data-dir=assets=assets
;   --output-dir=build --output-filename="Project Stella Montis.exe"
;   --company-name=Factiosi --product-name="Project Stella Montis"
;   --file-version=1.0.1.0 --product-version=1.0.1.0
;   --file-description="Project Stella Montis" psm.py

#define AppName "Project Stella Montis"
#define AppVersion "1.0.1"
#define AppPublisher "Factiosi"
#define AppExeName "Project Stella Montis.exe"
#define BuildDir "..\build\psm.dist"

[Setup]
AppId={{A566548F-CD7D-4CF0-906D-BF8BF8AABE1F}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}.0
VersionInfoProductName={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename={#AppName} {#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "PSM.ini,psm_baseline.dat,psm_baseline.dat.tmp"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
