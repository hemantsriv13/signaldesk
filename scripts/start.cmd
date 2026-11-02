@echo off
rem Start SignalDesk on http://127.0.0.1:8780 and open it in the browser.
rem The local model is optional: start it separately (see README, "Local model").
rem Pass --home <folder> to use a different data folder than D:\LocalAI\signaldesk.
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
.venv\Scripts\python -m signaldesk --open %*
