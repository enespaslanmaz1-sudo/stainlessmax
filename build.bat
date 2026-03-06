@echo off
setlocal enableextensions
cd /d "%~dp0"
title STAINLESS MAX - Build

echo ============================================
echo   STAINLESS MAX v2.2.1 - Build Script
echo ============================================
echo.

REM ===== On Kontroller =====
echo [CHECK] Python kontrolu...
python --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo HATA: Python bulunamadi. Python 3.10+ kurulu olmali.
    exit /b 1
)

echo [CHECK] Zorunlu dosyalar kontrol ediliyor...
for %%F in (main.py desktop_app.py stainlessmax_logo.png AppCore settings.json) do (
    if not exist "%%F" (
        echo HATA: %%F bulunamadi!
        exit /b 1
    )
)

REM ===== .env.example kontrolü =====
if not exist ".env.example" (
    echo [INFO] .env.example olusturuluyor...
    (
        echo # Stainless Max API Keys
        echo GEMINI_API_KEY=
        echo PEXELS_API_KEY=
        echo PIXABAY_API_KEY=
        echo TELEGRAM_BOT_TOKEN=
        echo TELEGRAM_ADMIN_ID=
        echo FLASK_SECRET_KEY=stainless_secure_2025
    ) > .env.example
    echo [INFO] .env.example olusturuldu.
)

REM ===== Icon Kontrolü =====
echo.
echo [1/5] Icon kontrol ediliyor...
if not exist "stainlessmax_logo.ico" (
    if exist "convert_icon.py" (
        echo [INFO] Icon donusturuluyor...
        python convert_icon.py
        if %ERRORLEVEL% neq 0 (
            echo HATA: Icon donusturme basarisiz!
            exit /b 1
        )
    ) else (
        echo HATA: stainlessmax_logo.ico bulunamadi ve convert_icon.py da yok.
        exit /b 1
    )
)
echo [OK] Icon hazir.

REM ===== Eski build temizle =====
echo.
echo [2/5] Eski build temizleniyor...
if exist "build" rd /s /q "build"
if exist "dist" rd /s /q "dist"
echo [OK] Temizlendi.

REM ===== Ana EXE build =====
echo.
echo [3/5] Ana uygulama EXE olusturuluyor (birkas dakika surebilir)...
mkdir "D:\Masaustu\stainless\temp_pyinstaller_cache" 2>nul
mkdir "D:\Masaustu\stainless\temp" 2>nul
set "PYINSTALLER_CONFIG_DIR=D:\Masaustu\stainless\temp_pyinstaller_cache"
set "TMP=D:\Masaustu\stainless\temp"
set "TMP=D:\Masaustu\stainless\temp"
set "TEMP=D:\Masaustu\stainless\temp"

python -m PyInstaller StainlessMax.spec --noconfirm --clean --workpath=D:\Masaustu\stainless\build --distpath=D:\Masaustu\stainless\dist > build_run_latest.log 2>&1

if %ERRORLEVEL% neq 0 (

    echo.
    echo HATA: Ana uygulama build basarisiz!
    echo Log: build_run_latest.log
    type build_run_latest.log
    exit /b 1
)
echo [OK] Ana EXE olusturuldu.

REM ===== Updater.exe build =====
echo.
echo [4/5] Updater.exe olusturuluyor...
python -m PyInstaller updater.py ^
    --noconfirm --clean --onefile ^
    --name Updater ^
    --distpath dist\StainlessMax ^
    --workpath build\updater ^
    --specpath build\updater ^
    --noconsole ^
    --hidden-import psutil 2>&1

if %ERRORLEVEL% neq 0 (
    echo UYARI: Updater.exe olusturulamadi (opsiyonel, devam ediliyor...)
) else (
    echo [OK] Updater.exe olusturuldu.
)

REM ===== Cikti Kontrolu =====
echo.
echo [5/5] Cikti kontrol ediliyor...
if not exist "dist\StainlessMax\StainlessMax.exe" (
    echo HATA: dist\StainlessMax\StainlessMax.exe olusmadi!
    exit /b 1
)

REM ===== Kullanici Dosyalarini Kopyala =====
echo [INFO] Tamamlayici dosyalar kopyalaniyor...

if exist ".env.example" (
    copy /y ".env.example" "dist\StainlessMax\.env.example" >nul
    echo [INFO] .env.example kopyalandi.
)
if exist "update_manifest.json" (
    copy /y "update_manifest.json" "dist\StainlessMax\update_manifest.json" >nul
    echo [INFO] update_manifest.json kopyalandi.
)
if exist "SETUP_GUIDE.md" (
    copy /y "SETUP_GUIDE.md" "dist\StainlessMax\SETUP_GUIDE.md" >nul
    echo [INFO] SETUP_GUIDE.md kopyalandi.
)

REM ===== Inno Setup Installer =====
echo.
set "ISCC_PATH="
for %%P in (
    "D:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "C:\Program Files\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
) do (
    if exist %%P set "ISCC_PATH=%%P"
)

if defined ISCC_PATH (
    echo [BONUS] Inno Setup bulundu, installer olusturuluyor...
    mkdir "dist\installer" 2>nul
    %ISCC_PATH% installer.iss
    if %ERRORLEVEL% equ 0 (
        echo [OK] Installer olusturuldu: dist\installer\
    ) else (
        echo UYARI: Installer olusturma basarisiz (installer.iss kontrol edin)
    )
) else (
    echo [BILGI] Inno Setup kurulu degil, installer olusmadi.
    echo         Inno Setup 6'yi indirin: https://jrsoftware.org/isdownload.php
)

echo.
echo ============================================
echo   BUILD TAMAMLANDI!
echo   EXE:  dist\StainlessMax\StainlessMax.exe
if exist "dist\StainlessMax\Updater.exe" (
    echo   UPD:  dist\StainlessMax\Updater.exe
)
if exist "dist\installer\StainlessMax_Setup_v2.2.1.exe" (
    echo   SETUP: dist\installer\StainlessMax_Setup_v2.2.1.exe
)
echo ============================================
echo.
