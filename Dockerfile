# ─── Backend (FastAPI) Dockerfile ───
FROM python:3.11-slim as builder

WORKDIR /app

# 이미지 크기 최적화를 위해 캐시 없이 설치
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 필수 패키지 설치 (psycopg2 등 컴파일용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Production Stage ───
FROM python:3.11-slim

WORKDIR /app

# 런타임 라이브러리만 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 빌더 스테이지에서 의존성 복사
COPY --from=builder /usr/local/lib/python3.11/site-packages/ /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# 소스 코드 복사
COPY . .

# 로그 디렉토리 권한 설정
RUN mkdir -p logs && chmod 777 logs

# 실행 환경 설정 (8000포트)
EXPOSE 8000

# Gunicorn을 통한 Production 서빙 (워커 수 자동 계산 가이드 반영 가능)
CMD ["uvicorn", "server.api_server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
