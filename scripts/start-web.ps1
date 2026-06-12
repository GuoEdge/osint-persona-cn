# 一键启动 OSINT Web 控制台 / Launch local web UI
param(
    [int]$Port = 8787,
    [string]$HostName = "127.0.0.1",
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Src = Join-Path $Root "src"
$Url = "http://${HostName}:$Port"

function Write-Banner {
    Write-Host ""
    Write-Host "  OSINT 个人情报台" -ForegroundColor Cyan
    Write-Host "  $Url" -ForegroundColor DarkGray
    Write-Host ""
}

function Get-PythonExe {
    $venvPy = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venvPy) { return $venvPy }
    $py312 = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $py312) { return $py312 }
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        $ver = & $py.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
        if ([version]$ver -ge [version]"3.14") {
            throw "检测到 Python $ver（不支持 rookiepy/Cookie 同步）。请使用 $Root\.venv 或安装 Python 3.12"
        }
        return $py.Source
    }
    throw "未找到 Python。请在项目目录创建 .venv：python -m venv .venv"
}

function Test-RookiePy($pythonExe) {
    & $pythonExe -c "import rookiepy" 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-ServerHealthy {
    try {
        $r = Invoke-WebRequest -Uri "$Url/api/extension/status" -UseBasicParsing -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-PortInUse {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return [bool]$conn
}

Write-Banner

if (Test-ServerHealthy) {
    Write-Host "服务已在运行（检测到新版 API）。" -ForegroundColor Green
    if (-not $NoBrowser) { Start-Process $Url }
    Write-Host "关闭本窗口不会停止服务；要停止请运行「停止情报台.bat」。" -ForegroundColor Yellow
    exit 0
}

if (Test-PortInUse) {
    Write-Host "端口 $Port 已被占用，但 API 不是当前版本（可能是旧服务）。" -ForegroundColor Yellow
    Write-Host "请先运行「停止情报台.bat」，再重新启动。" -ForegroundColor Yellow
    exit 1
}

$python = Get-PythonExe
$env:PYTHONPATH = $Src
Set-Location $Root

$pyVer = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-Host "Python: $python ($pyVer)" -ForegroundColor DarkGray
if (-not (Test-RookiePy $python)) {
    Write-Host "警告: 当前 Python 未安装 rookiepy，设置页「同步 Cookie」会失败。请用 .venv 或运行 sync-cookies.bat" -ForegroundColor Yellow
}
Write-Host "正在启动…（保持此窗口打开；Ctrl+C 停止服务）" -ForegroundColor Green
Write-Host "首次拉取 B站+知乎 约需 2–4 分钟，请勿关闭窗口。" -ForegroundColor DarkGray
Write-Host "浏览器补洞需 Playwright：首次请运行 scripts/install-browser-sync.ps1" -ForegroundColor DarkGray
Write-Host ""

if (-not $NoBrowser) {
    Start-Job -ScriptBlock {
        param($openUrl)
        Start-Sleep -Seconds 2
        Start-Process $openUrl
    } -ArgumentList $Url | Out-Null
}

& $python -m osint_toolkit.cli web --host $HostName --port $Port
