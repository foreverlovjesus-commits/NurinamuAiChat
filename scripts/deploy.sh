#!/bin/bash

# --- 🚀 GovOps RAG System Deploy Script ---
# 대상 OS: Rocky Linux / CentOS

echo "==========================================="
echo "  📦 챗봇 시스템 배포를 시작합니다 (Linux)  "
echo "==========================================="

# 1. 필수 폴더 생성
mkdir -p logs
mkdir -p doc_archive
mkdir -p temp

# 2. 파이썬 가상환경 구축
if [ ! -d "venv" ]; then
    echo "[1/3] 가상환경(venv) 생성 중..."
    python3.11 -m venv venv
fi

# 3. 라이브러리 설치
source venv/bin/activate
echo "[2/3] 파이썬 패키지 설치 중..."

# 폐쇄망 모드 확인 (offline_libs 폴더 존재 여부)
if [ -d "offline_libs" ]; then
    echo "🔗 폐쇄망 모드: 로컬 패키지 설치를 진행합니다."
    pip install --no-index --find-links=./offline_libs -r requirements.txt
else
    echo "🌐 온라인 모드: PyPI에서 패키지를 다운로드합니다."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# 4. 보안 키 점검
if [ ! -f ".env" ]; then
    echo "[3/3] .env 파일이 없습니다. 설정을 진행하세요."
    cp .env.example .env 2>/dev/null || touch .env
else
    echo "[3/3] 기존 .env 설정을 유지합니다."
fi

echo "==========================================="
echo "✅ 배포 완료! './scripts/start.sh'로 실행하세요."
echo "==========================================="
