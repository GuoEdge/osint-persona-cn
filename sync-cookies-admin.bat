@echo off
chcp 65001 >nul
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Edge 130+ needs Administrator to read cookies from disk.
  echo Requesting elevation...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
  exit /b
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync-cookies.ps1"
pause
