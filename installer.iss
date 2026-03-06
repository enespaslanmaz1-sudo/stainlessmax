; STAINLESS MAX - PRO INSTALLER v2.2.1
; Minimalist, Hizli, Modern - Discord/VSCode Stili Kurulum

[Setup]
AppName=Stainless Max
AppVersion=2.2.1
AppPublisher=StainlessMax
AppPublisherURL=https://stainlesmax.com
AppSupportURL=https://stainlesmax.com/support
AppUpdatesURL=https://stainlesmax.com/updates
AppId={{8A7F3B2C-1D4E-4F5A-9E8B-2C3D4E5F6A7B}
UsePreviousAppDir=no

; Kurulum klasörü (yönetici izni GEREKTIRMEZ - Discord/VSCode gibi)
DefaultDirName={localappdata}\Programs\Stainless Max
DefaultGroupName=Stainless Max
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Çıktı ayarları
OutputDir=dist\installer
OutputBaseFilename=StainlessMax_Setup_v2.2.1
SetupIconFile=stainlessmax_logo.ico
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Modern wizard
WizardStyle=modern
WizardResizable=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=no

; Finished sayfası mesajı (sadece uygulama adı ve sürüm)
[Messages]
turkish.FinishedHeadingLabel=Stainless Max v2.2.1
turkish.FinishedLabel=Stainless Max v2.2.1 başarıyla kuruldu.%nUygulama kullanıma hazır.

; Kaldırma bilgileri
UninstallDisplayIcon={app}\StainlessMax.exe
UninstallDisplayName=Stainless Max
CloseApplications=yes
CloseApplicationsFilter=StainlessMax.exe

; Minimum Windows 10
MinVersion=10.0

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "startuprun"; Description: "Windows başlangıcında otomatik başlat"; GroupDescription: "Başlangıç:"; Flags: unchecked

[Files]
; WebView2 Runtime Bootstrapper (native pencere için zorunlu)
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall
; Ana uygulama EXE
Source: "dist\StainlessMax\StainlessMax.exe"; DestDir: "{app}"; Flags: ignoreversion
; Tüm bağımlılıklar (dizin yapısıyla)
Source: "dist\StainlessMax\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "\.env,hesaplar.txt"
; .env.example → kullanıcı kendi API keylerini girer
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion onlyifdoesntexist

[Icons]
; Başlat menüsü
Name: "{autoprograms}\Stainless Max"; Filename: "{app}\StainlessMax.exe"; IconFilename: "{app}\_internal\stainlessmax_logo.ico"; AppUserModelID: "StainlessMax.App.1.0"
Name: "{autoprograms}\Stainless Max\Stainless Max Kaldır"; Filename: "{uninstallexe}"
; Masaüstü ikonu (Zorunlu, otomatik oluşturulur)
Name: "{autodesktop}\Stainless Max"; Filename: "{app}\StainlessMax.exe"; IconFilename: "{app}\_internal\stainlessmax_logo.ico"; AppUserModelID: "StainlessMax.App.1.0"

[Registry]
; Windows başlangıcına ekle (isteğe bağlı)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "StainlessMax"; ValueData: """{app}\StainlessMax.exe"""; Tasks: startuprun; Flags: uninsdeletevalue

[Dirs]
; Uygulama veri dizinleri (ilk çalışmada hazır olsun)
Name: "{app}\AppCore\outputs"
Name: "{app}\AppCore\logs"
Name: "{app}\AppCore\temp"
Name: "{app}\AppCore\tokens"
Name: "{app}\AppCore\config"
Name: "{app}\AppCore\upload_queue"
Name: "{app}\System_Data\outputs"
Name: "{app}\System_Data\clips_cache"
Name: "{app}\System_Data\audio"
Name: "{app}\System_Data\temp"

[Run]
; WebView2 Runtime kur (yoksa) — kullanıcıya UAC izni sorabilmek için silent değil normal çalıştırılır
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; StatusMsg: "Microsoft Edge WebView2 Runtime kuruluyor (Lütfen onay verin)..."; Flags: waituntilterminated; Check: not IsWebView2Installed
; Kurulum biter bitmez çalıştır (Chrome/Discord gibi)
Filename: "{app}\StainlessMax.exe"; Description: "Stainless Max Başlat"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; Üstüne kurarken eski log ve geçici dosyaları temizle
Type: filesandordirs; Name: "{app}\AppCore\logs\*"
Type: filesandordirs; Name: "{app}\AppCore\temp\*"
Type: filesandordirs; Name: "{app}\System_Data\temp\*"

[Code]
// WebView2 Runtime kurulu mu kontrol et (Registry'den)
function IsWebView2Installed: Boolean;
var
  ResultStr: string;
begin
  Result := RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE50529}', 'pv', ResultStr)
    or RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE50529}', 'pv', ResultStr)
    or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-235B8DE50529}', 'pv', ResultStr);
  if Result then
    Log('WebView2 Runtime found: ' + ResultStr)
  else
    Log('WebView2 Runtime NOT found - will install');
end;

// İlk kurulumda .env.example'ı .env olarak kopyala
procedure CopyEnvExample();
var
  ExampleFile, EnvFile: string;
begin
  ExampleFile := ExpandConstant('{app}\.env.example');
  EnvFile := ExpandConstant('{app}\.env');
  if FileExists(ExampleFile) and not FileExists(EnvFile) then
  begin
    if FileCopy(ExampleFile, EnvFile, False) then
      Log('Created .env from .env.example')
    else
      Log('Failed to create .env from .env.example');
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CopyEnvExample();
  end;
end;
