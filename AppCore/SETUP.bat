@echo off
chcp 65001 >nul
title Stainless Max - Kurulum

cd /d "%~dp0"

echo ==========================================
echo  Stainless Max v2.1.0 - Kurulum
echo ==========================================
echo.

REM Python kontrol
python --version >nul 2>&1
if errorlevel 1 (
    echo [HATA] Python bulunamadi!
    echo Lutfen Python 3.10+ kurun: https://python.org
    pause
    exit /b 1
)

echo [1/5] Python surumu kontrol ediliyor...
python --version

echo.
echo [2/5] Virtual environment olusturuluyor...
if exist ".venv" (
    echo Mevcut venv kullaniliyor...
) else (
    python -m venv .venv
    echo ✓ venv olusturuldu
)

echo.
echo [3/5] Virtual environment aktif ediliyor...
call .venv\Scripts\activate.bat

echo.
echo [4/5] Paketler yukleniyor (bu biraz zaman alabilir)...
python -m pip install --upgrade pip
if exist "requirements-dev.txt" (
    python -m pip install -r requirements-dev.txt
) else (
    python -m pip install -r requirements.txt
)

echo.
echo [5/5] Dizinler olusturuluyor...
if not exist "database" mkdir database
if not exist "logs" mkdir logs
if not exist "backup" mkdir backup
if not exist "config" mkdir config
if not exist "modules" mkdir modules
if not exist "temp" mkdir temp

echo.
echo ==========================================
echo  ✓ KURULUM TAMAMLANDI!
echo ==========================================
echo.
echo Simdi su komutu calistirabilirsiniz:
echo   python app.py
echo.
pause
