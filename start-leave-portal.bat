@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\uvicorn.exe" (
  echo 仮想環境が見つかりません。install-server.bat を先に実行してください。
  pause
  exit /b 1
)

set "PORT=8004"
netstat -ano | findstr /R /C:":8004 .*LISTENING" >nul
if not errorlevel 1 (
  echo [警告] ポート 8004 が使用中のため 8005 で起動します。
  set "PORT=8005"
)

echo Starting leave portal at http://127.0.0.1:%PORT%/
echo 管理者用アプリとは別ポートです。同じ shift.db を共有します。
echo 停止するには Ctrl+C を押してください。
echo.
.\.venv\Scripts\uvicorn.exe leave_portal_main:app --reload --host 127.0.0.1 --port %PORT%

if errorlevel 1 (
  echo.
  echo [エラー] 休み希望ポータルの起動に失敗しました。
  pause
  exit /b 1
)
