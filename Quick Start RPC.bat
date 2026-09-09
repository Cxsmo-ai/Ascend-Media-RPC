@echo off
setlocal EnableExtensions
cd /d "%~dp0"

title Ascend Media RPC
rem Optional: set ASCEND_TV_HOST before launching, or configure adb_host in config.json.
set "ASCEND_TV_HOST=%ASCEND_TV_HOST%"
set "ASCEND_NO_PAUSE=1"

echo Starting Ascend Media RPC for Android TV %ASCEND_TV_HOST%...
echo Keep this window open while watching.
echo.

call run.bat --host "%ASCEND_TV_HOST%"
set "ASCEND_EXIT=%errorlevel%"

if not "%ASCEND_EXIT%"=="0" (
    echo.
    echo Ascend stopped with error code %ASCEND_EXIT%.
    echo Check stremio_debug.log for details.
    pause
)
exit /b %ASCEND_EXIT%
