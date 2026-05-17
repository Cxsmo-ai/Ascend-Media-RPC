@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if not errorlevel 1 (
    py -3 vencord_installer_gui.py
    goto :done
)

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python 3.10+ and rerun this file.
    pause
    exit /b 1
)

python vencord_installer_gui.py

:done
if errorlevel 1 pause
