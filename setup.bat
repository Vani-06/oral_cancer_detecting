@echo off
rem One-time setup for OralSentinel on Windows: Python environment, backend
rem packages, settings file and website packages. Safe to run again.
setlocal
cd /d "%~dp0"
echo.
echo === OralSentinel setup ===
echo.

rem Python 3.14 is required (the pinned PyTorch build is tested on it).
set "PY="
py -3.14 --version >nul 2>nul && set "PY=py -3.14"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 14) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo Python 3.14 was not found.
  echo Install it from https://www.python.org/downloads/ - choose a 3.14 release,
  echo and tick "Add python.exe to PATH" on the first screen. Then run setup.bat again.
  goto :fail
)

where npm >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found.
  echo Install the LTS version from https://nodejs.org/ and run setup.bat again.
  goto :fail
)

echo [1/4] Creating the Python environment...
if not exist "backend\.venv\Scripts\python.exe" (
  %PY% -m venv backend\.venv
  if errorlevel 1 goto :fail
)

echo [2/4] Installing backend packages. This downloads about 1 GB and can take 10 to 20 minutes...
backend\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 goto :fail

echo [3/4] Writing backend settings...
if not exist "backend\.env" (
  > "backend\.env" echo DATABASE_URL=sqlite:///./oralsentinel.db
  >> "backend\.env" echo AUTO_CREATE_TABLES=true
  >> "backend\.env" echo MODEL_PATH=../ml/artifacts/resnet50_oral_cancer_v7.pt
  >> "backend\.env" echo GATE_MODEL_PATH=../ml/artifacts/oral_photo_gate_v1.pt
  >> "backend\.env" echo GRADING_MODEL_PATH=../ml/artifacts/resnet50_dysplasia_grade_v2.pt
  backend\.venv\Scripts\python.exe -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" >> "backend\.env"
) else (
  echo backend\.env already exists - kept as it is.
)

echo [4/4] Installing website packages. This can take a few minutes...
pushd frontend
call npm install --no-audit --no-fund
if errorlevel 1 (
  popd
  goto :fail
)
popd

echo.
echo Setup finished. Double-click start.bat to open OralSentinel.
if not defined NOPAUSE pause
exit /b 0

:fail
echo.
echo Setup did not finish. Read the message above, fix it, then run setup.bat again.
if not defined NOPAUSE pause
exit /b 1
