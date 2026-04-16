@echo off
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
    echo [WARN] A port is still busy. Falling back to broad python.exe + node.exe kill.
    taskkill /f /im python.exe 2>nul
    taskkill /f /im node.exe   2>nul
    timeout /t 2 /nobreak >nul
    netstat -ano | findstr :8000 | findstr LISTENING >nul
    if %errorlevel% equ 0 (
        echo [ERROR] Port 8000 STILL busy. Open Task Manager and kill all python.exe manually.
        pause
        exit /b 1
    )
)
echo       Ports are free.
echo.

:: ========== Step 5: Launch start.bat ==========
echo [5/5] Launching start.bat...
echo.
call "%~dp0start.bat"
