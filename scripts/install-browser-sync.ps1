# 安装 Playwright 浏览器同步依赖 / Install browser-sync optional deps
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "未找到 .venv。请先在项目目录运行: python -m venv .venv"
}
Set-Location $Root
Write-Host "安装 osint-toolkit[browser] …" -ForegroundColor Cyan
& $venvPy -m pip install -e ".[browser]"
Write-Host "安装 Playwright Edge 驱动 …" -ForegroundColor Cyan
& $venvPy -m playwright install msedge
Write-Host "完成。可运行 browser-sync.bat 或 osint ingest browser-sync" -ForegroundColor Green
