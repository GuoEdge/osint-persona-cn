# Thin wrapper — see start-web.ps1 for implementation
param(
    [int]$Port = 8787,
    [string]$HostName = "127.0.0.1",
    [switch]$NoBrowser
)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
& (Join-Path $here "start-web.ps1") -Port $Port -HostName $HostName -NoBrowser:$NoBrowser
