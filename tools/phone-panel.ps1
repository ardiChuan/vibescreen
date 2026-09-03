<#
.SYNOPSIS
    Build, install and wire up the VibePulse phone panel over USB.

.DESCRIPTION
    The phone replaces the ESP32 panel by being the same thing: an HTTP client
    that polls the tokenserver and answers one signed POST. Over USB that needs
    no network at all -- `adb reverse` puts the computer's tokenserver on the
    phone's own loopback, so the app talks to http://127.0.0.1:8737 and there is
    no WiFi, no pairing, and no LAN exposure.

    The reverse mapping lives in the adb daemon, not on the phone, so it is lost
    whenever the cable is unplugged or adb restarts. Re-run with -ReverseOnly to
    restore it; that is the normal daily command.

.PARAMETER ReverseOnly
    Skip building and installing; just re-establish the port mapping.

.PARAMETER Launch
    Start the app on the phone once everything is in place.

.EXAMPLE
    .\tools\phone-panel.ps1                 # build, install, reverse, launch
    .\tools\phone-panel.ps1 -ReverseOnly    # after replugging the cable
#>
[CmdletBinding()]
param(
    [switch]$ReverseOnly,
    [switch]$Launch = $true,
    [int]$Port = 8737
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$toolchain = Join-Path (Split-Path -Parent $repo) '.toolchain'

function Resolve-Adb {
    $candidates = @(
        (Join-Path $toolchain 'android-sdk\platform-tools\adb.exe'),
        "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe",
        "$env:ANDROID_HOME\platform-tools\adb.exe"
    )
    foreach ($c in $candidates) { if ($c -and (Test-Path $c)) { return $c } }
    $onPath = Get-Command adb -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    throw "adb not found. Install Android platform-tools, or keep the project toolchain at $toolchain."
}

$adb = Resolve-Adb
Write-Host "adb: $adb" -ForegroundColor DarkGray

# One authorised device, or the later commands act on the wrong target.
$devices = & $adb devices | Select-Object -Skip 1 | Where-Object { $_ -match '\S' }
$ready = $devices | Where-Object { $_ -match '\sdevice$' }
if (-not $ready) {
    Write-Host "No authorised device." -ForegroundColor Red
    Write-Host "  1. Settings -> About phone -> tap 'MIUI version' 7 times"
    Write-Host "  2. Settings -> Additional settings -> Developer options"
    Write-Host "  3. Enable 'USB debugging' AND 'Install via USB'"
    Write-Host "  4. Replug the cable and accept the prompt on the phone"
    if ($devices) { Write-Host "`nSeen: $($devices -join '; ')" -ForegroundColor Yellow }
    exit 1
}
if (@($ready).Count -gt 1) {
    throw "More than one device attached; unplug the others:`n$($ready -join "`n")"
}
Write-Host "device: $(($ready -split '\s+')[0])" -ForegroundColor Green

if (-not $ReverseOnly) {
    $env:JAVA_HOME = (Get-ChildItem $toolchain -Directory -Filter 'jdk-*' -EA SilentlyContinue |
        Select-Object -First 1).FullName
    $env:ANDROID_HOME = Join-Path $toolchain 'android-sdk'
    $env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
    $env:GRADLE_USER_HOME = Join-Path $toolchain 'gradle-home'
    $gradle = Join-Path $toolchain 'gradle-8.7\bin\gradle.bat'

    if (-not (Test-Path $gradle)) {
        throw "Gradle not found at $gradle. See docs/phone-panel.md for the toolchain setup."
    }
    if ($env:JAVA_HOME) { $env:Path = "$env:JAVA_HOME\bin;$env:Path" }

    Write-Host "`nBuilding..." -ForegroundColor Cyan
    Push-Location (Join-Path $repo 'android')
    try {
        & $gradle assembleDebug
        if ($LASTEXITCODE -ne 0) { throw "Gradle build failed." }
    } finally { Pop-Location }

    $apk = Join-Path $repo 'android\app\build\outputs\apk\debug\app-debug.apk'
    if (-not (Test-Path $apk)) { throw "APK missing at $apk" }

    Write-Host "Installing..." -ForegroundColor Cyan
    # -r reinstalls over an existing copy and keeps the stored device key.
    & $adb install -r $apk
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Install failed. On MIUI, 'Install via USB' must be enabled in Developer options." -ForegroundColor Yellow
        exit 1
    }
}

# The mapping the whole USB transport rests on. Phone-side localhost:$Port now
# reaches this computer's tokenserver.
& $adb reverse "tcp:$Port" "tcp:$Port"
if ($LASTEXITCODE -ne 0) { throw "adb reverse failed." }
Write-Host "reverse: phone localhost:$Port -> this computer:$Port" -ForegroundColor Green

$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -EA SilentlyContinue
if (-not $listening) {
    Write-Host "`nWarning: nothing is listening on port $Port here." -ForegroundColor Yellow
    Write-Host "Start the tokenserver, or the panel will show 'stale'." -ForegroundColor Yellow
}

if ($Launch) {
    & $adb shell am start -n se.torget.vibepulse/.MainActivity | Out-Null
    Write-Host "launched VibePulse on the phone" -ForegroundColor Green
}

Write-Host "`nPaste the device key into the app once (Settings -> Device key)." -ForegroundColor DarkGray
Write-Host "After replugging the cable: .\tools\phone-panel.ps1 -ReverseOnly" -ForegroundColor DarkGray
