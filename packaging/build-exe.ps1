# Build ShiftManager.exe on Windows
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "==> create venv (if needed)"
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
}

$py = Join-Path (Get-Location) ".venv\Scripts\python.exe"
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements.txt -r requirements-build.txt

Write-Host "==> pyinstaller"
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
& $py -m PyInstaller --noconfirm shift_manager.spec

$exe = Join-Path (Get-Location) "dist\ShiftManager.exe"
if (-not (Test-Path $exe)) {
    throw "EXE was not created"
}

Copy-Item "packaging\README_EXE.txt" "dist\使い方.txt" -Force
Write-Host "OK: $exe"
Write-Host "Copy dist\ShiftManager.exe and dist\使い方.txt for distribution."
