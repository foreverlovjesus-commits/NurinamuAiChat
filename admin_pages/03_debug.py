"""
🔎 검색 품질 디버그 페이지
그룹: 🧪 디버그 & 벤치마크
"""
import streamlit as st
import os
import sys
import time
import json
import asyncio
import glob
import subprocess
import pandas as pd
import psycopg2
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# 공통 유틸리티 로드
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)
load_dotenv(os.path.join(_BASE, ".env"))
from admin_shared_utils import (
    get_db_url, safe_set_key, fetch_indexed_files,
    fetch_indexed_collections, delete_collection, fetch_file_model_matrix,
    load_progress, read_tail_logs
)
import usage_tracker
try:
    from integrations.mcp_law_client import McpLawClient
except ImportError:
    McpLawClient = None
ENV_PATH = os.path.join(_BASE, ".env")
BASE_DIR = _BASE
PROGRESS_FILE = os.path.join(_BASE, "logs", "progress.json")

st.markdown("### 검색 품질 디버그 도구 (파이프라인 단계별 확인)")
st.info("입력된 질문이 RAG 엔진 내부에서 어떻게 처리되는지 단계별로 투명하게 보여줍니다. (쿼리 확장 → 메타데이터 추출 → 검색 → 리랭킹)")
debug_query = st.text_input("디버깅할 질문 입력", placeholder="예: 공직자가 외부강의를 할 때 사례금 상한액은 얼마인가요?")

if st.button("디버그 파이프라인 실행", type="primary") and debug_query:
    db_url = get_db_url()
    if not db_url:
        st.error("DB 연결 정보가 없습니다.")
    else:
        # RAG 엔진 및 Retriever 인스턴스화
        from rag.rag_engine import RAGEngineV3
        from retriever.factory import get_retriever
        retriever = get_retriever(db_url)
        rag_engine = RAGEngineV3(retriever)
        
        with st.status("디버깅 파이프라인 실행 중...", expanded=True) as status:
            pipeline_start_t = time.time()
            
            # 1. 쿼리 재구성 및 분류
            st.markdown("**1. 쿼리 재구성 및 분류 (Condense & Classify)**")
            t0 = time.time()
            router_llm = rag_engine._get_llm(os.getenv("GLOBAL_LLM_PROVIDER", "local"), is_router=True)
            
            condensed_query = asyncio.run(rag_engine.condense_question(debug_query, [], router_llm))
            st.write(f" - **재구성된 쿼리**: `{condensed_query}`")

            route_info = asyncio.run(rag_engine.classify_category(condensed_query, router_llm))
            t1 = time.time()
            st.caption(f"⏱️ 분류 완료 (소요시간: {t1 - t0:.2f}초)")
            st.write(" - **분류 결과 (JSON)**:")
            st.json(route_info)
            
            search_keyword = route_info.get("search_keyword", condensed_query)
            st.write(f" - **최종 검색 키워드**: `{search_keyword}`")
            
            # 2. 메타데이터 필터 시뮬레이션
            st.markdown("**2. 메타데이터 필터 추출 (LLM Tagging)**")
            tag_filter = {}
            is_tagging_enabled = os.getenv("ENABLE_METADATA_TAGGING", "true").lower() == "true"
            if is_tagging_enabled:
                t2_start = time.time()
                try:
                    from indexer.metadata_tagger import MetadataTagger
                    tagger = MetadataTagger(router_llm)
                    tag_filter = asyncio.run(tagger.tag_query(condensed_query))
                    st.json(tag_filter)
                    t2_end = time.time()
                    st.caption(f"⏱️ 메타데이터 추출 완료 (소요시간: {t2_end - t2_start:.2f}초)")
                except Exception as e:
                    st.warning(f"필터 추출 중 오류: {e}")
            else:
                st.info("💡 환경 설정에 의해 메타데이터 자동 태깅이 비활성화되었습니다. (건너뜀)")
            
            pg_filter_list = None
            pg_filter_for_debug = tag_filter
            if tag_filter:
                try:
                    pg_filter_list = retriever._build_filter_levels(tag_filter)
                    pg_filter_for_debug = pg_filter_list[0] if pg_filter_list else tag_filter
                except AttributeError:
                    pg_filter_list = [tag_filter, None]
            st.write(f"- PGVector 적용 필터 목록(내부용): `{pg_filter_list}`")
            st.write(f"- 단일 벡터 검색 테스트용 필터: `{pg_filter_for_debug}`")

            # 3. 쿼리 확장
            st.markdown("**3. 쿼리 확장 (Query Expansion)**")
            is_expansion_enabled = os.getenv("ENABLE_QUERY_EXPANSION", "false").lower() == "true"
            if is_expansion_enabled:
                t3_start = time.time()
                expanded_queries = asyncio.run(retriever.aexpand_query(search_keyword))
                st.json(expanded_queries)
                t3_end = time.time()
                st.caption(f"⏱️ 쿼리 확장 완료 (소요시간: {t3_end - t3_start:.2f}초)")
            else:
                st.info("💡 전역 속도 최적화 설정에 의해 쿼리 확장이 비활성화되었습니다. (원본 키워드로 즉시 검색)")

            # 4. 초기 검색 결과 (Vector vs FTS)
            st.markdown("**4. 핵심 검색 및 Reranking (Retrieve)**")
            t4_start = time.time()
            
            final_docs = asyncio.run(retriever.retrieve(search_keyword, final_k=3, metadata_filter=tag_filter))
            for i, d in enumerate(final_docs, 1):
                src = d.metadata.get("source", "알 수 없음")
                dtype = d.metadata.get("doc_type", "general")
                fscore = d.metadata.get("final_score", 0.0)
                st.markdown(f"**Rank {i}** | `[{dtype}] {src}` (가중치 반영 AI 점수: **{fscore}**)")
                st.write(d.page_content[:300] + "...")
            
            t4_end = time.time()
            st.caption(f"⏱️ 검색 및 순위 재조정 완료 (소요시간: {t4_end - t4_start:.2f}초)")
                
            pipeline_end_t = time.time()
            status.update(label=f"파이프라인 디버깅 완료! (총 소요시간: {pipeline_end_t - pipeline_start_t:.2f}초)", state="complete", expanded=False)

# ─────────────────────────────
# 탭 4: 문서 및 데이터 관리 (업로드 & 청크 검수)
# ─────────────────────────────
