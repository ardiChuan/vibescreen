<#
Registrera tokenservern som en schemalagd uppgift på Windows, så den
överlever utloggning och omstart — luckan i issue #3: tjänsten fanns men
dog med terminalfönstret.

Körs i PowerShell från repots rot:

  powershell -ExecutionPolicy Bypass -File tools\tokenserver\install-windows-task.ps1 `
      -PublishUrl "https://<din-brevlåda>/u/<hemlighet>"

  # utan relä (bara LAN-servering):
  powershell -ExecutionPolicy Bypass -File tools\tokenserver\install-windows-task.ps1

  # avinstallera:
  powershell -ExecutionPolicy Bypass -File tools\tokenserver\install-windows-task.ps1 -Uninstall

Designval, i linje med resten av repot:

- Uppgiften kör som DEN INLOGGADE ANVÄNDAREN, inte SYSTEM. Tokenservern
  läser %USERPROFILE%\.claude\.credentials.json — en SYSTEM-tjänst hade
  läst fel profil och dessutom gett processen mer rättigheter än den
  behöver.
- En dold PowerShell-wrapper kör python.exe och skriver en begränsad logg till
  %LOCALAPPDATA%\VibePulse\Logs\torget-tokenserver.log. En enda .old-fil
  håller omstarter och lång drift från att växa utan gräns.
- Interaction providers and detail are read from the tokenserver's saved config.
  Keep those choices out of the scheduled command so setup changes cannot go
  stale here. The optional publish arguments below are numbers-relay settings,
  not interaction-provider choices.
- Ingen hemlighet i den registrerade kommandoraden utom relä-URL:en, som
  användaren själv valt att ge — samma exponeringsnivå som secrets.h.
- Starta om vid fel, var 5:e minut, utan tak — en hyllservice ska resa
  sig själv, precis som launchd-plisten gör på macOS.
#>
param(
    [string]$PublishUrl = "",
    [string]$PublishName = "",
    [switch]$ValidateOnly,
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "VibePulse tokenserver"

if ($ValidateOnly -and $Uninstall) {
    throw "-ValidateOnly and -Uninstall cannot be combined"
}

function Resolve-VibePulsePython {
    # Task Scheduler inherits a much smaller PATH than an interactive shell.
    # Resolve the real interpreter at install time and reject Python versions
    # the tokenserver does not support instead of registering a task that can
    # only fail after the next login.
    $candidates = @()
    $py = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($py) {
        try {
            $pyLauncher = $py.Source
            $resolved = & $pyLauncher -3 -c `
                "import sys; print(sys.executable if sys.version_info >= (3, 11) else '')"
            if ($LASTEXITCODE -eq 0 -and $resolved) {
                $candidates += $resolved.Trim()
            }
        } catch {
            # Continue to explicit python.exe/python3.exe candidates.
        }
    }
    foreach ($name in @("python.exe", "python3.exe")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        try {
            & $candidate -c `
                "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {
            # Try the next candidate and fail once with one actionable message.
        }
    }
    throw "VibePulse requires Python 3.11 or newer. Install it, reopen PowerShell, and rerun this installer."
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Uppgiften '$TaskName' borttagen. Processen som redan kör påverkas inte;"
    Write-Host "stoppa den via porten:  Get-NetTCPConnection -LocalPort 8737 -State Listen |"
    Write-Host "  Select -Expand OwningProcess | ForEach-Object { Stop-Process -Id `$_ }"
    exit 0
}

# Repots rot är två steg upp från det här skriptet — uppgiften ska
# överleva att den registreras från vilken katalog som helst.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Server = Join-Path $RepoRoot "tools\tokenserver\tokenserver.py"
if (-not (Test-Path $Server)) { throw "hittar inte $Server" }
$Runner = Join-Path $RepoRoot "tools\tokenserver\run-windows-task.ps1"
if (-not (Test-Path $Runner)) { throw "hittar inte $Runner" }

$PythonConsole = Resolve-VibePulsePython
# Task Scheduler starts a hidden PowerShell wrapper. Keep python.exe rather
# than pythonw.exe so stdout/stderr can be captured in the durable log.
$PowerShell = (Get-Command powershell.exe -ErrorAction Stop).Source

$RunnerArgs = "-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass" +
    " -File `"$Runner`" -Python `"$PythonConsole`" -Server `"$Server`""
if ($PublishUrl) {
    $RunnerArgs += " -PublishUrl `"$PublishUrl`""
    if ($PublishName) { $RunnerArgs += " -PublishName `"$PublishName`"" }
}

$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $RunnerArgs `
    -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

# ValidateOnly deliberately constructs every ScheduledTasks object before it
# exits. PowerShell parser success did not catch a real-host enum mismatch;
# this dry run now exercises the module's runtime parameter conversion while
# still avoiding task lookup, registration, start, stop, or removal.
if ($ValidateOnly) {
    $Version = & $PythonConsole -c `
        "import sys; print('.'.join(map(str, sys.version_info[:3])))"
    Write-Host "VibePulse Windows installer validation: OK"
    Write-Host "  repo:    $RepoRoot"
    Write-Host "  server:  $Server"
    Write-Host "  runner:  $Runner"
    Write-Host "  python:  $PythonConsole ($Version)"
    Write-Host "  task objects: runtime construction passed"
    Write-Host "  action:  no Task Scheduler changes were made"
    exit 0
}

# Windows 10's ScheduledTasks PowerShell module does not expose the task
# schema's StopExisting policy; its enum contains only Parallel, Queue and
# IgnoreNew. Stop the exact old task explicitly during an idempotent update,
# then use the broadly supported IgnoreNew policy to prevent duplicate
# long-running tokenservers during ordinary triggers.
$ExistingTask = Get-ScheduledTask -TaskName $TaskName `
    -ErrorAction SilentlyContinue
if ($ExistingTask -and $ExistingTask.State -eq "Running") {
    Stop-ScheduledTask -TaskName $TaskName
}

Register-ScheduledTask -TaskName $TaskName -Action $Action `
    -Trigger $Trigger -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Uppgiften '$TaskName' registrerad och startad."
Write-Host "  server:  $Server"
if ($PublishUrl) { Write-Host "  relä:    $PublishUrl" }
Write-Host "  state:   $env:LOCALAPPDATA\VibePulse\"
Write-Host "  logg:    $env:LOCALAPPDATA\VibePulse\Logs\torget-tokenserver.log"
Write-Host "Verifiera:  curl http://localhost:8737/  (claudeProbe ska visa ok)"
