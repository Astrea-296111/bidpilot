$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
$PythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not (Test-Path $PythonExe)) { throw "Run .\scripts\setup.ps1 first." }
$env:MODE = "lite"
$env:EMBEDDING_PROVIDER = "hash"
& $PythonExe -m eval.run
if ($LASTEXITCODE -ne 0) { throw "Command failed" }
