@echo off
title RAG Chatbot - Local Mode

cd /d "%~dp0"

echo.
echo  ================================
echo   RAG Chatbot - Local (Ollama)
echo   URL : http://localhost:8000
echo  ================================
echo.

echo [1/2] Checking Ollama...
curl -s http://localhost:11434 > nul 2>&1
if %errorlevel% neq 0 (
    echo  WARNING: Ollama is not running.
    echo  Please run 'ollama serve' first.
    pause
    exit /b 1
)
echo  OK - Ollama is running.

echo [2/2] Starting API + UI Server (port 8000)...
start "RAG API Server" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn server.api_server:app --host 0.0.0.0 --port 8000 --reload"

echo  Waiting for server warmup (15 sec)...
timeout /t 15 /nobreak > nul

start "" "http://localhost:8000"

echo.
echo  Done! Open http://localhost:8000
echo.
pause
