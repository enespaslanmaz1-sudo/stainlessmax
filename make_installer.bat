@echo off
mkdir "dist\installer" 2>nul
"D:\Program Files\Inno Setup 6\ISCC.exe" installer.iss
if %ERRORLEVEL% equ 0 (
    echo INSTALLER OK
) else (
    echo INSTALLER FAILED
)
