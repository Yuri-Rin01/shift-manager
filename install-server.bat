@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  シフト管理サーバー - セットアップ
echo ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [エラー] Python が見つかりません。
  echo Python 3.11 以上をインストールしてから再実行してください。
  echo https://www.python.org/downloads/
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo 仮想環境を作成しています...
  python -m venv .venv
  if errorlevel 1 (
    echo [エラー] 仮想環境の作成に失敗しました。
    pause
    exit /b 1
  )
)

echo 依存パッケージをインストールしています...
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo [エラー] パッケージのインストールに失敗しました。
  pause
  exit /b 1
)

echo.
echo データベースを初期化しています...
.\.venv\Scripts\python.exe -c "from db.database import init_db; init_db(); print('OK')"
if errorlevel 1 (
  echo [エラー] データベース初期化に失敗しました。
  pause
  exit /b 1
)

echo.
echo ========================================
echo  セットアップ完了
echo  start-server.bat でサーバーを起動できます
echo ========================================
pause
