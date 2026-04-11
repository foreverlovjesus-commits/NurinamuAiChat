@echo off
setlocal

echo [1/4] Starting MCP Server...
start "MCP" cmd.exe /k "cd /d C:\korean-law-mcp-main && npm run start:sse"

echo [2/4] Starting Backend...
start "Backend" cmd.exe /k "cd /d C:\NuriNamuAiChat && venv\Scripts\python.exe -m uvicorn server.api_server:app --reload --port 8000"

echo [3/4] Starting Frontend...
start "Frontend" cmd.exe /k "cd /d C:\NuriNamuAiChat\frontend && npm run dev"

echo [4/4] Starting Admin...
start "Admin (Integrated)" cmd.exe /k "cd /d C:\NuriNamuAiChat && venv\Scripts\python.exe -m streamlit run admin_console.py --server.port 8502"

echo All services launched!
pause
