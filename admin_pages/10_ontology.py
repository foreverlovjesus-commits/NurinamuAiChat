"""
🧠 온톨로지 관리 페이지
그룹: 🗂️ 데이터베이스
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

import pandas as pd
try:
    from rag.ontology_manager import OntologyManager
    omp = OntologyManager()
    
    st.markdown("### 🧠 관용어 ↔ 법률개념어 (의미망 맵핑)")
    st.info("사용자의 거친 일상 질문(예: '학부모')을 법적 핵심 개념어(예: '직무관련자')로 은밀하고 확실하게 자동 확장하여 검색 성공률을 폭발적으로 끌어올리는 RAG의 두뇌(사전)입니다.")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("#### 📚 현재 적용 중인 사전")
        
        if not omp.ontology:
            st.warning("등록된 온톨로지 단어가 없습니다.")
        else:
            df_data = [{"단어 (사용자 입력)": k, "확장되는 법적 개념어": ", ".join(v)} for k, v in omp.ontology.items()]
            df = pd.DataFrame(df_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
            
    with col2:
        st.markdown("#### ⚙️ 사전 추가 / 삭제")
        with st.form("add_ontology_form"):
            new_entity = st.text_input("새 단어 (예: 식사대접)")
            new_concepts = st.text_input("매핑할 법적 개념 (쉼표로 구분, 예: 금품수수, 향응)")
            submit_btn = st.form_submit_button("추가 / 덮어쓰기")
            if submit_btn and new_entity and new_concepts:
                c_list = [c.strip() for c in new_concepts.split(",") if c.strip()]
                omp.add_entity(new_entity.strip(), c_list)
                st.success(f"'{new_entity}' → {c_list} 등록 완료!")
                st.rerun()
                
        with st.form("delete_ontology_form"):
            del_entity = st.text_input("삭제할 단어 지정")
            del_btn = st.form_submit_button("삭제")
            if del_btn and del_entity:
                if del_entity in omp.ontology:
                    omp.remove_entity(del_entity.strip())
                    st.warning(f"'{del_entity}' 항목이 삭제되었습니다.")
                    st.rerun()
                else:
                    st.error("해당 단어가 사전에 없습니다.")

    st.markdown("---")
    st.markdown("#### 🧪 작동 시뮬레이션")
    test_query = st.text_input("테스트 질문:", value="유치원 선생님께 스승의날에 재학중인 학생이 선물을 주는 것은 어떤 범에 저촉이 되는 거지")
    if st.button("내부 검색 쿼리 변환 확인하기"):
        expanded = omp.expand_query(test_query)
        st.success(f"**엔진 내부적으로 변환되어 벡터 DB로 전송되는 최종 검색어:**\n> {expanded}")
        
except ImportError:
    st.error("rag.ontology_manager 모듈을 찾을 수 없습니다. (구현 필요)")

# ─────────────────────────────
# 탭 X: 시스템 프롬프트 관리
# ─────────────────────────────
