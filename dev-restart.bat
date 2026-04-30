@echo off
chcp 65001 >nul
setlocal

echo.
echo =========================================
echo   LongTube dev 서버 재시작 (v1.2.12)
echo =========================================
echo.

cd /d "%~dp0frontend"

echo [1/3] 혹시 켜져있는 dev 서버 종료...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":3000 " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
echo       완료.
echo.

echo [2/3] .next 캐시 폴더 삭제...
if exist .next (
  rmdir /s /q .next
  echo       완료.
) else (
  echo       이미 없음.
)
echo.

echo [3/3] dev 서버 시작 (잠시 걸립니다)...
echo.
echo       브라우저에서 http://localhost:3000 을 여세요.
echo       같은 네트워크의 다른 PC에서는 http://이_PC_IP:3000 으로 접속하세요.
echo       이 창을 닫지 마세요. 멈추려면 Ctrl+C.
echo.
echo =========================================
echo.

set WATCHPACK_POLLING=true
set CHOKIDAR_USEPOLLING=1
call npm run dev

echo.
echo dev 서버가 종료되었습니다.
pause
