#ifndef SourceDir
  #error SourceDir must point to the PyInstaller onedir folder.
#endif

#ifndef ReleaseVersion
  #define ReleaseVersion "1.0.0"
#endif

[Setup]
AppId={{25351A96-AECF-4C3E-9E49-0B87CA42C317}
AppName=红烧box
AppVersion={#ReleaseVersion}
DefaultDirName={localappdata}\Programs\红烧box
DefaultGroupName=红烧box
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputBaseFilename=红烧box-Setup-{#ReleaseVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\红烧box.exe

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "启动红烧box.vbs"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\红烧box"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\启动红烧box.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\红烧box.exe"
Name: "{autodesktop}\红烧box"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\启动红烧box.vbs"""; WorkingDir: "{app}"; IconFilename: "{app}\红烧box.exe"; Tasks: desktopicon

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\启动红烧box.vbs"""; Description: "启动红烧box"; Flags: nowait postinstall skipifsilent
