#ifndef AppSource
  #error AppSource is required
#endif
#ifndef OutputFolder
  #error OutputFolder is required
#endif
[Setup]
AppId={{3B3C1924-C705-46F5-B8C6-964D6B7C6134}
AppName=一歌一景
AppVersion=8.0.0
AppPublisher=Hgb-2005
AppPublisherURL=https://github.com/Hgb-2005/song-scene
AppSupportURL=https://github.com/Hgb-2005/song-scene/issues
DefaultDirName={localappdata}\Programs\SongScene
DefaultGroupName=一歌一景
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputFolder}
OutputBaseFilename=SongScene-v8-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\SongScene.exe
CloseApplications=yes
RestartApplications=no
VersionInfoVersion=8.0.0.0

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\一歌一景"; Filename: "{app}\SongScene.exe"
Name: "{autodesktop}\一歌一景"; Filename: "{app}\SongScene.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SongScene.exe"; Description: "打开一歌一景"; Flags: nowait postinstall skipifsilent

; User work is stored outside {app}. Do not add an UninstallDelete rule for it.
