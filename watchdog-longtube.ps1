$ErrorActionPreference = "Continue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "data\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "longtube-watchdog.log"

function Write-WatchLog([string]$Message) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogFile -Encoding UTF8 -Value "[$ts] $Message"
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

function Start-Backend {
  $backend = Join-Path $Root "backend"
  $out = Join-Path $LogDir "watchdog-backend.out.log"
  $err = Join-Path $LogDir "watchdog-backend.err.log"
  Write-WatchLog "Backend down; starting uvicorn on 8000"
  Start-Process -WindowStyle Hidden -FilePath "python" `
    -ArgumentList @("-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8000","--reload","--reload-dir","app","--reload-dir","workflows","--reload-dir","scripts") `
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
  if (!(Test-Port 8000)) { Start-Backend }
  if (!(Test-Port 3000)) { Start-Frontend }
  if (!(Test-Port 8188)) { Start-Comfy }
} catch {
  Write-WatchLog "watchdog error: $($_.Exception.Message)"
}
