@echo off
setlocal enabledelayedexpansion

set "IMAGE_NAME=ascend-media-rpc:local"
if "%DASHBOARD_PORT%"=="" set "DASHBOARD_PORT=5466"

echo ==========================================
echo   Ascend Media RPC - Docker Build
echo ==========================================
echo.

docker --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker was not found on PATH. Install Docker Desktop first.
    pause
    exit /b 1
)

if not exist data mkdir data
if not exist rpc_artwork_cache mkdir rpc_artwork_cache
if not exist config.json (
    echo {}> config.json
    echo [INFO] Created config.json placeholder. The app will merge defaults on first run.
)

echo [INFO] Building %IMAGE_NAME%...
docker build -t "%IMAGE_NAME%" .
if errorlevel 1 (
    echo [ERROR] Docker build failed.
    pause
    exit /b 1
)

if /I "%~1"=="run" goto run_container
if /I "%~1"=="up" goto compose_up

echo.
echo [DONE] Docker image built: %IMAGE_NAME%
echo.
echo Run options:
echo   docker_build.bat run     Build and run with docker run
echo   docker_build.bat up      Build and start with docker compose
echo.
pause
exit /b 0

:run_container
echo [INFO] Starting container on host network...
docker rm -f ascend-rpc >nul 2>&1
docker run -d ^
  --name ascend-rpc ^
  --network host ^
  --restart unless-stopped ^
  -e ASCEND_PORT=%DASHBOARD_PORT% ^
  -e ADB_HOST=%ADB_HOST% ^
  -v "%CD%\config.json:/app/config.json" ^
  -v "%CD%\data:/app/data" ^
  -v "%CD%\rpc_artwork_cache:/app/rpc_artwork_cache" ^
  "%IMAGE_NAME%"
if errorlevel 1 (
    echo [ERROR] Docker run failed.
    pause
    exit /b 1
)
echo [DONE] Dashboard: http://localhost:%DASHBOARD_PORT%
pause
exit /b 0

:compose_up
echo [INFO] Starting with docker compose...
set "ASCEND_IMAGE=%IMAGE_NAME%"
docker compose up -d --build
if errorlevel 1 (
    echo [ERROR] docker compose up failed.
    pause
    exit /b 1
)
echo [DONE] Dashboard: http://localhost:%DASHBOARD_PORT%
pause
