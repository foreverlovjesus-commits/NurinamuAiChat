#!/bin/bash

# --- 🛑 챗봇 시스템 중지 스크립트 ---

echo "🛑 시스템 종료를 시작합니다..."

# 1. 백엔드 서버 중지
if [ -f "logs/api_server.pid" ]; then
    PID=$(cat logs/api_server.pid)
    echo "[1/2] 백엔드 서버 종료 중 (PID: $PID)..."
    kill $PID
    rm logs/api_server.pid
else
    echo "[1/2] 종료할 백엔드 서버 프로세스가 없습니다."
fi

# 2. 프론트엔드 UI 중지
if [ -f "logs/chat_ui.pid" ]; then
    PID=$(cat logs/chat_ui.pid)
    echo "[2/2] 프론트엔드 UI 종료 중 (PID: $PID)..."
    kill $PID
    rm logs/chat_ui.pid
else
    echo "[2/2] 종료할 UI 프로세스가 없습니다."
fi

# 💡 강제 종료가 필요한 경우 (포트 기준)
# fuser -k 8000/tcp 2>/dev/null
# fuser -k 8501/tcp 2>/dev/null

echo "==========================================="
echo "✅ 시스템이 완전히 종료되었습니다."
echo "==========================================="
