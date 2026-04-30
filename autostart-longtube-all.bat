@echo off
setlocal EnableExtensions
chcp 65001 >nul

title LongTube AutoStart
cd /d "%~dp0"

set "LOG_DIR=%~dp0data\logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
set "LOG_FILE=%LOG_DIR%\autostart-longtube-all.log"

echo.>>"%LOG_FILE%"
echo ==================================================>>"%LOG_FILE%"
echo [%date% %time%] LongTube AutoStart begin>>"%LOG_FILE%"
echo Root: %~dp0>>"%LOG_FILE%"

echo [1/2] Starting ComfyUI LAN server...
echo [%date% %time%] Starting ComfyUI LAN server>>"%LOG_FILE%"
start "ComfyUI-LAN-8188" cmd /k ""%~dp0start-comfyui-lan.bat""

echo [2/2] Starting LongTube backend/frontend...
echo [%date% %time%] Waiting 10s before LongTube start>>"%LOG_FILE%"
timeout /t 10 /nobreak >nul
echo [%date% %time%] Starting LongTube start.bat>>"%LOG_FILE%"
start "LongTube-Start" cmd /k ""%~dp0start.bat""

echo [%date% %time%] LongTube AutoStart launched child windows>>"%LOG_FILE%"
echo.
echo LongTube auto-start launched:
echo   - ComfyUI:  http://localhost:8188/
echo   - Frontend: http://localhost:3000/
echo   - Backend:  http://localhost:8000/api/health
echo.
timeout /t 3 /nobreak >nul
exit /b 0
