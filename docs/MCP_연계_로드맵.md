# Korean Law MCP 연계 로드맵

> Phase 1(MCP 외부 도구 호출)은 구현 완료.
> 본 문서는 Phase 2, 3 추가 작업 시 참고용.

---

## 현재 상태 (Phase 1 — 구현 완료)

Router LLM이 질문을 `"법령검색"`으로 분류하면, MCP HTTP API를 호출하여 법제처 실시간 법령 데이터를 가져와 답변에 활용한다.

```
사용자 질문 → Router → "법령검색" → MCP 서버 (HTTP) → 법제처 API → LLM 답변
                     → 그 외     → 기존 RAG (PGVector) → LLM 답변
```

**관련 파일:**
- `integrations/mcp_law_client.py` — MCP HTTP 클라이언트 (세션 관리, 도구 호출, 도구 선택)
- `rag/rag_engine.py` — `classify_category()`에 "법령검색" 추가, `generate_stream()`에 MCP 분기
- `server/api_server.py` — lifespan에서 `McpLawClient` 초기화/정리

---

## Phase 2: MCP 법령 데이터를 RAG 지식 베이스에 인덱싱

### 목표

핵심 법령(청탁금지법, 행정심판법, 국민권익위원회법 등)을 MCP로 가져와 PGVector에 미리 인덱싱.
기존 Retriever가 내부 문서와 법령을 **함께 검색**하므로 런타임 MCP 호출 없이도 법령 기반 답변 가능.

### 아키텍처

```
[배치 프로세스 — 주 1회 또는 수동 실행]

  law_indexer.py
    │
    ├─ MCP call_tool("search_law", {"query": "청탁금지법"})
    │   → 법령 목록 + MST 번호 획득
    │
    ├─ MCP call_tool("get_law_text", {"mst": "..."})
    │   → 전체 법령 텍스트 획득
    │
    ├─ chunk_legal() (rag_indexer.py의 기존 함수 재사용)
    │   → 제X조 단위로 분할
    │
    ├─ BAAI/bge-m3 임베딩 생성
    │
    └─ PGVector 저장
        metadata: {source_type: "법제처API", law_mst: "...", doc_type: "legal_api", fetched_at: "..."}

[런타임 — 변경 없음]

  사용자 질문 → Retriever → Vector+FTS+Rerank → 내부문서 + 법령 모두 검색됨
```

### 생성할 파일

| 파일 | 설명 |
|------|------|
| `indexer/law_indexer.py` | MCP에서 법령 가져와 PGVector에 인덱싱 |
| `scripts/sync_laws.py` | CLI 래퍼 — Task Scheduler/cron으로 주기적 실행 |

### 수정할 파일

| 파일 | 변경 내용 |
|------|-----------|
| `indexer/rag_indexer.py` | `chunk_legal()` 함수를 별도 모듈(`chunking_utils.py`)로 추출하여 재사용 가능하게 |

### 핵심 구현 사항

1. **대상 법령 목록 설정**: 국민권익위원회 업무 관련 핵심 법령
   - 청탁금지법 (부정청탁 및 금품등 수수의 금지에 관한 법률)
   - 행정심판법
   - 국민권익위원회의 설치와 운영에 관한 법률
   - 부패방지 및 국민권익위원회의 설치와 운영에 관한 법률
   - 이해충돌방지법 (공직자의 이해충돌 방지법)
   - 민원 처리에 관한 법률
   - 행정절차법

2. **MCP 호출 속도 제한**: 법제처 API + MCP 서버 rate limit (60 req/min) 고려
   - 법령 1개 = search_law(1회) + get_law_text(1회) = 2 API 호출
   - 7개 법령 = 약 14회 → 1분 이내 완료 가능
   - 대량 인덱싱 시 호출 간 1초 딜레이 추가1

3. **변경 감지**: `공포일자`(promulgation date) 비교로 재인덱싱 여부 판단
   - 이미 인덱싱된 법령의 공포일자가 동일하면 스킵
   - 변경된 경우만 기존 문서 삭제 후 재인덱싱

4. **메타데이터 태깅**: `source_type: "법제처API"`로 파일 기반 문서와 구분
   - Retriever는 변경 없이 동일 컬렉션에서 모두 검색

### 장단점

| 장점 | 단점 |
|------|------|
| 런타임 MCP 의존 없음 (오프라인 동작) | 데이터 신선도 — 동기화 주기에 따라 최신 개정 반영 지연 |
| 기존 RAG 파이프라인 변경 없음 | 스케줄링 인프라 필요 (Task Scheduler / cron) |
| 법령이 벡터 DB에 있으므로 유사 검색 가능 | 판례는 양이 방대하여 선별적 인덱싱 필요 |
| Phase 1과 **병행** 가능 (인덱싱 + 실시간 보완) | 스토리지 증가 (법령 조문 수 × 벡터 차원) |

### 예상 노력: 5~7일

---

## Phase 3: 통합 게이트웨이 (Hybrid 라우팅)

### 목표

Router를 3경로(`rag` / `law` / `hybrid`)로 확장하여, 질문 성격에 따라:
- **rag**: 내부 문서만 (기존)
- **law**: 법제처 실시간 법령만 (Phase 1)
- **hybrid**: 내부 문서 + 법제처 법령 **병렬 실행 후 컨텍스트 병합**

### 아키텍처

```
사용자 질문
    ↓
Enhanced Router LLM
    ↓ JSON 출력: {route_type, category, tool_hint, reason}
    │
    ├─ route_type: "rag"
    │   → Retriever (Vector+FTS+Rerank)
    │   → 내부 문서 컨텍스트
    │   → Main LLM 답변
    │
    ├─ route_type: "law"
    │   → MCP call_tool (chain_full_research 등)
    │   → 법제처 법령 컨텍스트
    │   → Main LLM 답변
    │
    └─ route_type: "hybrid"
        → asyncio.gather(
            Retriever.retrieve(question),
            McpLawClient.call_tool(tool, args)
          )
        → context_merger.merge_contexts()
            - 중복 제거 (같은 법령 조문이 양쪽에 있을 때)
            - 출처 라벨링: [법제처 실시간] vs [내부 문서]
            - MCP 결과 우선 (더 권위적/최신)
            - 토큰 예산 관리 (~4000 토큰)
        → Main LLM 답변 (통합 컨텍스트)
```

### 생성할 파일

| 파일 | 설명 |
|------|------|
| `rag/unified_engine.py` | `RAGEngineV3`를 확장한 `UnifiedRAGEngine` — 3경로 라우팅 |
| `integrations/context_merger.py` | RAG + MCP 결과 병합 로직 (중복 제거, 우선순위, 토큰 관리) |

### 수정할 파일

| 파일 | 변경 내용 |
|------|-----------|
| `rag/rag_engine.py` | `classify_category()` 메서드를 서브클래스에서 오버라이드 가능하도록 리팩토링 |
| `server/api_server.py` | `RAGEngineV3` → `UnifiedRAGEngine`으로 교체 |
| `static/index.html` | SSE `law_source` 이벤트 처리 → 출처 구분 UI 렌더링 |
| `docker-compose.yml` | MCP 서버를 Docker 서비스로 추가 |

### 핵심 구현 사항

1. **Enhanced Router 프롬프트**

```python
ROUTER_PROMPT = """
당신은 질문 분류 전문가입니다.

분류 기준:
1. route_type:
   - "rag": 내부 문서(지침, 매뉴얼, FAQ)로 답변 가능한 질문
   - "law": 현행 법령, 판례, 해석례 등 법제처 데이터가 필요한 질문
   - "hybrid": 내부 규정과 법령 모두 필요한 질문
     예) "우리 기관의 청탁금지법 위반 처리 절차는?" → 내부 지침 + 법령 모두 필요
2. category: [국민신문고, 청렴포털, 행정심판, 청탁금지법, 법령검색, 일반 Q&A]
3. tool_hint: law/hybrid일 때 사용할 MCP 도구
   - search_law: 특정 법령 검색
   - chain_full_research: 종합 리서치 (기본값)
   - search_precedents: 판례 검색

JSON으로 출력:
{"route_type": "...", "category": "...", "tool_hint": "...", "reason": "..."}
"""
```

2. **Hybrid 병렬 실행**

```python
async def generate_stream(self, question):
    route = await self.classify_and_route(question)

    if route["route_type"] == "hybrid":
        rag_task = asyncio.create_task(self.retriever.retrieve(question, final_k=3))
        mcp_task = asyncio.create_task(
            self.mcp_client.call_tool(route["tool_hint"], {"query": question})
        )
        rag_docs, mcp_text = await asyncio.gather(rag_task, mcp_task, return_exceptions=True)

        # 에러 핸들링 — 한쪽 실패 시 다른 쪽만 사용
        if isinstance(rag_docs, Exception):
            rag_docs = []
        if isinstance(mcp_text, Exception):
            mcp_text = ""

        context = merge_contexts(rag_docs, mcp_text, question)
    elif route["route_type"] == "law":
        mcp_text = await self.mcp_client.call_tool(route["tool_hint"], {"query": question})
        context = f"[법제처 실시간 법령]\n{mcp_text}"
    else:
        docs = await self.retriever.retrieve(question, final_k=3)
        context = build_rag_context(docs)
```

3. **Context Merger 로직**

```python
def merge_contexts(rag_docs, mcp_text, question, max_tokens=4000):
    """
    1. MCP 결과를 [법제처 실시간] 라벨로 앞에 배치 (권위적 소스 우선)
    2. RAG 문서 중 MCP와 동일 법령 조문이면 제외 (중복 제거)
    3. 나머지 RAG 문서를 [내부 문서] 라벨로 뒤에 배치
    4. 합산 토큰이 max_tokens 초과 시 RAG 문서부터 절삭
    """
```

4. **UI 출처 표시** (SSE 이벤트)

```javascript
// 기존 이벤트에 추가
// data: {"type": "law_source", "content": "법제처 (open.law.go.kr)", "tool": "chain_full_research"}

if (data.type === 'law_source') {
    // "⚖️ 법제처 실시간 법령 데이터 활용" 배지 렌더링
}
```

5. **Docker Compose 추가**

```yaml
# docker-compose.yml에 추가
mcp-law:
  build:
    context: ../korean-law-mcp-main
    dockerfile: Dockerfile
  container_name: mcp-law-server
  ports:
    - "3000:3000"
  environment:
    LAW_OC: ${LAW_OC}
  command: ["node", "build/index.js", "--mode", "http", "--port", "3000"]
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "wget", "-q", "--spider", "http://localhost:3000/health"]
    interval: 30s
    timeout: 5s
    retries: 3
```

6. **Graceful Degradation**

```
MCP 서버 다운 → hybrid 요청이 rag로 자동 fallback
MCP 타임아웃   → 내부 문서만으로 답변 + "법령 데이터를 가져오지 못했습니다" 안내
RAG DB 다운   → law 경로만 동작 (MCP만으로 답변)
```

### 장단점

| 장점 | 단점 |
|------|------|
| 최적의 답변 품질 (양쪽 소스 결합) | 구현 복잡도 높음 |
| 병렬 실행으로 지연 최소화 | Router 정확도가 전체 품질 좌우 |
| 출처 투명성 (어디서 온 정보인지 명시) | 컨텍스트 병합 로직 튜닝 필요 |
| Graceful degradation (부분 장애 허용) | 두 시스템 동시 운영/디버깅 부담 |
| Docker로 원클릭 배포 가능 | 인프라 비용 증가 (MCP 서버 프로세스) |

### 예상 노력: 10~15일 (Phase 1-2 완료 기준 추가분)

---

## 단계별 의존 관계

```
Phase 1 (완료)          Phase 2              Phase 3
──────────────         ─────────           ──────────
mcp_law_client.py  ──→ law_indexer.py
                       (클라이언트 재사용)

rag_engine.py   ──────────────────────→ unified_engine.py
(법령검색 분기)                             (3경로 확장)

                       chunking_utils.py ─→ (Phase 3에서도 재사용)
```

- Phase 2는 Phase 1의 `McpLawClient`를 재사용 (의존)
- Phase 3는 Phase 1의 MCP 분기 + Phase 2의 인덱싱 위에 구축
- 각 Phase는 **독립 배포 가능** — 이전 Phase만 완료되면 됨

---

## 환경 변수 참고

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `MCP_SERVER_URL` | `http://localhost:3000` | MCP 서버 주소 (빈 문자열이면 비활성화) |
| `LAW_API_KEY` | (없음) | 법제처 API 키 (MCP 서버에 전달) |
| `LAW_OC` | (없음) | MCP 서버 측 법제처 API 키 환경변수 |
