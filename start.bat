@echo off
cd /d "%~dp0"
echo Starting AutoAttend...
where py >nul 2>&1 && (
  set "PY=py -3"
) || (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating a local Python environment. This runs once.
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Python was not found. Install Python 3, then run this file again.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
set DB_TYPE=sqlite
start "" "http://127.0.0.1:5000/login"
".venv\Scripts\python.exe" app.py
pause
