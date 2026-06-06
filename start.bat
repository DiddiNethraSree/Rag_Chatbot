@echo off
echo Starting Video RAG Analyst...

echo.
echo [1/2] Starting FastAPI backend on port 8000...
start cmd /k "cd backend && uvicorn main:app --reload --port 8000"

timeout /t 3

echo [2/2] Starting React frontend on port 3000...
start cmd /k "cd frontend && npm start"

echo.
echo Both servers starting!
echo Backend: http://localhost:8000
echo Frontend: http://localhost:3000
echo API Docs: http://localhost:8000/docs
