@echo off
setlocal EnableExtensions
chcp 65001 >nul

cd /d "%~dp0"

set "TASK_NAME=LongTube AutoStart"
set "TARGET=%~dp0autostart-longtube-all.bat"
set "ACTION=cmd.exe /c ""%TARGET%"""

if not exist "%TARGET%" (
  echo [ERROR] Missing target script:
  echo         %TARGET%
  pause
  exit /b 1
)

echo.
echo ====================================
echo   Install LongTube Windows AutoStart
echo ====================================
echo.
echo Task name: %TASK_NAME%
echo Target:    %TARGET%
echo.
echo This registers a per-user Windows Task Scheduler job.
echo If Task Scheduler is blocked by Windows policy, it falls back to
echo the current user's Startup folder.
echo.

schtasks /Create /TN "%TASK_NAME%" /TR "%ACTION%" /SC ONLOGON /DELAY 0001:00 /RL LIMITED /F
if %errorlevel% neq 0 (
  echo.
  echo [WARN] Task Scheduler registration failed. Falling back to Startup shortcut...
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$startup=[Environment]::GetFolderPath('Startup');" ^
    "$lnk=Join-Path $startup 'LongTube AutoStart.lnk';" ^
    "$w=New-Object -ComObject WScript.Shell;" ^
    "$s=$w.CreateShortcut($lnk);" ^
    "$s.TargetPath='cmd.exe';" ^
    "$s.Arguments='/c ""%TARGET%""';" ^
    "$s.WorkingDirectory='%~dp0';" ^
    "$s.IconLocation='%SystemRoot%\System32\shell32.dll,220';" ^
    "$s.Description='Start ComfyUI, LongTube backend, and LongTube frontend at logon.';" ^
    "$s.Save();" ^
    "Write-Host ('[OK] Startup shortcut installed: ' + $lnk)"
  if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Failed to create Startup shortcut.
    pause
    exit /b 1
  )
  echo.
  pause
  exit /b 0
)

echo.
echo [OK] Auto-start task installed.
echo.
schtasks /Query /TN "%TASK_NAME%" /FO LIST
echo.
pause
