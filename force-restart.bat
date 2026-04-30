@echo off
setlocal EnableExtensions EnableDelayedExpansion
title LongTube-ForceRestart-%RANDOM%%RANDOM%
color 0E
echo.
echo ====================================
echo   LongTube Force Restart
echo ====================================
echo.

:: ========================================================================
:: CRITICAL: the PowerShell child's $PID is PowerShell itself, NOT the
:: cmd.exe running this .bat script. If we don't also exclude the parent
:: cmd.exe, PowerShell will kill the very cmd that's running us, and the
:: script dies mid-execution. So we compute the parent (cmd.exe) PID
:: inside PowerShell and exclude BOTH.
:: ========================================================================

echo [1/5] Killing LongTube backend (uvicorn python.exe)...
powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |" ^
  "  Where-Object { $_.CommandLine -like '*uvicorn*app.main:app*' } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('       killed python PID ' + $_.ProcessId) } catch {} }"
echo.

echo [1.5/5] Killing LongTube backend wrapper windows (powershell.exe)...
powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "$grandparent = 0; try { $grandparent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $parent)).ParentProcessId } catch {};" ^
  "$root = [IO.Path]::GetFullPath('%~dp0').TrimEnd('\');" ^
  "Get-CimInstance Win32_Process -Filter \"Name='powershell.exe'\" |" ^
  "  Where-Object { $_.CommandLine -and $_.CommandLine -like ('*' + $root + '*backend*uvicorn*app.main:app*') } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent -and $_.ProcessId -ne $grandparent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('       killed powershell PID ' + $_.ProcessId) } catch {} }"
echo.

echo [2/5] Killing LongTube frontend (node.exe next dev)...
powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" |" ^
  "  Where-Object { $_.CommandLine -like '*next*dev*' } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('       killed node PID ' + $_.ProcessId) } catch {} }"
echo.

echo [3/5] Killing cmd.exe wrapper windows (excluding this script's own cmd)...
powershell -NoProfile -Command ^
  "$me = $PID;" ^
  "$parent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $me)).ParentProcessId;" ^
  "$grandparent = 0; try { $grandparent = (Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $parent)).ParentProcessId } catch {};" ^
  "Get-CimInstance Win32_Process -Filter \"Name='cmd.exe'\" |" ^
  "  Where-Object { $_.CommandLine -and ($_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*next*dev*' -or $_.CommandLine -like '*start.bat*' -or $_.CommandLine -like '*force-restart.bat*') } |" ^
  "  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent -and $_.ProcessId -ne $grandparent } |" ^
  "  ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('       killed cmd PID ' + $_.ProcessId) } catch {} }"
echo.

:: Port-based fallback
echo [4/5] Killing anything on port 8000/3000 (fallback)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo       port 8000 PID %%a
    taskkill /f /pid %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
    echo       port 3000 PID %%a
    taskkill /f /pid %%a >nul 2>&1
)

timeout /t 3 /nobreak >nul

:: Verify
set STILL_BUSY=0
netstat -ano | findstr :8000 | findstr LISTENING >nul
if %errorlevel% equ 0 set STILL_BUSY=1
netstat -ano | findstr :3000 | findstr LISTENING >nul
if %errorlevel% equ 0 set STILL_BUSY=1

if %STILL_BUSY% equ 1 (
    echo.
    echo [WARN] A port is still busy. Retrying with port-owner kill only.
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
        echo       retry port 8000 PID %%a
        taskkill /f /pid %%a >nul 2>&1
    )
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :3000 ^| findstr LISTENING') do (
        echo       retry port 3000 PID %%a
        taskkill /f /pid %%a >nul 2>&1
    )
    timeout /t 2 /nobreak >nul
    netstat -ano | findstr :8000 | findstr LISTENING >nul
    if %errorlevel% equ 0 (
        echo [ERROR] Port 8000 STILL busy.
        pause
        exit /b 1
    )
    netstat -ano | findstr :3000 | findstr LISTENING >nul
    if %errorlevel% equ 0 (
        echo [ERROR] Port 3000 STILL busy.
        pause
        exit /b 1
    )
)
echo       Ports are free.
echo.

:: ========== Step 5: Start LongTube directly ==========
echo [5/5] Starting LongTube...
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js not found.
    pause
    exit /b 1
)

cd /d %~dp0frontend
if not exist "node_modules\next\dist\bin\next" (
    echo [INFO] Frontend packages missing. Running npm install...
    if exist node_modules rmdir /s /q node_modules
    if exist .next rmdir /s /q .next
    if exist .next-dev rmdir /s /q .next-dev
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] npm install failed.
        pause
        exit /b 1
    )
)
cd /d %~dp0

echo       Starting Redis (optional)...
docker start longtube-redis 2>nul || docker run -d --name longtube-redis -p 6379:6379 redis:alpine 2>nul

echo       Starting Backend window...
start "LongTube-Backend" cmd /k "cd /d %~dp0backend && set WATCHFILES_FORCE_POLLING=true && set WATCHFILES_POLL_DELAY_MS=300 && (python -m pip install -r requirements.txt -q || (echo [ERROR] pip install failed ^& pause ^& exit /b 1)) && (python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app --reload-dir workflows --reload-dir scripts || (echo [ERROR] uvicorn terminated ^& pause))"

echo       Starting Frontend window...
start "LongTube-Frontend" cmd /k "cd /d %~dp0frontend && set WATCHPACK_POLLING=true && set CHOKIDAR_USEPOLLING=1 && (node node_modules\next\dist\bin\next dev --hostname 0.0.0.0 --port 3000 || (echo [ERROR] next dev terminated ^& pause))"

echo.
echo Waiting for backend/frontend to respond...
set BACKEND_OK=0
set FRONTEND_OK=0
for /l %%i in (1,1,20) do (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set BACKEND_OK=1
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:3000/' -UseBasicParsing -TimeoutSec 1; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set FRONTEND_OK=1
    if "!BACKEND_OK!"=="1" if "!FRONTEND_OK!"=="1" goto :servers_ready
    timeout /t 1 /nobreak >nul
)

:servers_ready
echo.
if "%BACKEND_OK%"=="1" (
    echo [OK] Backend responded on 8000
) else (
    echo [WARN] Backend did not respond yet on 8000
)
if "%FRONTEND_OK%"=="1" (
    echo [OK] Frontend responded on 3000
) else (
    echo [WARN] Frontend did not respond yet on 3000
)

start http://localhost:3000/
echo.
echo ====================================
echo  LongTube force restart complete
echo ====================================
echo.
if "%BACKEND_OK%"=="1" if "%FRONTEND_OK%"=="1" exit /b 0
echo [INFO] One of the servers is still starting or failed. Check the opened Backend/Frontend windows.
pause
