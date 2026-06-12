# Create desktop shortcuts for OSINT web launcher (ASCII paths for reliability)
$Root = Split-Path -Parent $PSScriptRoot
$BatStart = Join-Path $Root "start-osint-web.bat"
$BatStop = Join-Path $Root "stop-osint-web.bat"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Wsh = New-Object -ComObject WScript.Shell

if (-not (Test-Path $BatStart)) {
    Write-Error "Not found: $BatStart"
    exit 1
}

$startLnk = Join-Path $Desktop "OSINT Web.lnk"
$start = $Wsh.CreateShortcut($startLnk)
$start.TargetPath = $BatStart
$start.WorkingDirectory = $Root
$start.WindowStyle = 1
$start.Description = "Start OSINT local web UI on http://127.0.0.1:8787"
$start.Save()

$stopLnk = Join-Path $Desktop "Stop OSINT Web.lnk"
$stop = $Wsh.CreateShortcut($stopLnk)
$stop.TargetPath = $BatStop
$stop.WorkingDirectory = $Root
$stop.WindowStyle = 1
$stop.Description = "Stop OSINT web service on port 8787"
$stop.Save()

Write-Host "Desktop shortcuts created:" -ForegroundColor Green
Write-Host "  $startLnk"
Write-Host "  $stopLnk"
