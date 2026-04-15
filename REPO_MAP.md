# Repository Map — NuriNamu AI Chat

## Top-Level Layout

```
NuriNamuAiChat/
├── server/             FastAPI backend (source of truth for request flow)
├── rag/                RAG engine (RAGEngineV3, prompt assembly)
├── retriever/          Retrieval layer (factory + hybrid)
├── indexer/            Document ingestion, tagging, parsing
├── integrations/       MCP law client, context merger
├── monitoring/         Query logging
├── admin_pages/        Streamlit admin dashboard (13 pages)
├── admin_console.py    Streamlit multipage entrypoint
├── frontend/           Next.js chat UI
├── doc_archive/        Source documents (법령/판례/FAQ)
├── docs/               Manuals + deployment guides
├── scripts/            Windows .bat helpers
├── static/             Legacy HTML fallback UI (mounted at /)
├── tests/              Pytest
├── logs/               Runtime logs + target_files.json
├── .env                Runtime config (NEVER commit)
├── Dockerfile          Backend container (multi-stage)
├── docker-compose.yml  Local dev stack (backend + frontend + postgres)
└── requirements.txt    Python deps
```

## Module Responsibilities

### `server/`
- `api_server.py` — FastAPI app, `/ask`, `/health`, `/feedback`, `/config/ui`,
  `/sessions/*`. **Source of truth for request/lifecycle.**
- `api_server_cloud.py` — cloud-specific variant (verify before using)
- `db_manager.py` — asyncpg connection pool, session history, feedback CRUD
- `audit_logger.py` — async audit event insert (compliance)
- `input_guard.py` — PII masking + prompt injection detection

### `rag/`
- `rag_engine.py` — `RAGEngineV3`. Orchestrates tagging → retrieval →
  prompt → LLM stream. Reads feature flags from `.env` (FIRAC mode, etc.)
- `ontology_manager.py` — domain ontology (법률 분류 체계)

### `retriever/`
- `factory.py` — `get_retriever(db_url)` — single entry point
- `advanced_retriever.py` — `AdvancedHybridRetrieverV2`: vector + FTS + RRF +
  graph expansion + reranker
- `_hybrid_retriever.py` — legacy (do not import)

### `indexer/`
- `rag_indexer.py` — CLI entry for batch indexing. Reads `logs/target_files.json`
- `pdf_parser.py` — llamaparse / unstructured wrapper
- `metadata_tagger.py` — LLM + rule-based tagging. **Rule-based must run
  independently of LLM.**
- `law_graph.py` — 조문 인용 관계 그래프
- `law_scheduler.py` — 배치로 국가법령정보센터 MCP 호출, 변경 법령 적재
- `law_indexer.py` — 법령 전용 인덱싱 경로

### `integrations/`
- `mcp_law_client.py` — MCP protocol client for 국가법령정보센터
  (**배치 전용** — `/ask` 요청 경로에서는 호출하지 않음)
- `context_merger.py` — retrieved chunks → prompt context

### `admin_pages/` (Streamlit)
| File | Purpose |
|---|---|
| 01_monitor.py | 실시간 모니터링 |
| 02_benchmark.py | 성능 벤치마크 |
| 03_debug.py | 검색 디버그 (쿼리 확장 / 필터 / 결과 시각화) |
| 04_doc_manage.py | 문서 업로드 / 인덱싱 |
| 05_graph.py | 지식 그래프 뷰어 |
| 06_billing.py | LLM 토큰 사용량 / 비용 |
| 07_accuracy.py | 정확도 평가 |
| 08_security.py | 보안 설정 |
| 09_config.py | 환경 변수 관리 |
| 10_ontology.py | 온톨로지 편집 |
| 11_prompts.py | 프롬프트 튜닝 |
| 12_similarity_lab.py | 임베딩 유사도 실험 |
| 13_notebook_chat.py | 노트북 형식 대화 실험 |

### `frontend/`
- Next.js 14+ App Router (see `frontend/AGENTS.md` — custom fork)
- `src/app/page.tsx` — chat home
- `src/api/client.ts` — backend client (reads `NEXT_PUBLIC_API_BASE_URL`
  at build time — see Dockerfile for build-arg injection)
- `src/components/chat/` — ChatContainer, ChatBubble, ExportButton

### `scripts/`
- `run_indexer_bg.bat` — 인덱싱 백그라운드 실행 (로그 리다이렉트 충돌 회피)
- `start_all.bat`, `start_local.bat`, `start_cloud.bat` — 환경별 기동
- `start_admin_8502.bat` — 관리자 콘솔 단독 기동

## Data Flow

### Query flow
```
Frontend → /ask (SSE)
       → input_guard.check_and_sanitize
       → rag_engine.generate_stream
              → metadata_tagger.tag_query
              → advanced_retriever.retrieve
                    → pgvector + FTS → RRF → graph_expand → rerank
              → context_merger
              → LLM stream (chunked SSE)
       → audit_logger.log_audit_event (async)
```

### Indexing flow
```
admin_pages/04_doc_manage.py → upload → doc_archive/
       → rag_indexer.py (CLI or button)
              → detect_doc_type → legal | case | faq | general
              → pdf_parser / md / xlsx
              → chunking
              → metadata_tagger.tag_chunks (async semaphore)
              → embedding (bge-m3)
              → pgvector INSERT
```

## Do Not Touch (legacy/empty)
- `auth/` — empty dir, reserved
- `web/` — no longer used; UI lives in `frontend/` and `static/`
- `0.27.0` — stray file, ignore
- `old/` — legacy code, do not import
- `_delete_legacy_collections.py`, `_fix_phone.py`, `_list_collections.py`
  — one-off maintenance scripts, do not run blindly
