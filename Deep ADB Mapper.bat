@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Ascend Maximum-Depth ADB Mapper
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "TV_HOST=%ASCEND_TV_HOST%"
if not defined TV_HOST set /p "TV_HOST=Android TV IP: "
set "AUTO_DEEP=0"
if /i "%~1"=="/deep" set "AUTO_DEEP=1"
set "VENV_PY=venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Local Python environment is missing. Running setup...
    call setup_env.bat
    if errorlevel 1 exit /b 1
)

:menu
cls
echo ================================================================
echo          ASCEND MAXIMUM-DEPTH ANDROID TV ADB MAPPER
echo                    Target: %TV_HOST%:5555
echo ================================================================
echo.
echo [1] MAXIMUM MAP - every dumpsys service + every package + continuous UI
echo [2] Full curated device map + continuous changed-screen UI capture
echo [3] Current screen/UI/text/click map only
echo [4] Watch and capture every changed screen for 2 minutes
echo [5] DPAD focus-navigation map ^(direction keys only, no ENTER^)
echo [6] Interactive click/key explorer ^(every action asks confirmation^)
echo [7] Change target IP
echo [8] Exit
echo.
if "%AUTO_DEEP%"=="1" (
    set "MAP_OPTION=1"
    set "MAP_MODE=maximum"
    set "STOP_FLAG=--until-stopped"
    set "PRIVATE_CHOICE=YES"
    goto configured
)
set "MAP_OPTION="
set /p "MAP_OPTION=Choose: "
if errorlevel 1 exit /b 0

if "%MAP_OPTION%"=="7" (
    set /p "TV_HOST=Android TV IP: "
    goto menu
)
if "%MAP_OPTION%"=="8" exit /b 0

set "MAP_MODE="
set "STOP_FLAG="
if "%MAP_OPTION%"=="1" set "MAP_MODE=maximum"
if "%MAP_OPTION%"=="2" set "MAP_MODE=full"
if "%MAP_OPTION%"=="3" set "MAP_MODE=screen"
if "%MAP_OPTION%"=="4" set "MAP_MODE=watch"
if "%MAP_OPTION%"=="5" set "MAP_MODE=focus"
if "%MAP_OPTION%"=="6" set "MAP_MODE=interactive"
if not defined MAP_MODE goto menu
if "%MAP_OPTION%"=="1" set "STOP_FLAG=--until-stopped"
if "%MAP_OPTION%"=="2" set "STOP_FLAG=--until-stopped"
if "%MAP_OPTION%"=="4" set "STOP_FLAG=--until-stopped"

echo.
echo Sensitive data can include notifications, account names, Wi-Fi details,
echo app usage, settings, logs, and URLs. It stays inside the local adb_maps folder.
echo APK files are NEVER downloaded or copied by this mapper.
set /p "PRIVATE_CHOICE=Include sensitive diagnostics? Type YES to include: "
if "%AUTO_DEEP%"=="1" set "PRIVATE_CHOICE=YES"

:configured
set "PRIVATE_FLAG="
if "!PRIVATE_CHOICE!"=="YES" set "PRIVATE_FLAG=--include-sensitive"

echo.
echo Starting !MAP_MODE! mapper. Keep this window open.
echo Maximum mode can take a long time and create a very large folder.
echo Press Ctrl+C to stop safely and keep everything already captured.
echo.
"%VENV_PY%" tools\adb_deep_mapper.py !MAP_MODE! --host "%TV_HOST%" --interval 0.10 --frame-interval 0.50 !PRIVATE_FLAG! !STOP_FLAG!
set "MAP_EXIT=!errorlevel!"
echo.
if "!MAP_EXIT!"=="0" (
    echo Mapping finished successfully. Results are under:
    echo %CD%\adb_maps
) else (
    echo Mapper exited with code !MAP_EXIT!.
)
if "%AUTO_DEEP%"=="1" exit /b !MAP_EXIT!
pause
goto menu
