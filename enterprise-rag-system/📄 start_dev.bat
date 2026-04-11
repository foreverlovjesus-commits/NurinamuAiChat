@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: =========================================================
::  🚀 NuriNamu AI Chat (v4.1) 개발 환경 통합 기동 스크립트
::  구성: Ollama, MCP Server, Backend API, Frontend UI, Admin
:: =========================================================

echo.
echo [1/5] 로컬 AI 엔진 (Ollama) 상태 확인...
:: Ollama 기본 포트 11434 확인 및 필요 시 기동
netstat -ano | findstr :11434 >nul
if %errorlevel% neq 0 (
    echo    - Ollama 서비스가 실행되지 않아 기동을 시도합니다...
    start "Ollama Engine" /B ollama serve >nul 2>&1
    timeout /t 3 >nul
) else (
    echo    - Ollama 서비스가 이미 실행 중입니다.
)

echo.
echo [2/5] 법령 검색 MCP 서버 (Port 3000) 기동...
:: 국가법령정보센터 실시간 연동 서버
start "Korean Law MCP Server" cmd /k "cd /d C:\korean-law-mcp-main && npm run start:sse"
timeout /t 4 >nul

echo.
echo [3/5] 백엔드 RAG API 서버 (Port 8000) 기동...
:: FastAPI + Uvicorn (핫 리로드 모드)
start "NuriNamu Backend API" cmd /k "cd /d C:\NuriNamuAiChat && venv\Scripts\python.exe -m uvicorn server.api_server:app --reload --host 0.0.0.0 --port 8000"

echo.
echo [4/5] 프론트엔드 인터페이스 (Port 3001) 기동...
:: Next.js 개발 서버
start "NuriNamu Frontend UI" cmd /k "cd /d C:\NuriNamuAiChat\frontend && npm run dev"

echo.
echo [5/5] 엔터프라이즈 통합 관리 도구 (Port 8501) 기동...
:: Streamlit 어드민 대시보드
start "NuriNamu Admin Dashboard" cmd /k "cd /d C:\NuriNamuAiChat && venv\Scripts\python.exe -m streamlit run admin_dashboard.py"

echo.
echo =========================================================
echo 🎉 NuriNamu Enterprise RAG 시스템 기동 완료!
echo =========================================================
echo  💡 접속 정보:
echo  - 사용자 채팅봇: http://localhost:3001
echo  - 관리 대시보드: http://localhost:8501
echo  - API 문서(Docs): http://localhost:8000/docs
echo  - 법령 MCP 헬스: http://localhost:3000/health
echo =========================================================
echo ※ 스케줄링 임베딩 프로세스는 사용자 요청에 따라 제외되었습니다.
echo.
pause