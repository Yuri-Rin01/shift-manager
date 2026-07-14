$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot

foreach ($port in 8000, 8001, 8002, 8003) {
    netstat -ano | Select-String ":$port\s+.*LISTENING" | ForEach-Object {
        $processId = ($_.Line -split '\s+')[-1]
        if ($processId -match '^\d+$') {
            taskkill /F /PID $processId 2>$null | Out-Null
        }
    }
}

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'shift-manager.*uvicorn|uvicorn.*main:app' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Sleep -Seconds 3

$uvicorn = Join-Path $PSScriptRoot ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $uvicorn)) {
    Write-Error "venv not found. Run install-server.bat first."
    exit 1
}

# Port 8000 may keep stale listeners on Windows; prefer 8003 when 8000 is still occupied.
$port = 8000
$ghostListeners = @(netstat -ano | Select-String "127.0.0.1:8000\s+.*LISTENING").Count
if ($ghostListeners -gt 0) {
    $port = 8003
}

Start-Process -FilePath $uvicorn -ArgumentList @(
    "main:app",
    "--reload",
    "--host", "127.0.0.1",
    "--port", "$port"
) -WorkingDirectory $PSScriptRoot

Start-Sleep -Seconds 5

Write-Host "Server: http://127.0.0.1:$port/"
foreach ($path in @("/", "/staff")) {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port$path" -UseBasicParsing -TimeoutSec 10
        Write-Host ($path + " -> " + $response.StatusCode)
    } catch {
        Write-Host ($path + " -> ERROR")
    }
}
