"""
📝 프롬프트 관리 페이지
그룹: ⚙️ 시스템 설정
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

st.markdown("### 📝 메인 답변 생성 프롬프트 (System Prompt) 관리")
st.info(
    "RAG 시스템이 문서를 바탕으로 최종 답변을 생성할 때 사용하는 최상위 지시어(System Prompt)입니다. "
    "주관식 답변의 어조, 포맷(FIRAC 등), 제약사항 등을 이곳에서 마음껏 추가로 지시하거나 통제할 수 있습니다."
)

# .env 파일에서 현재 재정의된 프롬프트 로드
current_custom_prompt = os.getenv("SYSTEM_PROMPT_OVERRIDE", "")

st.markdown("#### 핵심 시스템 지시어 재정의")
with st.form("prompt_management_form"):
    new_prompt = st.text_area(
        "커스텀 프롬프트 입력",
        value=current_custom_prompt,
        height=300,
        help="이곳을 비워두면 시스템 내부의 기본 최적화 프롬프트(FIRAC 및 법령 인용 제약 등 강력한 기본 룰)가 적용됩니다.\n"
             "여기에 내용을 작성하시면 **기본 프롬프트를 완전히 무시하고 오직 여기에 적힌 내용만 지시사항으로 사용**하게 됩니다. "
             "(단, FIRAC 체크박스가 켜져있다면 이 내용 뒤에 FIRAC 포맷 지시어가 자동으로 강제 첨부됩니다.)"
    )
    
    col1, col2 = st.columns([1, 4])
    with col1:
        submit_prompt = st.form_submit_button("프롬프트 저장")
    with col2:
        st.caption("저장 후 바로 다음 질문부터 즉시 반영됩니다.")
        
    if submit_prompt:
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("\n")
        # 입력값이 비어있거나 수정되었을 때 환경변수 저장 (여러 줄 저장을 위해 안전하게 처리 필요 - dotenv 지원방식)
        safe_set_key(ENV_PATH, "SYSTEM_PROMPT_OVERRIDE", new_prompt.strip().replace('\n', '\\n'))
        st.success("시스템 프롬프트가 성공적으로 저장되었습니다.")
        load_dotenv(ENV_PATH, override=True)  # 즉시 환경변수 갱신
        
        # 파이썬에서 즉시 적용되게 하기 위함
        os.environ["SYSTEM_PROMPT_OVERRIDE"] = new_prompt.strip().replace('\n', '\\n')
        
st.markdown("---")
st.markdown("#### 💡 팁: AI에게 효과적으로 지시하는 방법 (Prompt Engineering)")
st.markdown(
    """
    * **역할 부여**: `당신은 대한민국 최고의 공공기관 법률 분석가입니다.`
    * **부정 지시어 제어**: `~하지 마시오` 보다는 `대신 무조건 ~ 하시오` 라고 긍정문으로 강제하는 것이 훨씬 성능이 좋습니다.
    * **말투 고정**: `모든 답변은 '하십시오/합니까' 체로 종결하라.`
    * **출처 강제**: `제공된 참고 문서에 없는 내용은 절대로 상상해서 작성하지 말고, 파악할 수 없으면 '관련 근거를 찾을 수 없다'고 답하라.`
    """
)

st.markdown("---")
with st.expander("⚙️ 시스템 내부 엔지니어링 프롬프트 (읽기 전용) 보기"):
    st.info("아래 프롬프트들은 검색 품질과 내부 파이프라인(JSON 구조 등)을 제어하기 위해 파이썬 엔진에 단단히 고정된 규칙들입니다. 시스템 안정성을 위해 화면에서는 수정할 수 없습니다(비활성화).")
    
    st.text_area(
        "1. 라우터(분류기) 프롬프트",
        value="당신은 공공기관 민원/질문 분석 전문가입니다. 사용자의 질문을 분석하여 다음 기준에 따라 오직 JSON으로만 출력하세요.\n"
              "1. route_type: ['rag', 'law', 'hybrid']\n"
              "2. category: 다음 중 하나 선택 (청탁금지법, 이해충돌방지법, 공무원행동강령, 일반 Q&A 등)\n"
              "3. reason: 분류 판단 근거\n"
              "4. summary_5w1h: 육하원칙 요약\n"
              "5. search_keyword: 핵심 키워드 3~5개",
        height=150,
        disabled=True,
        help="사용자의 질문을 분석하여 10개 카테고리 중 하나를 고르는 프롬프트입니다."
    )
    
    st.text_area(
        "2. 맥락 압축(Condense) 프롬프트",
        value="지시대명사나 생략된 맥락을 포함한 완전한 검색용 문장으로 재구성하세요.\n\n"
              "[이전 대화]\n(대화 기록)\n\n"
              "[최신 질문]\n(현재 질문)",
        height=120,
        disabled=True,
        help="사용자의 생략된 질문('이건 왜요?')을 완전한 검색어로 복원하는 프롬프트입니다."
    )
    
    st.text_area(
        "3. 적격성 검사 프롬프트",
        value="답변은 '적격', '부적격', '판단불가' 중 하나로 시작하고 이유를 작성하세요.\n\n"
              "[정의 문서]\n(법적용 대상자 요약)\n\n"
              "[질문]\n(질문)",
        height=120,
        disabled=True,
        help="대상자가 청탁금지법 등 법적용 대상(공직자등)에 해당하는지 1차로 필터링하는 프롬프트입니다."
    )
