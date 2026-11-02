@echo off
rem One-time setup: Python environment, Python packages, and the web app build.
rem Run from the signaldesk folder:  scripts\setup.cmd
setlocal
cd /d "%~dp0.."
if not exist .venv (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv
)
call .venv\Scripts\python -m pip install --disable-pip-version-check -q -r requirements.txt || exit /b 1
pushd web
call npm install --no-fund --no-audit || exit /b 1
call npm run build || exit /b 1
popd
echo.
echo Setup done. Start SignalDesk with scripts\start.cmd
