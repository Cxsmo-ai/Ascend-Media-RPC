@echo off
setlocal EnableDelayedExpansion
title Deepbrid Torrent Link Generator
cd /d "%~dp0"

:main
cls
echo ==========================================
echo       Deepbrid Torrent Link Generator
echo ==========================================
echo.

if "%DEEPBRID_API_KEY%"=="" (
    set /p DEEPBRID_API_KEY="Enter your Deepbrid API Key: "
)

if "%DEEPBRID_API_KEY%"=="" goto main

echo.
echo [1] List Finished Torrents/Downloads
echo [2] List Active Torrents
echo [3] Add Magnet Link
echo [4] Change API Key
echo [5] Exit
echo.
set /p opt="Select an option: "

if "%opt%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "deepbrid_tool.ps1" -ApiKey "!DEEPBRID_API_KEY!" -Action "list_downloads"
    pause
    goto main
)
if "%opt%"=="2" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "deepbrid_tool.ps1" -ApiKey "!DEEPBRID_API_KEY!" -Action "list_torrents"
    pause
    goto main
)
if "%opt%"=="3" (
    echo.
    set /p MAG="Enter Magnet Link: "
    if "!MAG!"=="" goto main
    powershell -NoProfile -ExecutionPolicy Bypass -File "deepbrid_tool.ps1" -ApiKey "!DEEPBRID_API_KEY!" -Action "add_magnet" -Magnet "!MAG!"
    pause
    goto main
)
if "%opt%"=="4" (
    set "DEEPBRID_API_KEY="
    goto main
)
if "%opt%"=="5" exit /b 0
goto main
