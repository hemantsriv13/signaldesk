@echo off
rem Start SignalDesk on http://127.0.0.1:8780 and open it in the browser.
rem Starts the existing sibling local-ai Colibri launcher when port 8000 is free.
rem Pass --no-start-model to open only SignalDesk.
rem Pass --home <folder> to use a different data folder than D:\LocalAI\signaldesk.
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
  echo Run scripts\setup.cmd first.
  exit /b 1
)
.venv\Scripts\python -m signaldesk --open --start-model %*
