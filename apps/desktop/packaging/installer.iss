; Inno Setup script for TabForge-Setup.exe (ADR-0008). Per-user install, no admin rights.
; Compile from apps/desktop: iscc packaging\installer.iss
#define AppVersion GetEnv("TABFORGE_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{7B0F3E55-6C2A-4B7E-9F1D-2A8C4E1B9D60}
AppName=TabForge
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\TabForge
DefaultGroupName=TabForge
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=TabForge-Setup
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=TabForge

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\TabForge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\TabForge"; Filename: "{app}\TabForge.exe"
Name: "{autodesktop}\TabForge"; Filename: "{app}\TabForge.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TabForge.exe"; Description: "{cm:LaunchProgram,TabForge}"; Flags: nowait postinstall skipifsilent

; User data (%LOCALAPPDATA%\TabForge: database, audio, logs) is kept on uninstall on purpose.
