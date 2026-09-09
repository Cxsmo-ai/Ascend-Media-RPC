@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo   Stremio RPC - Portable Environment Setup
echo ==========================================

set "PYTHON_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD goto :no_python

if /i "%~1"=="/rebuild" (
    if exist "venv" (
        echo [INFO] Removing broken portable virtual environment...
        rmdir /s /q "venv"
        if exist "venv" goto :venv_fail
    )
)

if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating local virtual environment...
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 goto :venv_fail
    echo [SUCCESS] Virtual environment created.
)

echo [INFO] Updating pip and installing dependencies...

"venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check -q > setup.log 2>&1
if errorlevel 1 (
    echo [ERROR] Pip update failed. Check setup.log
    pause
    exit /b 1
)

"venv\Scripts\python.exe" -m pip install -r requirements.txt --disable-pip-version-check -q >> setup.log 2>&1
if errorlevel 1 (
    echo [ERROR] Dependency install failed. Check setup.log
    pause
    exit /b 1
)

echo.
echo [SUCCESS] Portable environment is ready.
echo You can now use run.bat.
echo.
exit /b 0

:no_python
echo [ERROR] Python is not installed or not in PATH.
echo Please install 64-bit Python 3.10+ from python.org and run setup_env.bat again.
pause
exit /b 1

:venv_fail
echo [ERROR] Failed to create virtual environment.
pause
exit /b 1

:install_fail
echo [ERROR] Failed to install dependencies.
pause
exit /b 1
