@echo off
chcp 65001 >nul
echo =========================================================
echo  🚀 MCP 연결 테스트용 경량 모드 기동 스크립트
echo  (AI 모델을 로드하지 않아 메모리를 절약합니다)
echo =========================================================

echo [DB/MCP 준비] 데이터베이스와 법제처 MCP 서버 기동 중...
:: 기존 배포된 Vector DB (govops_vector_db)는 자동 백그라운드 운용됨 (보장).
start "Korean Law MCP Server (Port 3000)" cmd /k "cd /d C:\korean-law-mcp-main && npm run start:sse"
timeout /t 3

echo [1/2] 백엔드 API 서버 (FastAPI) 기동 중...
:: AI 모델 없이 경량 모드로 서버를 켭니다.
start "GovOps Backend API (Port 8000)" cmd /k "cd .. && venv\Scripts\uvicorn.exe server.api_server:app --host 0.0.0.0 --port 8000"

echo [2/2] 프론트엔드 웹 서버 기동 중...
:: UI 서버를 켭니다.
start "GovOps Frontend UI (Port 8080)" cmd /k "cd .. && python -m http.server 8080 -d static"

echo.
echo 🎉 경량 테스트 서비스가 기동되었습니다!
echo 👉 웹 브라우저를 열고 http://localhost:8080 으로 접속하세요.
echo ⚠️ 중요: 이 모드는 MCP 연결 테스트 전용입니다.
echo =========================================================
pause