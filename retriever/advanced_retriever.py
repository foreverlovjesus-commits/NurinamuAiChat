import psycopg2
import asyncio
import os
import sys

# HuggingFace API 일시 초과(429) 방지: 기다운로드된 로컬 캐시 모델만 강제 사용
os.environ["HF_HUB_OFFLINE"] = "1"

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores.pgvector import PGVector
from sentence_transformers import CrossEncoder
from langchain_openai import ChatOpenAI

# 프로젝트 루트를 sys.path에 추가 (indexer 모듈 임포트용)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv()
import logging
logger = logging.getLogger(__name__)

class AdvancedHybridRetrieverV2:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.provider = os.getenv("GLOBAL_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "local")).lower()
        if self.provider == "ollama":
            self.provider = "local"
        self.router_model = os.getenv("ROUTER_LLM_MODEL", "exaone3.5:2.4b")

        ollama_url = os.getenv("OLLAMA_BASE_URL")
        base_url = f"{ollama_url.rstrip('/')}/v1" if self.provider == "local" else None
        api_key = "ollama" if self.provider == "local" else os.getenv("GOOGLE_API_KEY")

        try:
            self.db_pool = psycopg2.pool.ThreadedConnectionPool(
                int(os.getenv("DB_POOL_MIN", 1)),
                int(os.getenv("DB_POOL_MAX", 10)),
                db_url
            )
        except Exception:
            self.db_pool = None

        embedding_model = os.getenv("GLOBAL_EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
        self.active_embedding_model_name = embedding_model
        
        embed_lower = embedding_model.lower()
        emb_provider = os.getenv("GLOBAL_EMBEDDING_PROVIDER", "").lower()
        if emb_provider == "vertex":
            from langchain_google_vertexai import VertexAIEmbeddings
            self.embeddings = VertexAIEmbeddings(model_name=embedding_model)
        elif "google" in embed_lower or "models/" in embed_lower or "embedding-0" in embed_lower:
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            self.embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model, task_type="RETRIEVAL_QUERY")
        elif "openai" in embed_lower or "text-embedding-3" in embed_lower or "text-embedding-ada" in embed_lower:
            from langchain_openai import OpenAIEmbeddings
            self.embeddings = OpenAIEmbeddings(model=embedding_model)
        else:
            self.embeddings = HuggingFaceEmbeddings(
                model_name=embedding_model, 
                model_kwargs={"local_files_only": True}
            )
        
        safe_model_name = embedding_model.replace("/", "_").replace("-", "_")
        base_collection = os.getenv("VECTOR_DB_COLLECTION", "enterprise_knowledge_v3")
        collection_name = f"{base_collection}_{safe_model_name}"
        
        self.vectorstore = PGVector(
            collection_name=collection_name,
            connection_string=db_url,
            embedding_function=self.embeddings
        )

        # 💡 설정된 Router 모델 사용
        self.llm = ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=self.router_model,
            temperature=0.3
        )

        self.reranker = CrossEncoder('BAAI/bge-reranker-v2-m3', local_files_only=True)
        logger.info("[Retriever] Router: %s 가동", self.router_model)

    async def _expand_with_law_graph(self, query: str, initial_docs: list) -> list:
        """초기 검색 결과에서 참조 법률 그래프 기반 추가 검색 (온톨로지 확장)"""
        try:
            from indexer.law_graph import load_graph, find_related_laws
        except ImportError:
            return []

        graph = load_graph()
        if not graph.get("edges"):
            return []

        mentioned_laws = set()
        for doc in initial_docs:
            cat = doc.metadata.get("law_category", "")
            if cat and cat not in ("기타", "해당없음"):
                mentioned_laws.add(cat)

        if not mentioned_laws:
            return []

        related_laws = set()
        for law in mentioned_laws:
            for rel in find_related_laws(graph, law):
                if rel not in mentioned_laws:
                    related_laws.add(rel)

        if not related_laws:
            return []

        logger.info(f"🔗 지식 그래프 확장 검색 트리거: {', '.join(list(related_laws)[:3])}")
        tasks = []
        for law in list(related_laws)[:3]: # 속도 조절을 위해 최대 3개 법령만 추가 탐색
            tasks.append(asyncio.to_thread(
                self.vectorstore.similarity_search, query, k=3,
                filter={"law_category": law}
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        additional = []
        for r in results:
            if isinstance(r, list):
                additional.extend(r)
        return additional

    async def aexpand_query(self, original_query: str):
        """질문 확장 (Router 모델 사용)"""
        prompt = (
            f"다음 질문을 검색에 유리한 명사형 키워드 중심 검색어로 변환하여 2개 추가 생성하세요.\n"
            f"규칙:\n"
            f"- 번호(1., 2.)나 서술어를 붙이지 마세요\n"
            f"- 원래 질문의 의도를 유지하세요\n"
            f"- 질문에 없는 특정 법률명을 추측하여 추가하지 마세요\n"
            f"- 5~10단어 이내\n"
            f"질문: {original_query}"
        )
        try:
            res = await self.llm.ainvoke(prompt)
            lines = res.content.strip().split('\n')
            return [original_query] + [q.strip().replace('-', '').strip() for q in lines if q.strip()][:2]
        except Exception:
            return [original_query]

    def fts_search(self, query: str, k=15, metadata_filter: dict = None):
        query_terms = " | ".join(query.split())
        docs = []
        if not self.db_pool:
            return []

        # 메타데이터 필터 조건 구축 (화이트리스트 검증)
        try:
            from indexer.metadata_tagger import VALID_TAG_KEYS
        except ImportError:
            VALID_TAG_KEYS = frozenset()
        meta_clauses = []
        params = [query_terms, query_terms]
        if metadata_filter:
            for key, value in metadata_filter.items():
                if key == "source" and isinstance(value, list) and value:
                    # 다중 파일 선택 필터링 (ANY 연산자 사용)
                    meta_clauses.append(f"cmetadata->>'{key}' = ANY(%s)")
                    params.append(value)
                elif key in VALID_TAG_KEYS and value and value not in ("해당없음", "기타"):
                    meta_clauses.append(f"cmetadata->>'{key}' = %s")
                    params.append(value)

        meta_sql = ""
        if meta_clauses:
            meta_sql = " AND (" + " AND ".join(meta_clauses) + ")"
        params.append(k)

        conn = self.db_pool.getconn()
        try:
            with conn.cursor() as cursor:
                sql = f"""SELECT document, cmetadata FROM langchain_pg_embedding
                         WHERE fts @@ to_tsquery('simple', %s){meta_sql}
                         ORDER BY ts_rank(fts, to_tsquery('simple', %s)) DESC LIMIT %s;"""
                cursor.execute(sql, params)
                for row in cursor.fetchall():
                    docs.append(Document(page_content=row[0], metadata=row[1]))
        finally:
            self.db_pool.putconn(conn)
        return docs

    def rrf_score(self, results_list, k=60):
        type_weights = {
            "case": float(os.getenv("WEIGHT_CASE", "2.0")),
            "faq": float(os.getenv("WEIGHT_FAQ", "1.0")),
            "legal": float(os.getenv("WEIGHT_LEGAL", "0.0")),
            "general": float(os.getenv("WEIGHT_GENERAL", "0.0"))
        }
        
        doc_scores = {}
        for results in results_list:
            for rank, doc in enumerate(results):
                content = doc.page_content
                if content not in doc_scores:
                    doc_scores[content] = {"doc": doc, "score": 0}
                
                base_score = 1.0 / (k + rank + 1)
                dt = doc.metadata.get("doc_type", "general")
                # RRF 스코어 단위가 매우 작으므로(보통 0.01대), 보너스를 100으로 스케일링
                bonus = type_weights.get(dt, 0.0) / 100.0
                doc_scores[content]["score"] += (base_score + bonus)
                
        return [item["doc"] for item in sorted(doc_scores.values(), key=lambda x: x["score"], reverse=True)]

    def _build_filter_levels(self, metadata_filter: dict) -> list:
        """메타데이터 dict → 점진적 필터 레벨 목록 생성 (좁은→넓은→무필터)"""
        if not metadata_filter:
            return [None]
        try:
            from indexer.metadata_tagger import VALID_TAG_KEYS
        except ImportError:
            VALID_TAG_KEYS = frozenset()
        conditions = {}
        for key, value in metadata_filter.items():
            if key == "source":
                conditions[key] = value
            elif key in VALID_TAG_KEYS and value and value not in ("해당없음", "기타"):
                conditions[key] = value
        if not conditions:
            return [None]

        levels = []
        # Level 0: source 필터가 있으면 최우선 적용 (다중 선택 대응)
        if "source" in conditions:
            # PGVector (langchain) 필터 문법: 리스트일 경우 대응 로직이 필요할 수 있으나, 
            # 여기서는 dict를 그대로 넘기고 similarity_search 호출 시점에서 개별 처리하거나 fts_search에서 처리
            levels.append({"source": conditions["source"]})

        # Level 1: law_category만 (가장 넓은 필터)
        if "law_category" in conditions:
            levels.append({"law_category": conditions["law_category"]})
        # Level 2: act_type만
        if "act_type" in conditions:
            levels.append({"act_type": conditions["act_type"]})
        
        # Level 3: 무필터 (최종 폴백 - 단, NotebookLM 모드일 때는 무필터로 가면 안 됨)
        if "source" not in conditions:
            levels.append(None)
        
        return levels

    async def retrieve(self, query: str, final_k=3, metadata_filter: dict = None):
        is_expansion_enabled = os.getenv("ENABLE_QUERY_EXPANSION", "false").lower() == "true"
        queries = await self.aexpand_query(query) if is_expansion_enabled else [query]

        filter_levels = self._build_filter_levels(metadata_filter) if metadata_filter else [None]

        merged_docs = []
        used_filter = None
        for pg_filter in filter_levels:
            if pg_filter:
                # 💡 PGVector 의 filter 인자가 list를 직접 지원하지 않는 경우를 대비하여 source 리스트 필터링 보정
                v_filter = pg_filter.copy()
                if "source" in v_filter and isinstance(v_filter["source"], list):
                    # 개별 필터 요소가 일치하는지 확인하는 방식으로 PGVector가 동작하게 하려면 원본 소스 리스트 전달
                    # (참고: 일부 PGVector 버전에 따라 IN 절 구현이 다를 수 있음)
                    pass

                tasks = [asyncio.to_thread(self.vectorstore.similarity_search, q, k=10, filter=v_filter) for q in queries] + \
                        [asyncio.to_thread(self.fts_search, q, k=10, metadata_filter=metadata_filter) for q in queries]
            else:
                tasks = [asyncio.to_thread(self.vectorstore.similarity_search, q, k=10) for q in queries] + \
                        [asyncio.to_thread(self.fts_search, q, k=10) for q in queries]

            search_results_flat = await asyncio.gather(*tasks)
            merged_docs = self.rrf_score(search_results_flat)
            used_filter = pg_filter

            if len(merged_docs) >= 3:
                break
            logger.info("필터 %s 결과 부족 (%d건), 다음 레벨로 폴백", pg_filter, len(merged_docs))

        logger.info("최종 적용 필터: %s, 결과: %d건", used_filter, len(merged_docs))

        if not merged_docs:
            return []

        # 💡 지식 그래프 기반 컨텍스트 확장 (Reranking 전 수행)
        graph_docs = await self._expand_with_law_graph(query, merged_docs[:10])
        if graph_docs:
            existing = {d.page_content for d in merged_docs}
            for gd in graph_docs:
                if gd.page_content not in existing:
                    merged_docs.append(gd)
                    existing.add(gd.page_content)

        candidate_docs = merged_docs[:20]
        pairs = [[query, doc.page_content] for doc in candidate_docs]
        scores = await asyncio.to_thread(self.reranker.predict, pairs)

        type_weights = {
            "case": float(os.getenv("WEIGHT_CASE", "2.0")),
            "faq": float(os.getenv("WEIGHT_FAQ", "1.0")),
            "legal": float(os.getenv("WEIGHT_LEGAL", "0.0")),
            "general": float(os.getenv("WEIGHT_GENERAL", "0.0"))
        }

        SCORE_THRESHOLD = float(os.getenv("RERANKER_THRESHOLD", "-5.0"))
        filtered_results = []
        for doc, score in zip(candidate_docs, scores):
            dt = doc.metadata.get("doc_type", "general")
            bonus = type_weights.get(dt, 0.0)
            final_score = float(score) + bonus
            if final_score >= SCORE_THRESHOLD:
                filtered_results.append((doc, final_score))

        sorted_results = sorted(filtered_results, key=lambda x: x[1], reverse=True)[:final_k]
        
        final_docs = []
        for doc, f_score in sorted_results:
            doc.metadata["final_score"] = round(f_score, 2)
            final_docs.append(doc)
            
        return final_docs
    
    def __del__(self):
        if hasattr(self, 'db_pool') and self.db_pool:
            self.db_pool.closeall()
