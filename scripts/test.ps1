$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
$PythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not (Test-Path $PythonExe)) { throw "Run .\scripts\setup.ps1 first." }
& $PythonExe -m ruff check .
if ($LASTEXITCODE -ne 0) { throw "Lint failed" }
& $PythonExe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Command failed" }
