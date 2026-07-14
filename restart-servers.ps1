# shift-manager server restart (main + leave portal)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$venvUvicorn = Join-Path $PSScriptRoot ".venv\Scripts\uvicorn.exe"
if (-not (Test-Path $venvUvicorn)) {
    throw "venv not found. Run install-server.bat first."
}

function Stop-ShiftManagerServers {
    Get-CimInstance Win32_Process |
        Where-Object { $_.CommandLine -and $_.CommandLine -like "*shift-manager*" -and $_.CommandLine -match "uvicorn" } |
        ForEach-Object {
            Write-Host "stop PID $($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    Start-Sleep -Seconds 2
}

function Test-LeaveRequestsPage {
    param([int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/leave-requests" -UseBasicParsing -TimeoutSec 5
        return ($response.StatusCode -eq 200 -and $response.Content -match "leave-requests-page")
    } catch {
        return $false
    }
}

function Test-LeaveRequestsApi {
    param([int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/leave-requests/overview" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-SettingsPage {
    param([int]$Port)
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/settings" -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-MainServerHealthy {
    param([int]$Port)
    return (Test-LeaveRequestsPage -Port $Port) -and (Test-LeaveRequestsApi -Port $Port) -and (Test-SettingsPage -Port $Port)
}

function Start-MainServer {
    foreach ($port in 8000, 8010, 8003) {
        Write-Host "main try port $port"
        $proc = Start-Process -FilePath $venvUvicorn `
            -ArgumentList @("main:app", "--host", "127.0.0.1", "--port", "$port") `
            -WorkingDirectory $PSScriptRoot `
            -WindowStyle Hidden `
            -PassThru
        Start-Sleep -Seconds 4
        if (Test-MainServerHealthy -Port $port) {
            Write-Host "main OK http://127.0.0.1:$port/"
            return $port
        }
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    throw "main server failed (old process may still hold port 8000 - try PC reboot or use 8010 manually)"
}

function Start-PortalServer {
    foreach ($port in 8004, 8005) {
        Write-Host "portal try port $port"
        $proc = Start-Process -FilePath $venvUvicorn `
            -ArgumentList @("leave_portal_main:app", "--host", "127.0.0.1", "--port", "$port") `
            -WorkingDirectory $PSScriptRoot `
            -WindowStyle Hidden `
            -PassThru
        Start-Sleep -Seconds 4
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/" -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Host "portal OK http://127.0.0.1:$port/"
                return $port
            }
        } catch {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
    throw "portal server failed"
}

Write-Host "=== stop existing ==="
Stop-ShiftManagerServers

Write-Host "=== start servers ==="
$mainPort = Start-MainServer
$portalPort = Start-PortalServer

Write-Host ""
Write-Host "done"
Write-Host "  main: http://127.0.0.1:$mainPort/"
Write-Host "  leave admin: http://127.0.0.1:$mainPort/leave-requests"
Write-Host "  leave portal: http://127.0.0.1:$portalPort/"
