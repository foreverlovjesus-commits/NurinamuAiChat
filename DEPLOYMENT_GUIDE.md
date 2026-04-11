# NuriNamu AI Chat Enterprise 배포 가이드 (V4.1)

본 문서는 국민권익위원회 및 공공기관의 비즈니스 연속성을 보장하기 위한 **실제 서비스 배포용 인프라 권고안** 및 **최적화 가이드**를 담고 있습니다.

---

## 🏗️ 1. 하드웨어 사이징 권고 (Server Sizing)

RAG 시스템은 임베딩 연산과 LLM 토큰 생성 과정에서 상당한 리소스를 요구합니다. 동시 접속자 수에 따른 최적 스펙은 다음과 같습니다.

| 서비스 규모 | 동시 접속자 | 권장 스펙 (vCPU / RAM / GPU) | 비고 |
| :--- | :---: | :--- | :--- |
| **Small** | 5~10명 | 4 vCPU / 16GB RAM / (GPU 없음) | 내부 테스트 및 소규모 부서용 |
| **Medium** | 30~50명 | 8 vCPU / 32GB RAM / T4 GPU 16GB | 전 부서 공통 사용 (Ollama 로컬 구동 시) |
| **Large** | 100명+ | 16 vCPU / 64GB RAM / A100 40GB+ | 전사적 통합 서비스 및 실시간 대량 분석 |

> [!NOTE]
> **Gemini/GPT-4o 등 클라우드 API 사용 시:** GPU가 필요하지 않으므로 CPU와 RAM 위주로 구성하며, 네트워크 대역폭(Outbound) 확보가 중요합니다.
> **vCPU vs 일반 CPU:** 가상화된 환경(Cloud)에서의 CPU 코어를 의미하며, 물리 코어 1개는 통상 2 vCPU로 매핑됩니다.

---

## 🐳 2. 컨테이너 기반 배포 (Docker)

환경에 구애받지 않는 안정적인 구동을 위해 Docker 배포를 권장합니다.

### 백엔드 (FastAPI) 최적화
- **Worker 수:** `(2 * vCPU 코어 수) + 1` 권장. (8 vCPU 기준 17개 워커)
- **Timeout:** RAG 엔진의 검색 및 생성 시간을 고려하여 최소 `60s`~`120s`로 설정.

### 프론트엔드 (Next.js) 최적화
- **Standalone 모드:** `next.config.mjs`에서 `output: 'standalone'` 설정을 활성화하여 이미지 크기를 최소화하고 전송 속도를 높입니다.

---

## 🔒 3. 보안 하이닝 (Security Hardening)

1. **API Key 관리:** `.env` 파일은 절대 Git에 포함하지 않으며, AWS Secrets Manager 또는 HashiCorp Vault 연동을 권장합니다.
2. **CORS 제한:** `ALLOWED_ORIGINS` 환경 변수를 통해 실제 서비스 도메인만 허용하도록 화이트리스트를 관리합니다.
3. **DB 접속:** PostgreSQL은 반드시 전용 서브넷(Private Subnet)에 배치하고, 화이트리스트된 애플리케이션 서버에서만 접속을 허용합니다.

---

## 📈 4. 모니터링 및 로깅

- **Usage Tracker 로깅:** `usage_stats.db`를 정기적으로 백업하거나 중앙 집중식 로그 분석 도구(ELK/Grafana)로 전송합니다.
- **상태 체크:** `/health` 엔드포인트를 로드밸런서(LB)의 헬스체크 경로로 지정하여 무중단 배포(Blue-Green/Rolling)를 지원합니다.

---

## 🏁 결론
현재 구축된 **NuriNamu AI Chat V4**는 수평적 확장(Scale-out)이 가능한 구조로 설계되어 있습니다. 사용자가 급증할 경우 앱 서버(FastAPI) 인스턴스를 늘리는 것만으로도 대응이 가능합니다.
