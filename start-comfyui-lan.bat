@echo off
setlocal EnableExtensions
title ComfyUI-LAN-8188
color 0B

set "COMFY_ROOT=%LOCALAPPDATA%\Programs\ComfyUI\resources\ComfyUI"
set "COMFY_DATA=%APPDATA%\ComfyUI-Data"
set "COMFY_PY=%COMFY_DATA%\.venv\Scripts\python.exe"
set "COMFY_FRONTEND=%LOCALAPPDATA%\Programs\ComfyUI\resources\ComfyUI\web_custom_versions\desktop_app"
set "COMFY_DB=%APPDATA:\=/%/ComfyUI-Data/user/comfyui.db"
set "LOG_DIR=%~dp0data\logs"
set "LOG_FILE=%LOG_DIR%\comfyui-lan.log"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

echo.
echo ====================================
echo   ComfyUI LAN server - port 8188
echo ====================================
echo.
echo [%date% %time%] ComfyUI LAN start requested>>"%LOG_FILE%"

if not exist "%COMFY_ROOT%\main.py" (
  echo [ERROR] ComfyUI main.py not found: %COMFY_ROOT%\main.py
  echo [%date% %time%] ERROR main.py not found: %COMFY_ROOT%\main.py>>"%LOG_FILE%"
  pause
  exit /b 1
)

if not exist "%COMFY_PY%" (
  echo [ERROR] ComfyUI python not found: %COMFY_PY%
  echo [%date% %time%] ERROR python not found: %COMFY_PY%>>"%LOG_FILE%"
  pause
  exit /b 1
)

echo [1/2] Stopping old ComfyUI desktop/server...
echo [%date% %time%] stopping old ComfyUI processes>>"%LOG_FILE%"
taskkill /f /im ComfyUI.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8188 " ^| findstr LISTENING') do (
  echo       killing PID %%a on port 8188
  echo [%date% %time%] killing PID %%a on port 8188>>"%LOG_FILE%"
  taskkill /f /pid %%a >nul 2>&1
)
powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter ('ProcessId=' + $me)).ParentProcessId;" ^
  "Get-CimInstance Win32_Process |" ^
  "  Where-Object { $_.CommandLine -and $_.CommandLine -match 'main.py.*--port 8188' } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('       killed ComfyUI python PID ' + $_.ProcessId) } catch {} }"
timeout /t 2 /nobreak >nul

echo [2/2] Starting ComfyUI on 0.0.0.0:8188 ...
echo       Local:   http://localhost:8188/
echo       LAN:     http://192.168.0.221:8188/
echo       Log:     %LOG_FILE%
echo       DB:      %COMFY_DB%
echo.
echo [%date% %time%] launching ComfyUI python>>"%LOG_FILE%"

cd /d "%COMFY_ROOT%"
"%COMFY_PY%" main.py --windows-standalone-build --disable-auto-launch --listen 0.0.0.0 --port 8188 --base-directory C:\ --user-directory "%COMFY_DATA%\user" --database-url "sqlite:///%COMFY_DB%" --front-end-root "%COMFY_FRONTEND%" >>"%LOG_FILE%" 2>>&1

echo.
echo ComfyUI LAN server stopped.
echo [%date% %time%] ComfyUI LAN server stopped, exitcode=%ERRORLEVEL%>>"%LOG_FILE%"
pause
