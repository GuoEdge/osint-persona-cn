@echo off
chcp 65001 >nul
title OSINT 情报台
cd /d "%~dp0"
call "%~dp0start-osint-web.bat"
if errorlevel 1 pause
