# Project Context — NuriNamu AI Chat

## What this is

A production RAG chatbot answering Korean public-sector compliance questions
(청탁금지법, 이해충돌방지법, 행정심판법, 공익신고자보호법 등) with legal-grade
reasoning (FIRAC format), citation, and audit logging.

Target customer: 국민권익위원회 및 기타 공공기관 (조달청 납품 기준).

## Domain

- **Legal corpus**: 법령 전문, 시행령, 시행규칙, 판례, 질의응답집
- **FAQ corpus**: 청탁금지법 외부강의 질의회신집 등
- **Live data**: 국가법령정보센터 MCP 연동 (배치 전용, 쿼리 시점에는 조회 안 함)

## Core Capabilities

1. **Hybrid retrieval**: vector + full-text + RRF + cross-encoder rerank
2. **Metadata-aware filtering**: `law_category`, `act_type`, `subject_type`
   태그 기반 다단계 필터 폴백
3. **Knowledge graph expansion**: 인용된 조문 자동 확장 (`law_graph.py`)
4. **FIRAC-mode legal reasoning**: Fact → Issue → Rule → Analysis → Conclusion
5. **Multi-LLM routing**: router LLM + main LLM 분리 (비용 최적화)
6. **Audit & compliance**: 모든 요청 감사 로그 DB 기록, PII 마스킹,
   프롬프트 인젝션 차단
7. **Admin dashboard**: 13 Streamlit pages — 모니터링, 디버그, 온톨로지,
   문서 관리, 프롬프트 튜닝

## Out of Scope

- General-purpose chatbot (no small talk, no coding help)
- Non-Korean language answers
- Real-time 법령 변경 알림 (배치 주기 기반만 지원)

## Stakeholders & Constraints

- **납품 환경**: 공공기관, 망분리 환경 가능성 있음
- **보안 요건**: API Key 인증, CORS 화이트리스트, 감사 로그 필수,
  HTTPS 강제 (배포 가이드 참조)
- **성능 목표**: `/ask` p95 < 5s (streaming first-token < 1.5s)
- **비용 목표**: 월간 토큰 비용 < 50만원 (Gemini 2.5 Flash-lite 기준)

## Deployment Targets

- **Local**: `start_all.bat` — Windows + Ollama + Postgres 로컬
- **Cloud**: GCP Cloud Run + Supabase (pgvector) — 가이드는
  `docs/GCP_Supabase_배포가이드.md` (현재 P0 이슈 여러 건, 리뷰 대기)
