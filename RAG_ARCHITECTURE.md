# RAG Architecture — NuriNamu V3

## High-Level Flow

```
User → Next.js Frontend → FastAPI /ask (streaming SSE)
                              ↓
                          Input Guard (PII / injection)
                              ↓
                          RAGEngineV3 (rag/rag_engine.py)
                              ↓
           ┌──────────────────┼─────────────────┐
           ↓                  ↓                 ↓
      Query Tagger      Hybrid Retriever    History (DB)
   (metadata_tagger)  (advanced_retriever)
                              ↓
                      ┌───────┴────────┐
                      ↓                ↓
               Vector Search     Postgres FTS
               (pgvector)        (tsvector)
                      ↓                ↓
                      └──────→ RRF ←───┘
                              ↓
                    Graph Expansion (law_graph)
                              ↓
                    Cross-encoder Reranker
                              ↓
                    Context Merger (integrations/)
                              ↓
                    Prompt Assembly (FIRAC / Standard)
                              ↓
                    LLM Stream (Gemini / OpenAI / Ollama)
                              ↓
                    SSE → Frontend → Audit Log (async)
```

## Retrieval Stages

### Stage 1: Query Metadata Tagging
`indexer/metadata_tagger.py::tag_query()`
- LLM-based tagging (optional, times out gracefully)
- **Rule-based fallback runs unconditionally** (past incident fix)
- Produces: `{law_category, act_type, subject_type}` dict

### Stage 2: Adaptive Filter Levels
`retriever/advanced_retriever.py::_build_filter_levels()`
- Level 1: full metadata filter (strict)
- Level 2: law_category only (loose)
- Level 3: no filter (fallback)
- Returns first level yielding ≥3 results

### Stage 3: Parallel Hybrid Search
For each expanded query × each retrieval mode:
- `vectorstore.similarity_search(q, k=10, filter=level)` (pgvector)
- `fts_search(q, k=10, metadata_filter=...)` (Postgres tsvector)
- All tasks run concurrently via `asyncio.gather`

### Stage 4: Reciprocal Rank Fusion
`rrf_score()` merges results from all search arms with weighted
scores per content-type (`WEIGHT_CASE`, `WEIGHT_LEGAL`, `WEIGHT_FAQ`).

### Stage 5: Knowledge Graph Expansion
`_expand_with_law_graph()` — if a retrieved 조문 cites another 조문,
pull the cited text too.

### Stage 6: Cross-Encoder Rerank
`BAAI/bge-reranker-v2-m3` pairwise scores → top-k final.

## Indexing Pipeline

```
Upload (admin_pages/04_doc_manage.py)
  ↓
detect_doc_type()  →  legal | case | faq | general
  ↓
PDF Parser (llamaparse) / Excel / MD
  ↓
Chunking (per content-type strategy)
  ↓
Metadata Tagger (LLM batch, async semaphore)
  ↓
Embedding (bge-m3, CPU)
  ↓
pgvector INSERT + FTS tsvector GENERATED
```

## Key Invariants

1. **Never bypass the factory**: `get_retriever(DB_URL)` is the only
   entry point to the retrieval layer.

2. **Rule-based tagging is authoritative on LLM failure**:
   `_rule_based_fallback()` runs even when `tag_query()` LLM call raises.

3. **Filter strategy is multi-level**: never apply all filters blindly —
   always degrade gracefully when result count < threshold.

4. **Content-type drives weighting**: 판례 > 법령 > FAQ > 일반 in RRF scores.

5. **Streaming is SSE, not WebSocket**: SSE over HTTP/1.1 for firewall
   compatibility in 망분리 환경.

## Performance Notes

- Embedding (bge-m3 CPU): ~150ms per chunk — bottleneck of indexing
- Tagging (Gemini flash-lite): ~500ms per chunk at concurrency=5
- Retrieval (hybrid + rerank, k=10): ~300ms p50
- LLM first-token (Gemini 2.5 Flash): ~800ms
- LLM full answer (streaming): 2-5s typical
