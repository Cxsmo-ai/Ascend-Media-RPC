@echo off
setlocal
cd /d "%~dp0"

echo ==================================================
echo  Ascend Vencord Installer
echo ==================================================
echo.
echo.
echo Canary-only setup has been replaced by the GUI installer.
echo The GUI supports Discord Stable, PTB, Canary, Development,
echo and custom Discord install folders.
echo.

call "%~dp0launch_installer.bat"
