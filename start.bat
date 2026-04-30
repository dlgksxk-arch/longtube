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
  "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |" ^
  "  Where-Object { $_.CommandLine -like '*spawn_main*' } |" ^
  "  ForEach-Object {" ^
  "    $pp = Get-CimInstance Win32_Process -Filter (\"ProcessId=\" + $_.ParentProcessId) -ErrorAction SilentlyContinue;" ^
  "    $pcmd = if ($pp) { $pp.CommandLine } else { '' };" ^
  "    if ((-not $pp) -or ($pcmd -like '*uvicorn*app.main:app*') -or ($pcmd -like '*LongTube-Backend*') -or ($pcmd -like '*start.bat*')) {" ^
  "      try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('     killed orphan backend child PID ' + $_.ProcessId) } catch {}" ^
  "    }" ^
  "  }"

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
set "NODE_EXE=node"
set "NPM_CMD=npm"
set "LOCAL_NODE_DIR=%LOCALAPPDATA%\LongTubeTools\node-v22.22.2-win-x64"
if exist "%LOCAL_NODE_DIR%\node.exe" (
    set "NODE_EXE=%LOCAL_NODE_DIR%\node.exe"
)
if exist "%LOCAL_NODE_DIR%\npm.cmd" (
    set "NPM_CMD=%LOCAL_NODE_DIR%\npm.cmd"
)
"%NODE_EXE%" --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist "%LOCAL_NODE_DIR%\node.exe" (
        set "NODE_EXE=%LOCAL_NODE_DIR%\node.exe"
        set "NPM_CMD=%LOCAL_NODE_DIR%\npm.cmd"
    ) else if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" (
        set "NODE_EXE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
    ) else if exist "C:\Program Files\nodejs\node.exe" (
        set "NODE_EXE=C:\Program Files\nodejs\node.exe"
        if exist "C:\Program Files\nodejs\npm.cmd" set "NPM_CMD=C:\Program Files\nodejs\npm.cmd"
    ) else (
        echo [ERROR] Node.js not found or cannot be executed!
        pause
        exit /b 1
    )
)
echo [OK] Node.js found: %NODE_EXE%
echo.

:: Fix frontend node_modules if broken
cd /d %~dp0frontend
if not exist "node_modules\next\dist\bin\next" (
    echo [!] Frontend packages missing or broken. Fixing...
    echo     Deleting old node_modules...
    if exist node_modules rmdir /s /q node_modules
    if exist .next rmdir /s /q .next
    if exist .next-dev rmdir /s /q .next-dev
    timeout /t 2 /nobreak >nul
    echo     Installing packages...
    call "%NPM_CMD%" install
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
:: v2.1.0: /min 제거 — pip/uvicorn 실패 시 창이 숨겨져 원인 파악이 안되던 문제
::         해결. 실패하면 `pause` 로 창이 닫히지 않고 에러를 보여준다.
:: v2.1.1: 파일 감시를 polling 으로 강제 — Codex/외부 툴 편집 시에도
::         Windows 에서 reload 이벤트를 놓치지 않게 한다.
echo [2/3] Starting Backend server...
start "LongTube-Backend" cmd /k "cd /d %~dp0backend && set WATCHFILES_FORCE_POLLING=true && set WATCHFILES_POLL_DELAY_MS=300 && (python -m pip install -r requirements.txt -q || (echo [ERROR] pip install failed ^& pause ^& exit /b 1)) && (python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app --reload-dir workflows --reload-dir scripts || (echo [ERROR] uvicorn terminated ^& pause))"
echo        Backend starting on port 8000
echo.

:: Frontend
:: v2.1.0: /min 제거 — next dev 가 조용히 죽어도 창이 남아 메시지를 볼 수 있게.
:: v2.1.1: polling 감시 강제 — TS/TSX/CSS 변경을 외부 편집에서도 즉시 반영.
echo [3/3] Starting Frontend server...
start "LongTube-Frontend" cmd /k "cd /d %~dp0frontend && set WATCHPACK_POLLING=true && set CHOKIDAR_USEPOLLING=1 && (%NODE_EXE% node_modules\next\dist\bin\next dev --hostname 0.0.0.0 --port 3000 || (echo [ERROR] next dev terminated ^& pause))"
echo        Frontend starting on port 3000
echo.

echo ====================================
echo  Waiting for servers to start... (15s)
echo ====================================
timeout /t 15 /nobreak >nul

:: v1.2.1: v2 는 폐기. v1 메인 대시보드(/) 로 바로 진입.
start http://localhost:3000/

echo.
echo ====================================
echo  LongTube is running!
echo  Open http://localhost:3000/
echo ====================================
echo.

title LongTube Server
pause
