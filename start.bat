@echo off
rem Starts the OralSentinel backend and website, each in its own window,
rem then opens the website. Close both windows to stop it.
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" (
  echo Run setup.bat first.
  pause
  exit /b 1
)
echo Starting OralSentinel. Two windows will open: keep them open while you use it.
start "OralSentinel backend" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"
start "OralSentinel website" cmd /k "cd /d "%~dp0frontend" && npm run dev"
echo Waiting for the models to load...
timeout /t 30 /nobreak >nul
start "" http://localhost:5173
