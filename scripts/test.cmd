@echo off
rem Mocked tests (no network, no model) and the deterministic evaluation.
setlocal
cd /d "%~dp0.."
.venv\Scripts\python -m pytest || exit /b 1
.venv\Scripts\python -m eval.run_eval rules || exit /b 1
pushd web
call npx tsc -b || exit /b 1
popd
