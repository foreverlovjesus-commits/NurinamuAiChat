@echo off
title RAG Chatbot - Cloud Mode

cd /d "%~dp0"

echo.
echo  ================================
echo   RAG Chatbot - Cloud (Gemini)
echo   URL : http://localhost:8001
echo  ================================
echo.

echo [1/2] Starting Cloud API Server (port 8001)...
start "Cloud API Server" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m uvicorn server.api_server_cloud:app --host 0.0.0.0 --port 8001"

echo  Waiting 5 sec...
timeout /t 5 /nobreak > nul

echo [2/2] Starting Cloud UI (port 8502)...
start "Cloud Chat UI" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe -m streamlit run web/chat_ui_cloud.py --server.port 8502"

timeout /t 8 /nobreak > nul
start "" "http://localhost:8502"

echo.
echo  Done! Open http://localhost:8502
echo.
pause
