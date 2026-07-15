$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Stop-Build {
    param([string]$Message)

    Write-Host ""
    Write-Host "Errore: $Message"
    exit 1
}

Write-Host "[check] verifico i prerequisiti"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Errore: uv non trovato."
    Write-Host ""
    Write-Host "Installer ufficiale:"
    Write-Host '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
}

$UvVersion = & uv --version
Write-Host "[ok] $UvVersion"

$PythonVersion = & uv python find --show-version 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Errore: non trovo un Python compatibile con il progetto."
    Write-Host ""
    Write-Host "Soluzioni possibili:"
    Write-Host "  uv python install '>=3.13,<3.15'"
    Write-Host "  oppure installa Python 3.13 o 3.14 da https://www.python.org/downloads/"
    exit 1
}

Write-Host "[ok] Python $PythonVersion"

Write-Host ""
Write-Host "[sync] preparo l'ambiente Python"
& uv sync --frozen --dev
if ($LASTEXITCODE -ne 0) {
    Stop-Build "uv sync --frozen --dev non riuscito. Controlla uv.lock, la connessione Internet e la configurazione di uv."
}

Write-Host ""
Write-Host "[build] creo il pacchetto MoonTransfer"
$BuildScript = Join-Path (Join-Path $Root "tools") "build.py"
& uv run --frozen --dev python $BuildScript
if ($LASTEXITCODE -ne 0) {
    Stop-Build "build non riuscita."
}
