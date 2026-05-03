@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%watchdog-longtube.ps1"
set "HIDDEN=%ROOT%run-watchdog-hidden.vbs"
set "TASK_MIN=LongTube Watchdog"
set "TASK_LOGON=LongTube Watchdog Logon"

if not exist "%SCRIPT%" (
  echo [ERROR] watchdog script not found: %SCRIPT%
  exit /b 1
)
if not exist "%HIDDEN%" (
  echo [ERROR] hidden watchdog launcher not found: %HIDDEN%
  exit /b 1
)

echo Installing LongTube watchdog scheduled tasks...
schtasks /Create /F /TN "%TASK_MIN%" /SC MINUTE /MO 1 /TR "wscript.exe \"%HIDDEN%\"" >nul
if errorlevel 1 (
  echo [ERROR] Failed to create minute watchdog task.
  exit /b 1
)

schtasks /Create /F /TN "%TASK_LOGON%" /SC ONLOGON /TR "wscript.exe \"%HIDDEN%\"" >nul
if errorlevel 1 (
  echo [WARN] Failed to create logon watchdog task. Minute watchdog is installed.
) else (
  echo [OK] Logon watchdog installed.
)

echo Running watchdog once now...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"

echo [OK] LongTube watchdog installed.
echo   - Checks backend  : http://localhost:8000/api/health
echo   - Checks frontend : http://localhost:3000/
echo   - Checks ComfyUI  : http://localhost:8188/
exit /b 0
