; Inno Setup script for Hushtype. Built by .github/workflows/build.yml.
; Installs per user (no admin rights) into %LOCALAPPDATA%\Programs\Hushtype.

#define AppVersion GetEnv("HUSHTYPE_VERSION")
#if AppVersion == ""
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{768CA8E2-9366-44AB-8EB8-BCC586B0E30D}
AppName=Hushtype
AppVersion={#AppVersion}
AppVerName=Hushtype {#AppVersion}
AppPublisher=Khurram Iftikhar
AppPublisherURL=https://github.com/khurramiftikhar77/Hushtype
AppSupportURL=https://github.com/khurramiftikhar77/Hushtype/issues
DefaultDirName={localappdata}\Programs\Hushtype
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Hushtype-Setup-{#AppVersion}
SetupIconFile=hushtype.ico
UninstallDisplayIcon={app}\Hushtype.exe
UninstallDisplayName=Hushtype
LicenseFile=..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Closes a running Hushtype before updating or uninstalling.
AppMutex=HushtypeSingleInstance
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Hushtype\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; Remove files from an older version before copying the new one.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Hushtype"; Filename: "{app}\Hushtype.exe"
Name: "{autodesktop}\Hushtype"; Filename: "{app}\Hushtype.exe"; Tasks: desktopicon

[Registry]
; The app itself manages "Start with Windows" (Settings). Uninstall removes the entry.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Hushtype"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Hushtype.exe"; Description: "Open Hushtype now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
