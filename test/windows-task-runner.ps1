<# Non-mutating Windows CI test for the Task Scheduler entrypoint. #>
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $RepoRoot "tools\tokenserver\run-windows-task.ps1"
$Python = (Get-Command python.exe -ErrorAction Stop).Source
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) (
    "VibePulse runner å " + [guid]::NewGuid().ToString("N")
)
$PreviousLocalAppData = $env:LOCALAPPDATA

try {
    New-Item -ItemType Directory -Path $TempRoot -Force | Out-Null
    $env:LOCALAPPDATA = $TempRoot
    $Fixture = Join-Path $TempRoot "fixture med å.py"
    @'
import sys
print("stdout-ok")
print("stderr-ok", file=sys.stderr)
'@ | Set-Content -LiteralPath $Fixture -Encoding UTF8

    $LogDir = Join-Path $TempRoot "VibePulse\Logs"
    $LogPath = Join-Path $LogDir "torget-tokenserver.log"
    $OldLogPath = "$LogPath.old"
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $Filler = New-Object byte[] (5MB + 4096)
    [System.IO.File]::WriteAllBytes($LogPath, $Filler)
    [System.IO.File]::AppendAllText($LogPath, "rotation-sentinel")

    & $Runner -Python $Python -Server $Fixture
    if ($LASTEXITCODE -ne 0) {
        throw "runner returned $LASTEXITCODE"
    }

    if (-not (Test-Path -LiteralPath $OldLogPath -PathType Leaf)) {
        throw "runner did not create the rotated .old tail"
    }
    if ((Get-Item -LiteralPath $OldLogPath).Length -gt 256KB) {
        throw "rotated tail exceeds 256 KiB"
    }
    $OldText = [System.IO.File]::ReadAllText($OldLogPath)
    if (-not $OldText.Contains("rotation-sentinel")) {
        throw "rotated tail lost its final marker"
    }
    $CurrentText = [System.IO.File]::ReadAllText($LogPath)
    if (-not $CurrentText.Contains("stdout-ok")) {
        throw "stdout was not captured"
    }
    if (-not $CurrentText.Contains("stderr-ok")) {
        throw "stderr was not captured"
    }
    Write-Host "VibePulse Windows task runner: OK"
} finally {
    $env:LOCALAPPDATA = $PreviousLocalAppData
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force
    }
}
