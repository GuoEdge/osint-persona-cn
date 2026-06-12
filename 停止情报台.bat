@echo off
chcp 65001 >nul
title 停止 OSINT 情报台
cd /d "%~dp0"
call "%~dp0stop-osint-web.bat"
