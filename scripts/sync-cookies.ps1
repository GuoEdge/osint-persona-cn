# Sync Edge cookies via project venv (UTF-8)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Host "[ERROR] .venv not found. Run: python -m venv .venv; pip install -e .[web]" -ForegroundColor Red
    exit 1
}
$env:PYTHONPATH = Join-Path $Root "src"
Write-Host ""
Write-Host "Close ALL Edge windows, then press Enter..." -ForegroundColor Yellow
Write-Host "(Guan bi suo you Edge chuang kou, an Hui che ji xu)" -ForegroundColor DarkGray
Read-Host | Out-Null
& $Py -m osint_toolkit.cli auth sync-cookies --browser edge
$code = $LASTEXITCODE
if ($code -ne 0) {
    Write-Host ""
    Write-Host "If you see appbound encryption: use extension button" -ForegroundColor Yellow
    Write-Host "  or run sync-cookies-admin.bat as Administrator" -ForegroundColor Yellow
    exit $code
}
Write-Host ""
Write-Host "Done. Check Bilibili/Zhihu status in Web Settings." -ForegroundColor Green
