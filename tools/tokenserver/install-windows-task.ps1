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
- pythonw.exe (inget konsolfönster). Loggarna hamnar där de redan bor:
  %LOCALAPPDATA%\VibePulse\ (tjänstens egen självroterande logg).
- Ingen hemlighet i den registrerade kommandoraden utom relä-URL:en, som
  användaren själv valt att ge — samma exponeringsnivå som secrets.h.
- Starta om vid fel, var 5:e minut, utan tak — en hyllservice ska resa
  sig själv, precis som launchd-plisten gör på macOS.
#>
param(
    [string]$PublishUrl = "",
    [string]$PublishName = "",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$TaskName = "VibePulse tokenserver"

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

# pythonw = ingen konsol. Faller tillbaka till python.exe om pythonw
# saknas (minimala installationer) — då syns ett fönster, men tjänsten kör.
$Python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command python.exe).Source }

$ServerArgs = "`"$Server`""
if ($PublishUrl) {
    $ServerArgs += " --publish `"$PublishUrl`""
    if ($PublishName) { $ServerArgs += " --publish-name `"$PublishName`"" }
}

$Action = New-ScheduledTaskAction -Execute $Python -Argument $ServerArgs `
    -WorkingDirectory $RepoRoot
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0)

Register-ScheduledTask -TaskName $TaskName -Action $Action `
    -Trigger $Trigger -Settings $Settings -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName

Write-Host "Uppgiften '$TaskName' registrerad och startad."
Write-Host "  server:  $Server"
if ($PublishUrl) { Write-Host "  relä:    $PublishUrl" }
Write-Host "  loggar:  $env:LOCALAPPDATA\VibePulse\"
Write-Host "Verifiera:  curl http://localhost:8737/  (claudeProbe ska visa ok)"
