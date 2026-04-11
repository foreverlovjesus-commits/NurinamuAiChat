@echo off
setlocal
cd /d "%~dp0"

echo.
echo  ================================
echo   NuriNamu Admin Dashboard (8502)
echo   URL : http://localhost:8502
echo  ================================
echo.

echo [1/2] Checking Python Virtual Environment...
if not exist venv (
    echo  ERROR: venv not found. Please run setup first.
    pause
    exit /b 1
)

echo [2/2] Starting Streamlit Admin Dashboard on port 8502...
venv\Scripts\python.exe -m streamlit run admin_console.py --server.port 8502
