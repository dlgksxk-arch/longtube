@echo off
title LongTube-Launcher-%RANDOM%%RANDOM%
color 0A
echo.
echo ====================================
echo   LongTube - Video Automation
echo ====================================
echo.

:: ========================================================================
:: Cleanup previous LongTube processes.
:: CRITICAL: $PID in PowerShell is the PowerShell child, NOT this cmd.exe.
:: We must also exclude the parent (cmd.exe running this bat) and the
:: grandparent (the cmd.exe that may have called us via force-restart.bat),
:: otherwise PowerShell will kill the very cmd that runs this script.
:: ========================================================================
echo [0] Cleaning up previous LongTube processes...

powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |" ^
  "  Where-Object { $_.CommandLine -like '*uvicorn*app.main:app*' } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('     killed python PID ' + $_.ProcessId) } catch {} }"

powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" |" ^
  "  Where-Object { $_.CommandLine -like '*next*dev*' } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('     killed node PID ' + $_.ProcessId) } catch {} }"

powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "$grandparent = 0; try { $grandparent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $parent)).ParentProcessId } catch {};" ^
  "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" |" ^
  "  Where-Object { $_.CommandLine -and ($_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*next*dev*' -or $_.CommandLine -like '*start.bat*' -or $_.CommandLine -like '*force-restart.bat*') } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent -and $_.ProcessId -ne $grandparent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('     killed cmd PID ' + $_.ProcessId) } catch {} }"

:: Port fallback
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo     killing PID %%a on port 8000...
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    echo     killing PID %%a on port 3000...
    taskkill /f /pid %%a >nul 2>&1
)

timeout /t 2 /nobreak >nul

netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% equ 0 (
    echo [WARN] Port 8000 still busy. Falling back to broad python.exe kill...
    taskkill /f /im python.exe >nul 2>&1
    timeout /t 1 /nobreak >nul
)
echo     Done.
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)
echo [OK] Python found

:: Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found!
    pause
    exit /b 1
)
echo [OK] Node.js found
echo.

:: Fix frontend node_modules if broken
cd /d %~dp0frontend
if not exist "node_modules\next\dist\bin\next" (
    echo [!] Frontend packages missing or broken. Fixing...
    echo     Deleting old node_modules...
    if exist node_modules rmdir /s /q node_modules
    if exist .next rmdir /s /q .next
    timeout /t 2 /nobreak >nul
    echo     Installing packages...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed! Try right-click start.bat - Run as Administrator
        pause
        exit /b 1
    )
    echo     [OK] Packages installed!
    echo.
)
cd /d %~dp0

:: Redis (Docker) - optional
echo [1/3] Starting Redis...
docker start longtube-redis 2>nul || docker run -d --name longtube-redis -p 6379:6379 redis:alpine 2>nul
if %errorlevel% neq 0 (
    echo        Redis not available - continuing without it
) else (
    echo        Redis OK
)
echo.

:: Backend
echo [2/3] Starting Backend server...
start /min "LongTube-Backend" cmd /k "cd /d %~dp0backend && python -m pip install -r requirements.txt -q && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-include *.env"
echo        Backend starting on port 8000
echo.

:: Frontend
echo [3/3] Starting Frontend server...
start /min "LongTube-Frontend" cmd /k "cd /d %~dp0frontend && node node_modules\next\dist\bin\next dev --port 3000"
echo        Frontend starting on port 3000
echo.

echo ====================================
echo  Waiting for servers to start... (15s)
echo ====================================
timeout /t 15 /nobreak >nul

:: Open browser
start http://localhost:3000

echo.
echo ====================================
echo  LongTube is running!
echo  Open http://localhost:3000
echo ====================================
echo.

title LongTube Server
pause
