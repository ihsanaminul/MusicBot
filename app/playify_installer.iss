; ===================================================================
;  Playify Installer Script - Updated for Auto-Update Feature
; ===================================================================

[Setup]
; --- Application Identity ---
AppName=Playify
; The AppVerName is what is displayed in "Add/Remove Programs".
; It includes the AppName and the version.
AppVerName=Playify v1.2.0
; This version number is crucial. The auto-updater will compare against this.
; Remember to increment this for each new release.
AppVersion=1.2.0
AppPublisher=Alan (alananasssss)
DefaultDirName={autopf}\Playify

; --- Installation Options ---
DisableProgramGroupPage=yes
; The OutputBaseFilename should also reflect the new version.
OutputBaseFilename=Playify_Setup_v1.2.0
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\images\playify.ico

; --- Silent Install Configuration ---
; These settings ensure that when the updater runs the installer,
; it can do so silently without bothering the user.
PrivilegesRequired=admin
UninstallDisplayIcon={app}\Playify.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
; Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}";

[Files]
; This command copies all application files.
; Because the user's config file is in %LOCALAPPDATA%\Playify, it will NOT be
; deleted or overwritten during an update, which is the desired behavior.
Source: "dist\Playify\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Playify"; Filename: "{app}\Playify.exe"
Name: "{autodesktop}\Playify"; Filename: "{app}\Playify.exe"; Tasks: desktopicon

[Run]
; This command launches the program after the installation is complete.
; It's smart enough to not run if the installation was silent (/SILENT),
; but the postinstall flag ensures it runs after a successful setup.
Filename: "{app}\Playify.exe"; Description: "{cm:LaunchProgram,Playify}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; This ensures the directory in AppData is removed upon uninstallation
; for a clean removal.
Type: filesandordirs; Name: "{localappdata}\Playify"
