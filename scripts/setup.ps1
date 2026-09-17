param([switch]$Models)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$env:PYTHONUTF8 = "1"
if (-not (Test-Path ".venv/Scripts/python.exe")) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { py -3.11 -m venv .venv }
    if ($LASTEXITCODE -ne 0) { throw "Install Python 3.11 or 3.12 with the Windows py launcher." }
}
$PythonExe = Join-Path (Get-Location) ".venv/Scripts/python.exe"
& $PythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $PythonExe -m pip install -e ".[dev,ui]"
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
if ($Models) {
    & $PythonExe -m pip install -e ".[models]"
    if ($LASTEXITCODE -ne 0) { throw "Model dependency installation failed" }
}
if (-not (Test-Path ".env")) { Copy-Item .env.example .env }
& $PythonExe scripts/generate_formats.py
if ($LASTEXITCODE -ne 0) { throw "Fixture generation failed" }
Write-Host "Ready. Run .\scripts\demo_lite.ps1"
