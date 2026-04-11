#!/bin/bash

echo "========================================================="
echo " 🚀 GovOps AI 운영 환경(Production) 일괄 기동 스크립트"
echo "========================================================="

# 로그 폴더 확인
mkdir -p logs

# 1. Ollama 서비스 기동 (보통 systemctl로 켜져 있으나 체크용)
echo "[1/3] Ollama AI 엔진 상태 확인..."
if ! pgrep -x "ollama" > /dev/null; then
    nohup ollama serve > logs/ollama.log 2>&1 &
    echo "  -> Ollama 데몬을 백그라운드에서 시작했습니다."
fi

# 가상환경 활성화
source venv/bin/activate

# 2. 백엔드 API 서버 기동 (Gunicorn + Uvicorn 다중 워커)
echo "[2/3] 백엔드 API 서버 (Gunicorn, Port 8000) 기동 중..."
# 기존 프로세스가 있다면 종료
pkill -f "gunicorn api_server:app"
cd server
nohup gunicorn api_server:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000 > ../logs/api_server.log 2>&1 &
cd ..
echo "  -> 백엔드 서버가 백그라운드에서 실행되었습니다."

# 3. 프론트엔드 웹 서버 기동
echo "[3/3] 프론트엔드 웹 서버 (Port 8080) 기동 중..."
pkill -f "python3 -m http.server 8080"
nohup python3 -m http.server 8080 > logs/frontend.log 2>&1 &
echo "  -> 프론트엔드 서버가 백그라운드에서 실행되었습니다."

# 4. 백그라운드 법령 인덱싱 스케줄러 기동 (Phase 2)
echo "[4/4] 법령 데이터 동기화 스케줄러 기동 중..."
pkill -f "python ../indexer/law_scheduler.py"
nohup python ../indexer/law_scheduler.py > logs/law_scheduler.log 2>&1 &
echo "  -> 법령 스케줄러가 백그라운드에서 실행되었습니다."

echo -e "\n🎉 모든 운영 서비스가 기동되었습니다!"
echo "👉 서비스 접속: http://[서버IP]:8080"
echo "👉 실시간 백엔드 로그 확인: tail -f logs/api_server.log"
echo "👉 스케줄러 로그 확인: tail -f logs/law_scheduler.log"
echo "========================================================="