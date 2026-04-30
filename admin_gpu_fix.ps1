$ErrorActionPreference = "Continue"

$log = "C:\Users\Ai_M9\Desktop\longtube\dumpcopy\gpu-fix-install.log"
$installer = "C:\Users\Ai_M9\Desktop\longtube\dumpcopy\595.79-studio.exe"

function Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    $line | Tee-Object -FilePath $log -Append
}

Log "=== GPU fix started ==="
Log "Running as: $([Security.Principal.WindowsIdentity]::GetCurrent().Name)"

try {
    $path = "HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
    New-Item -Path $path -Force | Out-Null
    New-ItemProperty -Path $path -Name HwSchMode -PropertyType DWord -Value 1 -Force | Out-Null
    $val = (Get-ItemProperty -Path $path -Name HwSchMode -ErrorAction Stop).HwSchMode
    Log "HAGS HwSchMode set to $val (1 = disabled)"
} catch {
    Log "HAGS set failed: $($_.Exception.Message)"
}

try {
    Log "Stopping ComfyUI/python GPU processes if present"
    Get-CimInstance Win32_Process -Filter "name = 'python.exe'" |
        Where-Object { $_.CommandLine -match "ComfyUI|--port 8188" } |
        ForEach-Object {
            Log "Stopping PID $($_.ProcessId): $($_.CommandLine)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Continue
        }
} catch {
    Log "Process stop skipped/failed: $($_.Exception.Message)"
}

try {
    if (-not (Test-Path -LiteralPath $installer)) {
        throw "Installer missing: $installer"
    }
    Log "Starting NVIDIA 595.79 Studio installer clean/silent"
    $args = "-s -clean -noreboot"
    $p = Start-Process -FilePath $installer -ArgumentList $args -Wait -PassThru
    Log "NVIDIA installer exit code: $($p.ExitCode)"
} catch {
    Log "NVIDIA installer failed: $($_.Exception.Message)"
}

try {
    Log "Current video controller state after installer:"
    Get-CimInstance Win32_VideoController |
        Select-Object Name,DriverVersion,DriverDate |
        Format-List |
        Out-String |
        Tee-Object -FilePath $log -Append
} catch {
    Log "Driver query failed: $($_.Exception.Message)"
}

Log "=== GPU fix finished. Reboot is required. ==="
