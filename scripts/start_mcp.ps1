param([switch]$Http)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
$PythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
if (-not (Test-Path $PythonExe)) { throw "Run .\scripts\setup.ps1 first." }
if ($Http) { & $PythonExe -m bidpilot_mcp.server --transport streamable-http }
else { & $PythonExe -m bidpilot_mcp.server }
if ($LASTEXITCODE -ne 0) { throw "Command failed" }
