@echo off
chcp 65001 >nul
title OSINT Web
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-web.ps1"
if errorlevel 1 pause
