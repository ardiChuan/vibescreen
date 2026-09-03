<#
.SYNOPSIS
    Register the tokenserver and Bluetooth bridge as Task Scheduler tasks so the
    phone panel keeps working after this terminal closes and after a reboot.

.DESCRIPTION
    Both processes are ordinary user-session programs: the tokenserver reads the
    signed-in user's Claude credentials, and the bridge needs the user's paired
    Bluetooth radio. They are therefore registered to run at logon as the
    current user in an interactive session -- not as SYSTEM, which would see
    neither.

    Windows keeps no state from this script beyond the two tasks, so
    -Uninstall removes the whole footprint.

.PARAMETER Uninstall
    Remove both tasks and stop them if running.

.PARAMETER NoBluetooth
    Register only the tokenserver.

.EXAMPLE
    .\tools\btbridge\install-phone-panel-tasks.ps1
    .\tools\btbridge\install-phone-panel-tasks.ps1 -Uninstall
#>
[CmdletBinding()]
param(
    [switch]$Uninstall,
    [switch]$NoBluetooth,
    [int]$Port = 8737,
    [int]$Channel = 5
)

$ErrorActionPreference = 'Stop'

$TASK_SERVER = 'VibePulse Tokenserver'
$TASK_BRIDGE = 'VibePulse Bluetooth Bridge'

function Remove-Task($name) {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($existing) {
        try { Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue } catch {}
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "removed: $name" -ForegroundColor Yellow
    } else {
        Write-Host "not present: $name" -ForegroundColor DarkGray
    }
}

if ($Uninstall) {
    Remove-Task $TASK_SERVER
    Remove-Task $TASK_BRIDGE
    Write-Host "`nDone. Nothing else was installed system-wide." -ForegroundColor Green
    return
}

# The repo root is two levels up from tools/btbridge.
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path (Join-Path $repo 'tools\tokenserver\tokenserver.py'))) {
    throw "Could not locate the repository from $PSScriptRoot"
}

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "python not found on PATH." }

# pythonw.exe runs without opening a console window, which is what you want for
# something that lives in the background. Fall back to python.exe if absent.
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
$runner = if (Test-Path $pythonw) { $pythonw } else { $python }

$keyPath = Join-Path $env:USERPROFILE '.vibepulse-device-key'
if (-not (Test-Path $keyPath)) {
    # The panel is read-only and never answers, so no key is required. The
    # tokenserver simply logs that device answers are unconfigured.
    Write-Host "note: no device key present - fine, the phone panel is read-only." -ForegroundColor DarkGray
}

Write-Host "repo   : $repo"
Write-Host "python : $runner`n"

# --- tokenserver -------------------------------------------------------------
Remove-Task $TASK_SERVER
$serverArgs = "`"$repo\tools\tokenserver\tokenserver.py`" --port $Port"
$action = New-ScheduledTaskAction -Execute $runner -Argument $serverArgs -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited
# Restart on failure, and never let Windows stop it for running "too long":
# it is a service, so its whole job is to run indefinitely.
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $TASK_SERVER -Action $action -Trigger $trigger `
    -Principal $principal -Settings $settings `
    -Description 'Serves Claude usage JSON to the VibePulse phone panel.' | Out-Null
Write-Host "registered: $TASK_SERVER" -ForegroundColor Green

# --- bluetooth bridge --------------------------------------------------------
if (-not $NoBluetooth) {
    Remove-Task $TASK_BRIDGE
    $bridgeArgs = "`"$repo\tools\btbridge\bt_bridge.py`" --channel $Channel " +
                  "--tokenserver http://127.0.0.1:$Port"
    $action2 = New-ScheduledTaskAction -Execute $runner -Argument $bridgeArgs -WorkingDirectory $repo
    Register-ScheduledTask -TaskName $TASK_BRIDGE -Action $action2 -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description 'Bridges the VibePulse phone panel over Bluetooth RFCOMM.' | Out-Null
    Write-Host "registered: $TASK_BRIDGE" -ForegroundColor Green
}

Write-Host "`nStarting both now..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TASK_SERVER
if (-not $NoBluetooth) { Start-ScheduledTask -TaskName $TASK_BRIDGE }

Start-Sleep -Seconds 4
try {
    $r = Invoke-WebRequest "http://127.0.0.1:$Port/api/tokens" -UseBasicParsing -TimeoutSec 6
    Write-Host "tokenserver responding on $Port (HTTP $($r.StatusCode))" -ForegroundColor Green
} catch {
    Write-Host "tokenserver not answering yet: $_" -ForegroundColor Yellow
    Write-Host "Check Task Scheduler > $TASK_SERVER for its last result." -ForegroundColor Yellow
}

Write-Host "`nBoth start again at every logon. Remove with:" -ForegroundColor DarkGray
Write-Host "  .\tools\btbridge\install-phone-panel-tasks.ps1 -Uninstall" -ForegroundColor DarkGray
