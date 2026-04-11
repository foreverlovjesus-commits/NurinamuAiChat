"""
⚖️ 모델 성능 비교 페이지
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

st.markdown("### 임베딩 모델 검색 성능 비교")
st.info("DB에 색인된 임베딩 모델 컬렉션을 자동으로 탐지합니다. 비교할 모델을 체크하고 질문을 입력하세요.")

@st.cache_resource(show_spinner=False)
def get_cached_embeddings(model_name):
    """Streamlit 재실행 시 httpx client close 오류를 방지하기 위한 캐싱"""
    embed_lower = model_name.lower()
    if "google" in embed_lower or "models/" in embed_lower or "embedding-0" in embed_lower:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(model=model_name, task_type="RETRIEVAL_QUERY")
    elif "openai" in embed_lower or "text-embedding" in embed_lower:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model_name)
    else:
        from langchain_huggingface import HuggingFaceEmbeddings
        # httpx client 상태 캐싱 비활성화 (huggingface_hub 버그 우회)
        os.environ["HF_HUB_DISABLE_HTTPX_CLIENT_STATES"] = "1"
        return HuggingFaceEmbeddings(model_name=model_name)

base_collection = os.getenv("VECTOR_DB_COLLECTION", "enterprise_knowledge_v3")
all_collections = fetch_indexed_collections()

# 컬렉션 이름에서 base_collection 접두어를 제거하여 모델명 복원
model_collection_map = {}
for col_name, doc_count in all_collections:
    if col_name.startswith(base_collection + "_"):
        safe_name = col_name[len(base_collection) + 1:]
        # 역변환: _ -> / 는 불완전하므로, 컬렉션 이름과 문서수를 함께 표시
        model_collection_map[col_name] = {"safe_name": safe_name, "doc_count": doc_count}

if not model_collection_map:
    st.warning("색인된 임베딩 모델 컬렉션이 없습니다. 먼저 [배치 모니터링] 탭에서 문서를 색인해주세요.")
else:
    st.markdown("#### 색인된 임베딩 모델 컬렉션 (비교할 모델 체크)")
    selected_collections = []
    col1, col2 = st.columns(2)
    items = list(model_collection_map.items())
    for i, (col_name, info) in enumerate(items):
        target_col = col1 if i % 2 == 0 else col2
        with target_col:
            checked = st.checkbox(
                f"`{info['safe_name']}`  ({info['doc_count']:,}개 청크)",
                value=(i < 2),  # 기본으로 처음 2개 체크
                key=f"bench_{col_name}"
            )
            if checked:
                selected_collections.append(col_name)

    st.markdown("---")
    bench_query = st.text_input("비교 테스트 질문 입력", placeholder="예: 유치원 선생님에게 화분을 선물해도 되나요?")
    top_k = st.slider("상위 검색 결과 수 (Top-K)", min_value=1, max_value=5, value=3)

    if st.button("성능 비교 실행", type="primary", disabled=not (bench_query and len(selected_collections) >= 1)):
        if not bench_query.strip():
            st.warning("질문을 입력해주세요.")
        elif len(selected_collections) < 1:
            st.warning("비교할 모델을 최소 1개 이상 선택해주세요.")
        else:
            db_url = get_db_url()

            def run_search(collection_name, safe_name, query, k):
                from langchain_community.vectorstores.pgvector import PGVector
                
                # 컬렉션 이름(safe_name)을 원래 임베딩 모델명으로 복원
                known_models = [
                    "jhgan/ko-sroberta-multitask",
                    "BAAI/bge-m3",
                    "intfloat/multilingual-e5-small",
                    "models/gemini-embedding-001",
                    "models/text-embedding-004"
                ]
                safe_to_original = {m.replace("/", "_").replace("-", "_"): m for m in known_models}
                target_model = safe_to_original.get(safe_name, safe_name)

                # 캐싱된 전역 임베딩 모델 객체 재사용
                embeddings = get_cached_embeddings(target_model)

                try:
                    vs = PGVector(collection_name=collection_name, connection_string=db_url, embedding_function=embeddings)
                    return vs.similarity_search_with_score(query, k=k)
                except Exception as e:
                    return str(e)

            # 탭 형태로 결과 표시
            result_tabs = st.tabs([f"`{model_collection_map[c]['safe_name']}`" for c in selected_collections])
            for tab, col_name in zip(result_tabs, selected_collections):
                with tab:
                    info = model_collection_map[col_name]
                    with st.spinner(f"{info['safe_name']} 검색 중..."):
                        results = run_search(col_name, info['safe_name'], bench_query, top_k)

                    if isinstance(results, str):
                        st.error(f"오류: {results}")
                    elif not results:
                        st.warning("검색 결과가 없습니다.")
                    else:
                        for rank, (doc, score) in enumerate(results, 1):
                            source = doc.metadata.get("source", "알 수 없는 출처")
                            medal = [f"Rank {i}" for i in range(1, 6)][rank - 1]
                            with st.expander(f"{medal}  |  {source}  |  유사도: `{score:.4f}`", expanded=(rank == 1)):
                                st.text(doc.page_content[:800])
    
# ─────────────────────────────
# 탭 3: 검색 품질 디버그 도구
# ─────────────────────────────
