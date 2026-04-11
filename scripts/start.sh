#!/bin/bash

# --- ⚡ 챗봇 시스템 가동 스크립트 ---

echo "🚀 시스템 가동을 시작합니다..."

# 1. 가상환경 활성화
source venv/bin/activate

# 2. 백엔드 API 서버 실행 (FastAPI - 8000포트)
echo "[1/2] 백엔드 서버 실행 중 (Port: 8000)..."
nohup uvicorn server.api_server:app --host 0.0.0.0 --port 8000 --workers 4 > logs/api_server.log 2>&1 &
echo $! > logs/api_server.pid

# 3. 프론트엔드 UI 실행 (Streamlit - 8501포트)
echo "[2/2] 프론트엔드 UI 실행 중 (Port: 8501)..."
nohup streamlit run web/chat_ui_v2.py --server.port 8501 --server.address 0.0.0.0 > logs/chat_ui.log 2>&1 &
echo $! > logs/chat_ui.pid

echo "==========================================="
echo "✅ 시스템 가동 완료!"
echo "📡 API: http://서버IP:8000"
echo "🖥️  UI:  http://서버IP:8501"
echo "==========================================="
