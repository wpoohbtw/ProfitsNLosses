@echo off
setlocal EnableExtensions
chcp 65001 > nul

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "PYTHON_EXE=%ROOT%backend\.venv\Scripts\python.exe"

echo [INFO] Workspace: %ROOT%

where python > nul 2> nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH.
  exit /b 1
)

where npm > nul 2> nul
if errorlevel 1 (
  echo [ERROR] npm was not found in PATH.
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [INFO] Creating backend virtualenv...
  python -m venv "%ROOT%backend\.venv"
  if errorlevel 1 exit /b 1
)

echo [INFO] Checking backend dependencies...
call "%PYTHON_EXE%" -m pip install -r "%ROOT%backend\requirements.txt"
if errorlevel 1 exit /b 1

if not exist "%ROOT%node_modules" (
  echo [INFO] Installing frontend dependencies...
  call npm install
  if errorlevel 1 exit /b 1
)

echo [INFO] Stopping stale local services on ports 8001 and 5173...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do (
  echo [WARN] Killing stale backend PID %%P
  taskkill /F /PID %%P > nul 2> nul
)
for /f "skip=1 tokens=2 delims=," %%P in ('wmic process where "commandline like '%%%ROOT:\=\\%backend%%uvicorn%%app.main:app%%'" get ProcessId /format:csv 2^>nul') do (
  if not "%%P"=="" (
    echo [WARN] Killing stale uvicorn PID %%P
    taskkill /F /PID %%P > nul 2> nul
  )
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
  echo [WARN] Killing stale frontend PID %%P
  taskkill /F /PID %%P > nul 2> nul
)
timeout /t 1 /nobreak > nul

echo [OK] Backend:  http://127.0.0.1:8001
echo [OK] Frontend: http://127.0.0.1:5173
echo [INFO] Starting backend in this window...

start "PNL_BACKEND" /B cmd /c cd /d "%BACKEND_DIR%" ^&^& "%PYTHON_EXE%" -m uvicorn app.main:app --host 127.0.0.1 --port 8001

echo [INFO] Waiting for backend health...
set "BACKEND_READY="
for /l %%I in (1,1,45) do (
  "%PYTHON_EXE%" -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health', timeout=1).status == 200 else 1)" > nul 2> nul
  if not errorlevel 1 (
    set "BACKEND_READY=1"
    goto backend_ready
  )
  timeout /t 1 /nobreak > nul
)

:backend_ready
if not defined BACKEND_READY (
  echo [ERROR] Backend did not become healthy on http://127.0.0.1:8001/api/v1/health.
  echo [INFO] Stopping local site...
  for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do taskkill /F /PID %%P > nul 2> nul
  exit /b 1
)

echo [OK] Backend health is ready.
echo [INFO] Starting frontend...
start "PNL_FRONTEND" /B cmd /c cd /d "%ROOT%" ^&^& npm run dev

echo [INFO] Close this window to stop the site, or press any key for cleanup.
pause > nul

echo [INFO] Stopping local site...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do taskkill /F /PID %%P > nul 2> nul
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do taskkill /F /PID %%P > nul 2> nul
echo [OK] Stopped.

endlocal
