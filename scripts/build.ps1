$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv non trovato. Installa uv prima di continuare."
    Write-Host ""
    Write-Host "Installer ufficiale:"
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}

uv sync
uv run --frozen --dev python tools\build.py
