param([switch]$Approve, [switch]$Reject)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
$PythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not (Test-Path $PythonExe)) { throw "Run .\scripts\setup.ps1 first." }
$env:MODE = "lite"
$env:EMBEDDING_PROVIDER = "hash"
$DemoArgs = @("-m", "bidpilot.cli", "demo")
if ($Approve) { $DemoArgs += "--approve" }
if ($Reject) { $DemoArgs += "--reject" }
& $PythonExe @DemoArgs
if ($LASTEXITCODE -ne 0) { throw "Command failed" }
