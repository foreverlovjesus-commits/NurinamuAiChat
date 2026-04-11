# 누리나무 AI 법률통합지원 시스템 — 운영자(관리자) 매뉴얼

**문서 번호**: NNA-AM-2026-001  
**버전**: v4.1  
**최종 수정일**: 2026년 4월  
**대상**: 시스템 운영자, IT 관리자

---

## 1. 시스템 구성도

```
[사용자 브라우저]
      │ HTTPS
      ▼
[Next.js 프론트엔드 :3000]
      │ HTTP/REST (내부망)
      ▼
[FastAPI 백엔드 :8000]
    │         │         │
    ▼         ▼         ▼
[PostgreSQL]  [MCP     [Ollama /
[+ pgvector]  법령서버] 클라우드 LLM]
```

---

## 2. 서비스 시작 / 중지

### 2.1 전체 시작

```powershell
# 프로젝트 루트에서 실행
cd C:\NuriNamuAiChat
.\start_all.bat
```

### 2.2 개별 서비스 제어

```powershell
# 백엔드 서버만 시작
python -m uvicorn server.api_server:app --host 0.0.0.0 --port 8000

# 프론트엔드만 시작
cd frontend
npm run dev

# 관리자 대시보드
python -m streamlit run admin_dashboard.py --server.port 8501

# MCP 법령 서버
cd integrations/mcp-law-server
node server.js
```

### 2.3 전체 중지

```powershell
.\stop_all.bat
```

---

## 3. 환경 변수 설정

주요 설정 파일: `.env` (루트 디렉토리)

```
# 필수 보안 설정 (⚠️ 빈값 금지)
API_KEY=<32자 이상 랜덤 문자열>
ALLOWED_ORIGINS=https://시스템도메인.go.kr
NODE_ENV=production

# DB 연결
DATABASE_URL=postgresql://user:pass@host:5432/db_name

# LLM 설정
GLOBAL_LLM_PROVIDER=gemini
GOOGLE_API_KEY=<Gemini API Key>

# Rate Limit (IP당 분당 요청 수)
RATE_LIMIT_PER_MINUTE=30/minute
```

---

## 4. 관리자 대시보드 (`http://[서버]:8501`)

| 탭 | 기능 |
|-----|------|
| 배치 모니터링 | 문서 색인 진행 상황, 재색인 실행 |
| 모델 성능 비교 | 임베딩 모델별 검색 성능 비교 |
| 검색 디버그 | 벡터 검색 결과 디버깅 |
| 문서 관리 | 색인 문서 목록, 개별 삭제 |
| API 사용량 | LLM 토큰 사용량 및 비용 추적 |
| 환경 설정 | API Key, 임베딩 모델 변경 |

---

## 5. 문서 색인 (RAG 지식베이스 관리)

### 5.1 문서 추가

1. `doc_archive/` 폴더에 PDF/DOCX/HWP 파일 복사
2. 관리자 대시보드 → **배치 모니터링** → **전체 문서 재색인 실행**
3. 진행 상황 실시간 확인 (완료까지 파일당 수 분 소요)

### 5.2 문서 삭제

1. 관리자 대시보드 → **문서 관리** 탭
2. 삭제할 파일 선택 → **선택 삭제**

---

## 6. 로그 확인

### 6.1 로그 파일 위치

| 로그 종류 | 경로 |
|---------|------|
| 백엔드 API 로그 | `logs/api_server.log` |
| 문서 색인 로그 | `logs/indexer.log` |
| 감사 로그 (Audit) | DB `audit_log` 테이블 또는 서버 로그 |

### 6.2 실시간 로그 확인

```powershell
# 백엔드 로그 실시간 확인 (PowerShell)
Get-Content -Path "logs\api_server.log" -Wait -Tail 100
```

---

## 7. 백업 및 복구

### 7.1 DB 백업

```powershell
# 전체 백업
pg_dump -h localhost -U nurinamu_admin nurinamu_chat_db > backup_$(Get-Date -Format "yyyyMMdd").sql

# 자동 백업 (작업 스케줄러 등록 권장)
```

### 7.2 복구

```powershell
# DB 복구
psql -h localhost -U nurinamu_admin nurinamu_chat_db < backup_20260408.sql
```

---

## 8. 장애 대응 절차 (Runbook)

### Case 1: 서비스 완전 중단 (P1)

```
1. 서비스 상태 확인: curl http://localhost:8000/health
2. 프로세스 확인: Get-Process python, node
3. 로그 확인: logs/api_server.log 마지막 100줄
4. DB 연결 확인: psql 접속 테스트
5. 재시작: .\start_all.bat
6. 30분 내 미복구 시 → 에스컬레이션
```

### Case 2: AI 답변 품질 저하

```
1. admin_dashboard → 검색 디버그 탭에서 검색 테스트
2. 임베딩 모델 상태 확인 (Ollama: ollama list)
3. LLM API 할당량 확인 (admin → API 사용량 탭)
4. 필요 시 임베딩 모델 재선택 및 재색인
```

### Case 3: DB 용량 부족

```
1. 불필요한 컬렉션 확인: admin → 문서 관리
2. 중복 임베딩 컬렉션 삭제
3. DB 스토리지 증설 요청
```

---

## 9. 성능 모니터링 체크리스트

**일간 점검 (자동화 권장)**
- [ ] 헬스체크 엔드포인트 응답 정상 (`/health`)
- [ ] 디스크 사용량 80% 미만
- [ ] 에러 로그 이상 급증 여부

**주간 점검**
- [ ] API 사용량 및 예상 비용 확인
- [ ] 백업 파일 정상 생성 확인
- [ ] 감사 로그 이상 패턴 검토

**월간 점검**
- [ ] 보안 패치 적용 현황 검토
- [ ] SLA 달성률 보고서 작성
- [ ] 사용자 피드백 데이터 검토

---

## 10. 비상 연락처

| 역할 | 담당자 | 연락처 |
|------|--------|--------|
| 시스템 운영 | 운영기관 IT팀 | (운영기관 설정) |
| LLM API 장애 | Google Cloud 지원 | support.google.com |
| 공급사 긴급 | NuriNamu 개발팀 | (계약서 참조) |
