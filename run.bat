@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if "%GUI_MODE%"=="" set "GUI_MODE=browser"
echo Starting Stremio RPC Controller (Mode: %GUI_MODE%)...

set "VENV_PY=venv\Scripts\python.exe"
call :validate_venv
if errorlevel 1 (
    echo [INFO] Local virtual environment is missing or not runnable. Rebuilding...
    call setup_env.bat /rebuild
    if errorlevel 1 (
        echo [ERROR] Setup failed. Cannot start application.
        pause
        exit /b 1
    )
)

"%VENV_PY%" start_gui.py
if errorlevel 1 (
    echo.
    echo Application crashed or closed with an error.
    pause
)
exit /b 0

:validate_venv
if not exist "%VENV_PY%" exit /b 1
if not exist "venv\pyvenv.cfg" exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='venv\Scripts\python.exe'; if (!(Test-Path $p)) { exit 1 }; $b=[IO.File]::ReadAllBytes($p); if ($b.Length -lt 512 -or $b[0] -ne 0x4d -or $b[1] -ne 0x5a) { exit 2 }; $o=[BitConverter]::ToInt32($b,0x3c); if ($o -lt 0 -or ($o+6) -ge $b.Length) { exit 3 }; if ($b[$o] -ne 0x50 -or $b[$o+1] -ne 0x45 -or $b[$o+2] -ne 0 -or $b[$o+3] -ne 0) { exit 4 }; $m=[BitConverter]::ToUInt16($b,$o+4); if ($m -ne 0x8664 -and $m -ne 0x14c) { exit 5 }; exit 0"
exit /b %errorlevel%
