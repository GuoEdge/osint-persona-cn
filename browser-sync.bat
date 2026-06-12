@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  set PY=.venv\Scripts\python.exe
) else (
  set PY=python
)
set PYTHONPATH=%CD%\src
"%PY%" -m pip show playwright >nul 2>&1
if errorlevel 1 (
  echo 正在安装 Playwright 依赖...
  "%PY%" -m pip install -e ".[browser]"
)
echo.
echo  OSINT 浏览器会话补洞 Playwright
echo  Edge 打开时会自动用 Cookie 模式，无需关闭浏览器
echo.
"%PY%" -m osint_toolkit.cli ingest browser-sync %*
if errorlevel 1 pause
