@echo off
title LongTube - Fix Frontend
color 0E
echo.
echo ====================================
echo   Fixing Frontend (node_modules)
echo ====================================
echo.
echo [1] Closing any running Node processes...
taskkill /f /im node.exe 2>nul
timeout /t 2 /nobreak >nul
echo.
echo [2] Deleting old node_modules...
cd /d %~dp0frontend
if exist node_modules (
    rmdir /s /q node_modules
    echo     Deleted!
) else (
    echo     Already clean.
)
echo.
echo [3] Deleting Next cache...
if exist .next (
    rmdir /s /q .next
    echo     Deleted!
)
if exist .next-dev (
    rmdir /s /q .next-dev
    echo     Deleted .next-dev!
)
echo.
echo [4] Running npm install...
call npm install
echo.
if %errorlevel% neq 0 (
    echo [ERROR] npm install failed!
    echo Try running as Administrator.
    pause
    exit /b 1
)
echo ====================================
echo   Done! Now run start.bat
echo ====================================
pause
