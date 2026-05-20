$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "longtube-watchdog.log"
$StateFile = Join-Path $LogDir "longtube-watchdog-state.json"

$BackendFailThreshold = 3
$FrontendFailThreshold = 3
$ComfyFailThreshold = 5
$WatchdogMutex = New-Object System.Threading.Mutex($false, "Global\LongTubeWatchdog")
if (-not $WatchdogMutex.WaitOne(0)) {
  exit 0
}

function Write-WatchLog([string]$Message) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogFile -Encoding UTF8 -Value "[$ts] $Message"
}

function Load-State {
  $state = [ordered]@{
    backend_failures = 0
    frontend_failures = 0
    comfy_failures = 0
  }
  if (Test-Path $StateFile) {
    try {
      $raw = Get-Content -Raw -Encoding UTF8 -Path $StateFile | ConvertFrom-Json
      foreach ($name in @("backend_failures", "frontend_failures", "comfy_failures")) {
        if ($null -ne $raw.$name) {
          $state[$name] = [int]$raw.$name
        }
      }
    } catch {
      Write-WatchLog "state load failed; resetting: $($_.Exception.Message)"
    }
  }
  return $state
}

function Save-State($State) {
  try {
    $State | ConvertTo-Json | Set-Content -Path $StateFile -Encoding UTF8
  } catch {
    Write-WatchLog "state save failed: $($_.Exception.Message)"
  }
}

function Test-Port([int]$Port) {
  try {
    $client = New-Object Net.Sockets.TcpClient
    $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
    if ($ok) { $client.EndConnect($iar) }
    $client.Close()
    return [bool]$ok
  } catch {
    return $false
  }
}

function Test-Http([string]$Url, [int]$TimeoutSec = 5) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec $TimeoutSec
    return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
  } catch {
    return $false
  }
}

function Test-ProcessCommand([string]$Pattern) {
  try {
    $matches = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -and $_.CommandLine -match $Pattern })
    return ($matches.Count -gt 0)
  } catch {
    Write-WatchLog "process command check failed: $($_.Exception.Message)"
    return $false
  }
}

function Stop-Port([int]$Port, [string]$Label) {
  try {
    $pids = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
      Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($pidToStop in $pids) {
      if ($pidToStop -and $pidToStop -ne $PID) {
        Write-WatchLog "$Label unhealthy; stopping PID $pidToStop on port $Port"
        Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
      }
    }
  } catch {
    Write-WatchLog "$Label port cleanup failed: $($_.Exception.Message)"
  }
}

function Start-Backend {
  if (Test-ProcessCommand "uvicorn\s+app\.main:app.*--port\s+8000") {
    Write-WatchLog "Backend port not ready; uvicorn process already exists"
    return
  }
  $backend = Join-Path $Root "backend"
  $out = Join-Path $LogDir "watchdog-backend.out.log"
  $err = Join-Path $LogDir "watchdog-backend.err.log"
  Write-WatchLog "Backend down; starting uvicorn on 8000"
  Start-Process -WindowStyle Hidden -FilePath "python" `
    -ArgumentList @("-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000") `
    -WorkingDirectory $backend `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err
}

function Resolve-Node {
  $localNode = Join-Path $env:LOCALAPPDATA "LongTubeTools\node-v22.22.2-win-x64\node.exe"
  if (Test-Path $localNode) { return $localNode }
  return "node"
}

function Start-Frontend {
  if (Test-ProcessCommand "next.*dev.*--port\s+3000") {
    Write-WatchLog "Frontend port not ready; Next process already exists"
    return
  }
  $frontend = Join-Path $Root "frontend"
  $node = Resolve-Node
  $out = Join-Path $LogDir "watchdog-frontend.out.log"
  $err = Join-Path $LogDir "watchdog-frontend.err.log"
  Write-WatchLog "Frontend down; starting Next on 3000"
  $env:WATCHPACK_POLLING = "true"
  $env:CHOKIDAR_USEPOLLING = "1"
  Start-Process -WindowStyle Hidden -FilePath $node `
    -ArgumentList @("node_modules\next\dist\bin\next","dev","--hostname","0.0.0.0","--port","3000") `
    -WorkingDirectory $frontend `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err
}

function Start-Comfy {
  if (Test-ProcessCommand "ComfyUI\\main\.py|main\.py.*--port\s+8188") {
    Write-WatchLog "ComfyUI port not ready; ComfyUI process already exists"
    return
  }
  $script = Join-Path $Root "start-comfyui-lan.bat"
  if (!(Test-Path $script)) {
    Write-WatchLog "ComfyUI down but start script missing: $script"
    return
  }
  Write-WatchLog "ComfyUI down; starting on 8188"
  Start-Process -WindowStyle Hidden -FilePath "cmd.exe" `
    -ArgumentList @("/c", "`"$script`"") `
    -WorkingDirectory $Root
}

try {
  $state = Load-State

  if (!(Test-Port 8000)) {
    $state["backend_failures"] = 0
    Start-Backend
  } elseif (Test-Http "http://127.0.0.1:8000/api/health" 5) {
    $state["backend_failures"] = 0
  } else {
    $state["backend_failures"] = [int]$state["backend_failures"] + 1
    Write-WatchLog "Backend health failed ($($state["backend_failures"])/$BackendFailThreshold)"
    if ([int]$state["backend_failures"] -ge $BackendFailThreshold) {
      Stop-Port 8000 "Backend"
      Start-Sleep -Seconds 2
      Start-Backend
      $state["backend_failures"] = 0
    }
  }

  if (!(Test-Port 3000)) {
    $state["frontend_failures"] = 0
    Start-Frontend
  } elseif (Test-Http "http://127.0.0.1:3000/api/frontend-health" 5) {
    $state["frontend_failures"] = 0
  } else {
    $state["frontend_failures"] = [int]$state["frontend_failures"] + 1
    Write-WatchLog "Frontend health failed ($($state["frontend_failures"])/$FrontendFailThreshold)"
    if ([int]$state["frontend_failures"] -ge $FrontendFailThreshold) {
      Stop-Port 3000 "Frontend"
      Start-Sleep -Seconds 2
      Start-Frontend
      $state["frontend_failures"] = 0
    }
  }

  if (!(Test-Port 8188)) {
    $state["comfy_failures"] = 0
    Start-Comfy
  } elseif (Test-Http "http://127.0.0.1:8188/system_stats" 8) {
    $state["comfy_failures"] = 0
  } else {
    $state["comfy_failures"] = [int]$state["comfy_failures"] + 1
    Write-WatchLog "ComfyUI health failed ($($state["comfy_failures"])/$ComfyFailThreshold)"
    if ([int]$state["comfy_failures"] -ge $ComfyFailThreshold) {
      Start-Comfy
      $state["comfy_failures"] = 0
    }
  }

  Save-State $state
} catch {
  Write-WatchLog "watchdog error: $($_.Exception.Message)"
} finally {
  if ($WatchdogMutex) {
    try {
      $WatchdogMutex.ReleaseMutex() | Out-Null
      $WatchdogMutex.Dispose()
    } catch {
    }
  }
}
