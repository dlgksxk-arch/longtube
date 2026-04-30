@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "TASK_NAME=LongTube AutoStart"

echo.
echo ======================================
echo   Uninstall LongTube Windows AutoStart
echo ======================================
echo.

schtasks /Delete /TN "%TASK_NAME%" /F
if %errorlevel% neq 0 (
  echo.
  echo [WARN] Scheduled task was not found or could not be deleted.
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$lnk=Join-Path ([Environment]::GetFolderPath('Startup')) 'LongTube AutoStart.lnk';" ^
  "if (Test-Path $lnk) { Remove-Item -LiteralPath $lnk -Force; Write-Host ('[OK] Startup shortcut removed: ' + $lnk) } else { Write-Host '[INFO] Startup shortcut not found.' }"

echo.
echo [OK] Auto-start uninstall finished.
echo.
pause
