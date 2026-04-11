# 누리나무 AI 법률통합지원 시스템 — 오픈소스 컴포넌트 목록 (SBOM)

**문서 번호**: NNA-SBOM-2026-001  
**버전**: v1.0  
**최종 수정일**: 2026년 4월  
**목적**: 조달청 납품 요건 충족 및 오픈소스 라이선스 리스크 관리

---

## 1. 백엔드 (Python / FastAPI)

| 패키지명 | 버전 | 라이선스 | 용도 |
|---------|------|---------|------|
| fastapi | ≥0.115 | MIT | API 웹 프레임워크 |
| uvicorn | ≥0.34 | BSD-3 | ASGI 서버 |
| pydantic | ≥2.0 | MIT | 데이터 검증 |
| python-dotenv | ≥1.0 | BSD-3 | 환경변수 관리 |
| slowapi | ≥0.1 | MIT | Rate Limiting |
| cryptography | ≥44.0 | Apache-2.0 | 암호화 처리 |
| psycopg2-binary | ≥2.9 | LGPL-3.0 | PostgreSQL 드라이버 |
| langchain | ≥0.3 | MIT | LLM 파이프라인 |
| langchain-community | ≥0.3 | MIT | 커뮤니티 통합 |
| langchain-google-genai | ≥2.0 | MIT | Google Gemini 연동 |
| langchain-openai | ≥0.3 | MIT | OpenAI 연동 |
| langchain-anthropic | ≥0.3 | MIT | Anthropic 연동 |
| langchain-huggingface | ≥0.1 | MIT | HuggingFace 임베딩 |
| sentence-transformers | ≥3.0 | Apache-2.0 | 로컬 임베딩 모델 |
| pgvector | ≥0.3 | MIT | 벡터 DB (PostgreSQL) |
| streamlit | ≥1.40 | Apache-2.0 | 관리자 대시보드 |
| pandas | ≥2.2 | BSD-3 | 데이터 처리 |
| httpx | ≥0.28 | BSD-3 | HTTP 클라이언트 (MCP) |
| pymupdf | ≥1.25 | AGPL-3.0 ⚠️ | PDF 파싱 |
| python-docx | ≥1.0 | MIT | DOCX 파싱 |

> ⚠️ **PyMuPDF (AGPL-3.0)**: AGPL 라이선스는 소스코드 공개 의무가 있습니다. 공공기관 납품 시 법무 검토가 필요합니다. 대안: `pypdf` (MIT) 또는 `pdfplumber` (MIT)

---

## 2. 프론트엔드 (Next.js / TypeScript)

| 패키지명 | 버전 | 라이선스 | 용도 |
|---------|------|---------|------|
| next | 15.x | MIT | React 프레임워크 |
| react | 19.x | MIT | UI 라이브러리 |
| react-dom | 19.x | MIT | DOM 렌더링 |
| typescript | 5.x | Apache-2.0 | 타입 시스템 |
| react-markdown | ≥9.0 | MIT | 마크다운 렌더링 |
| remark-gfm | ≥4.0 | MIT | GFM 마크다운 |
| lucide-react | ≥0.464 | ISC | 아이콘 라이브러리 |
| clsx | ≥2.1 | MIT | 조건부 CSS 클래스 |
| tailwind-merge | ≥2.5 | MIT | Tailwind 병합 |
| tailwindcss | 4.x | MIT | CSS 유틸리티 |

---

## 3. 외부 폰트 / CDN 리소스

| 리소스 | 출처 | 라이선스 | 용도 |
|--------|------|---------|------|
| Pretendard | jsDelivr CDN (GitHub) | SIL OFL 1.1 | 공공기관 표준 웹폰트 |

---

## 4. 라이선스 호환성 검토

| 라이선스 | 상업적 이용 | 특허 보호 | 소스 공개 의무 | 납품 적합성 |
|---------|----------|---------|-------------|-----------|
| MIT | ✅ | ❌ | ❌ | ✅ 적합 |
| Apache-2.0 | ✅ | ✅ | ❌ | ✅ 적합 |
| BSD-3 | ✅ | ❌ | ❌ | ✅ 적합 |
| ISC | ✅ | ❌ | ❌ | ✅ 적합 |
| SIL OFL 1.1 | ✅ (폰트) | — | ❌ | ✅ 적합 |
| LGPL-3.0 | ✅ | ✅ | 라이브러리 부분만 | ⚠️ 요주의 |
| AGPL-3.0 | ✅ | ✅ | ✅ (전체 소스) | ⚠️ **요주의** |

---

## 5. 취약점 점검 방법

```powershell
# Python 패키지 취약점 스캔
pip install pip-audit
pip-audit

# Node.js 패키지 취약점 스캔
cd frontend
npm audit
```

---

## 6. 업데이트 정책

- **Critical CVE**: 발견 즉시 패치 (72시간 이내)
- **High CVE**: 30일 이내 패치
- **Medium/Low**: 분기별 정기 업데이트 시 검토

---

*본 문서는 패키지 업데이트 시 갱신되어야 합니다.*
