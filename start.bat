@echo off
cd /d "%~dp0"
echo Starting Video RAG Analyst...

echo.
echo Freeing port 8000 if a stale process is holding it...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr LISTENING') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo [1/2] Starting FastAPI backend on port 8000...
start cmd /k "cd /d %~dp0backend && uvicorn main:app --reload --host 127.0.0.1 --port 8000"

timeout /t 3

echo [2/2] Starting React frontend on port 3000...
start cmd /k "cd /d %~dp0frontend && npm start"

echo.
echo Both servers starting!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo API Docs: http://localhost:8000/docs
