; ASTA — instalador do Windows (Inno Setup 6). Gerado pelo workflow `release` via build-windows.ps1, que monta a pasta `stage` ao lado deste arquivo:
;   stage\python   Python embutido (python.org, "embeddable") com o ASTA instalado no site-packages
;   stage\native   asta_core.dll — o núcleo em Rust, já compilado
;   stage\ASTA.cmd e stage\asta.ico
; Instala só para o usuário (sem administrador). Os dados do usuário (%USERPROFILE%\.asta) ficam fora da pasta do programa: atualizar ou desinstalar nunca os apaga.

#ifndef AppVersion
  #define AppVersion "0.14.0"
#endif
#ifndef FileLabel
  #define FileLabel "0-14"
#endif

[Setup]
AppId={{6F1A2C3D-8B4E-4F70-A1D2-5C9E7B3A0F14}
AppName=ASTA
AppVersion={#AppVersion}
AppVerName=ASTA {#AppVersion}
AppPublisher=KMC
AppPublisherURL=https://github.com/KMC1525/ASTA
AppSupportURL=https://github.com/KMC1525/ASTA/issues
AppUpdatesURL=https://github.com/KMC1525/ASTA/releases
DefaultDirName={localappdata}\Programs\ASTA
DefaultGroupName=ASTA
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist-installers
OutputBaseFilename=ASTA-{#FileLabel}-Win
SetupIconFile=stage\asta.ico
UninstallDisplayIcon={app}\asta.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\..\LICENSE
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "stage\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "stage\native\*"; DestDir: "{app}\native"; Flags: ignoreversion
Source: "stage\ASTA.cmd"; DestDir: "{app}"; Flags: ignoreversion
Source: "stage\asta.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\ASTA"; Filename: "{app}\ASTA.cmd"; IconFilename: "{app}\asta.ico"; Flags: runminimized; Comment: "ASTA — open source AI creation hub"
Name: "{autodesktop}\ASTA"; Filename: "{app}\ASTA.cmd"; IconFilename: "{app}\asta.ico"; Tasks: desktopicon; Flags: runminimized

[Run]
Filename: "{app}\ASTA.cmd"; Description: "{cm:LaunchProgram,ASTA}"; Flags: nowait postinstall skipifsilent runminimized

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
