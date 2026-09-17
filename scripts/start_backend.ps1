$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
$PythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not (Test-Path $PythonExe)) { throw "Run .\scripts\setup.ps1 first." }
& $PythonExe -m uvicorn bidpilot.api.app:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
if ($LASTEXITCODE -ne 0) { throw "Command failed" }
