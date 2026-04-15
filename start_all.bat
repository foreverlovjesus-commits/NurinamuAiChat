@echo off
title RAG Chatbot - All Services

cd /d "%~dp0"

echo.
echo  ================================
echo   RAG Chatbot - All Services
echo   Local  : http://localhost:8000
echo   Cloud  : http://localhost:8001
echo  ================================
echo.

echo [1/2] Starting Local API (port 8000)...
start "RAG Local API" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn server.api_server:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Starting Cloud API (port 8001)...
start "RAG Cloud API" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn server.api_server_cloud:app --host 0.0.0.0 --port 8001 --reload"

echo  Waiting 15 sec...
timeout /t 15 /nobreak > nul

start "" "http://localhost:8000"

echo.
echo  Done!
echo  Local : http://localhost:8000
echo  Cloud : http://localhost:8001
echo.
pause
