# Stop OSINT Web service on local port (UTF-8 with BOM for Windows PowerShell 5.1)
param([int]$Port = 8787)

$pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

if (-not $pids) {
    Write-Host "端口 $Port 上没有正在监听的服务." -ForegroundColor Yellow
    exit 0
}

foreach ($procId in $pids) {
    try {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        if ($proc.ProcessName -notmatch "python|pythonw") {
            $yn = Read-Host "端口被 $($proc.ProcessName) 占用，非 osint，是否结束? (y/N)"
            if ($yn -ne "y") { continue }
        }
        Write-Host "结束进程 $($proc.ProcessName) (PID $procId)" -ForegroundColor Cyan
        Stop-Process -Id $procId -Force
    } catch {
        Write-Host "无法结束 PID $procId : $_" -ForegroundColor Red
    }
}

Write-Host "已停止." -ForegroundColor Green
