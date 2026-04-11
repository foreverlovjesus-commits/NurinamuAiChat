"""
⚙️ 코어 설정 페이지
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


st.markdown("### 전역 시스템 작동 설정")
with st.form("global_config_form"):
    st.info("이곳에서 설정한 값은 일반 사용자의 채팅 화면에 즉시 전체 적용됩니다.")
    
    mode_options = {
        "auto": "자동 하이브리드 탐색 (AI 판단)", 
        "hybrid": "강제 통합 검색 (내부 파일 + 법제처 동시 탐색)",
        "rag": "내부 지침문서 전용 탐색 (RAG)", 
        "pure_llm": "순수 지식 검색 (RAG 미사용, LLM 자체 엔진)",
        "law": "실시간 법제처 전용 탐색 (MCP)"
    }
    current_mode = os.getenv("GLOBAL_SEARCH_MODE", "auto")
    mode_idx = list(mode_options.keys()).index(current_mode) if current_mode in mode_options else 0
    selected_mode = st.selectbox("기본 검색 모드", options=list(mode_options.keys()), index=mode_idx, format_func=lambda x: mode_options[x])

    llm_options = {
        "local":     "구축형 로컬 AI (Ollama)",
        "openai":    "OpenAI (모델명은 하단에서 직접 설정)",
        "gemini":    "Google Gemini (모델명은 하단에서 직접 설정)",
        "anthropic": "Anthropic Claude (모델명은 하단에서 직접 설정)"
    }
    # LLM_PROVIDER (레거시) / GLOBAL_LLM_PROVIDER 양쪽 모두 확인
    current_llm = os.getenv("GLOBAL_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "local"))
    # 레거시 값 호환: 'ollama' -> 'local', 'commercial' -> 기존 제공사
    if current_llm == "ollama":
        current_llm = "local"
    llm_idx = list(llm_options.keys()).index(current_llm) if current_llm in llm_options else 0
    selected_llm = st.selectbox("전역 LLM 제공사", options=list(llm_options.keys()), index=llm_idx, format_func=lambda x: llm_options[x])
    
    current_hide_judgment = os.getenv("HIDE_DETAILED_JUDGMENT", "false").lower() == "true"
    hide_judgment = st.checkbox("상세 법적 판단 설명 생략 (5W1H, 키워드, 조문 원문만 출력)", value=current_hide_judgment)

    current_enable_firac = os.getenv("ENABLE_FIRAC_MODE", "false").lower() == "true"
    enable_firac = st.checkbox("FIRAC 법률 논리 추론 모드 활성화 (사실-쟁점-규정-포섭-결론 구조 강제)", value=current_enable_firac)
    
    if enable_firac:
        st.markdown("---")
        st.markdown("**🖋️ FIRAC 세부 스타일 설계 (빌더)**")
        f_col1, f_col2, f_col3 = st.columns(3)
        
        with f_col1:
            format_options = {"concise": "간결체 (Concise)", "narrative": "서술식 (Narrative)", "prolix": "만연체 (Prolix)"}
            current_format = os.getenv("FIRAC_FORMAT_STYLE", "concise")
            f_format = st.selectbox("문장 형태 (Formatting)", options=list(format_options.keys()), index=list(format_options.keys()).index(current_format) if current_format in format_options else 0, format_func=lambda x: format_options[x], help="글의 전반적인 문체와 표현 리듬을 결정합니다.")
            
        with f_col2:
            logic_options = {"front": "두괄식 (결론 상단)", "inductive": "미괄식 (결론 하단)"}
            current_logic = os.getenv("FIRAC_LOGIC_STRUCTURE", "front")
            f_logic = st.selectbox("논리 배치 (Logic)", options=list(logic_options.keys()), index=list(logic_options.keys()).index(current_logic) if current_logic in logic_options else 0, format_func=lambda x: logic_options[x], help="가장 중요한 결론을 어디에 배치할지 결정합니다.")
            
        with f_col3:
            template_options = {"basic": "기본 FIRAC", "statutory": "조문체 (계층 구조)", "judicial": "판결문체 (주문/이유)"}
            current_template = os.getenv("FIRAC_TEMPLATE_TYPE", "basic")
            f_template = st.selectbox("특수 양식 (Template)", options=list(template_options.keys()), index=list(template_options.keys()).index(current_template) if current_template in template_options else 0, format_func=lambda x: template_options[x], help="법률 문서 특유의 구조적 형식을 지정합니다.")
        st.markdown("---")
    else:
        # 비활성화 시 기본값 할당 (저장 로직 오류 방지)
        f_format, f_logic, f_template = "concise", "front", "basic"

    st.markdown("##### ⚡ 속도 최적화 (다이어트) 옵션")
    current_enable_eligibility = os.getenv("ENABLE_ELIGIBILITY_CHECK", "false").lower() == "true"
    enable_eligibility = st.checkbox("부적격 자동 심사(Gatekeeper) 활성화 (체크 해제 시 속도 대폭 향상)", value=current_enable_eligibility)

    current_enable_expansion = os.getenv("ENABLE_QUERY_EXPANSION", "false").lower() == "true"
    enable_expansion = st.checkbox("검색 전 쿼리 의미 확장(Query Expansion) 활성화 (체크 해제 시 속도 대폭 향상)", value=current_enable_expansion)

    submitted_config = st.form_submit_button("전역 설정 저장")
    if submitted_config:
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("\n")
        safe_set_key(ENV_PATH, "GLOBAL_SEARCH_MODE", selected_mode)
        safe_set_key(ENV_PATH, "GLOBAL_LLM_PROVIDER", selected_llm)
        # 레거시 키도 함께 갱신 (rag_engine.py 등 다른 모듈 호환)
        safe_set_key(ENV_PATH, "LLM_PROVIDER", selected_llm)
        safe_set_key(ENV_PATH, "HIDE_DETAILED_JUDGMENT", "true" if hide_judgment else "false")
        safe_set_key(ENV_PATH, "ENABLE_FIRAC_MODE", "true" if enable_firac else "false")
        if enable_firac:
            safe_set_key(ENV_PATH, "FIRAC_FORMAT_STYLE", f_format)
            safe_set_key(ENV_PATH, "FIRAC_LOGIC_STRUCTURE", f_logic)
            safe_set_key(ENV_PATH, "FIRAC_TEMPLATE_TYPE", f_template)
            
        safe_set_key(ENV_PATH, "ENABLE_ELIGIBILITY_CHECK", "true" if enable_eligibility else "false")
        safe_set_key(ENV_PATH, "ENABLE_QUERY_EXPANSION", "true" if enable_expansion else "false")
        
        st.success("전역 시스템 작동 설정이 성공적으로 저장되었습니다.")
        load_dotenv(ENV_PATH, override=True)  # 즉시 환경변수 갱신

st.markdown("---")
st.markdown("### 📈 문서 유형별 검색 가중치 (우선순위 역학 조절)")
st.info("청탁금지법 등 해석이 중요한 분야에서, 동일한 유사도일 경우 명시된 유형의 문서(예: 유권해석, 사례집)를 최우선으로 결과에 노출하도록 가산점(Bonus)을 부여합니다.")

with st.form("doc_weight_form"):
    w_col1, w_col2 = st.columns(2)
    with w_col1:
        val_case = st.slider("유권해석 / 판례 (case) 가중치", min_value=0.0, max_value=5.0, value=float(os.getenv("WEIGHT_CASE", "2.0")), step=0.1, help="가장 높은 응답 우선순위가 필요한 유권해석 자료에 부여하는 점수입니다.")
        val_faq = st.slider("사례집 / 질의응답 (faq) 가중치", min_value=0.0, max_value=5.0, value=float(os.getenv("WEIGHT_FAQ", "1.0")), step=0.1, help="명확한 Q&A 기반 안내 자료에 부여하는 점수입니다.")
    with w_col2:
        val_legal = st.slider("법령 원문 (legal) 가중치", min_value=0.0, max_value=5.0, value=float(os.getenv("WEIGHT_LEGAL", "0.0")), step=0.1, help="해석의 기반이 되는 법 조문 원문입니다.")
        val_general = st.slider("일반 안내문 (general) 가중치", min_value=0.0, max_value=5.0, value=float(os.getenv("WEIGHT_GENERAL", "0.0")), step=0.1, help="그 외 매뉴얼이나 공문 등의 자료입니다.")

    submitted_weights = st.form_submit_button("가중치 설정 적용")
    if submitted_weights:
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("\n")
        safe_set_key(ENV_PATH, "WEIGHT_CASE", str(val_case))
        safe_set_key(ENV_PATH, "WEIGHT_FAQ", str(val_faq))
        safe_set_key(ENV_PATH, "WEIGHT_LEGAL", str(val_legal))
        safe_set_key(ENV_PATH, "WEIGHT_GENERAL", str(val_general))
        st.success(f"문서 우선순위 가중치가 저장되었습니다. (유권해석: +{val_case}, 사례집: +{val_faq}, 법령: +{val_legal})")
        load_dotenv(ENV_PATH, override=True)

st.markdown("---")
st.markdown("### 🌐 외부 연동 및 네트워크(CORS) 설정")
st.info("프론트엔드 통신 허용 범위와 법제처 법령 검색 등 외부 모듈(MCP) 서버 주소를 설정합니다.")

with st.form("network_config_form"):
    mcp_url_val = os.getenv("MCP_SERVER_URL", "http://localhost:3000")
    mcp_server_url = st.text_input("MCP 외부 서버 URL (법제처 검색 전용)", value=mcp_url_val, help="연동된 법제처 MCP 백엔드 서버의 주소입니다.")
    
    api_key_val = os.getenv("API_KEY", "")
    system_api_key = st.text_input("시스템 보안 통신 키 (API_KEY)", value=api_key_val, type="password", help="MCP 서버 연동 및 /ask 엔드포인트 인증 등에 사용되는 자체 보안 키입니다.")
    
    cors_val = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501")
    allowed_origins = st.text_input("허용할 프론트엔드 출처 표시 (ALLOWED_ORIGINS)", value=cors_val, help="웹 화면 구동 허용 목록입니다 (띄어쓰기 없이 쉼표로 구분)")
    
    doc_archive_val = os.getenv("DOC_ARCHIVE_DIR", "doc_archive")
    doc_archive_dir = st.text_input("임베딩 파일 기본 업로드 폴더명 (DOC_ARCHIVE_DIR)", value=doc_archive_val, help="업로드된 파일들이 저장되는 경로입니다. (기본값: doc_archive)")
    
    submitted_network = st.form_submit_button("네트워크 설정 저장")
    if submitted_network:
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("\n")
        safe_set_key(ENV_PATH, "MCP_SERVER_URL", mcp_server_url.strip())
        safe_set_key(ENV_PATH, "API_KEY", system_api_key.strip())
        safe_set_key(ENV_PATH, "ALLOWED_ORIGINS", allowed_origins.strip())
        safe_set_key(ENV_PATH, "DOC_ARCHIVE_DIR", doc_archive_dir.strip())
        st.success("네트워크 설정(CORS, 스토리지)이 성공적으로 저장되었습니다.")
        load_dotenv(ENV_PATH, override=True)

st.markdown("---")
st.markdown("### 🔑 상용 LLM API Keys 설정")
st.info("API Key를 입력하고 저장하면, 위에서 선택한 전역 LLM 모델 구동 시 즉각 사용됩니다.")

with st.form("api_key_form"):
    openai_key = st.text_input("OpenAI API Key (gpt-4o 등)", value=os.getenv("OPENAI_API_KEY", ""), type="password")
    google_key = st.text_input("Google AI Studio API Key (gemini-2.5-flash 등)", value=os.getenv("GOOGLE_API_KEY", ""), type="password")
    anthropic_key = st.text_input("Anthropic API Key (claude-3-5-sonnet 등)", value=os.getenv("ANTHROPIC_API_KEY", ""), type="password")
    
    submitted = st.form_submit_button("설정 저장")
    if submitted:
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("\n")
        safe_set_key(ENV_PATH, "OPENAI_API_KEY", openai_key)
        safe_set_key(ENV_PATH, "GOOGLE_API_KEY", google_key)
        safe_set_key(ENV_PATH, "ANTHROPIC_API_KEY", anthropic_key)
        st.success("API 키가 `.env` 파일에 성공적으로 저장되었습니다.")

st.markdown("---")
st.markdown("### LLM 모델명 직접 설정 (상용 및 로컬)")
st.info("각 제공사의 정확한 모델 ID를 아래에 입력하시면 해당 모델로 즉시 전환됩니다. (예: gemini-2.5-pro, gpt-4o, qwen2.5:14b)")

with st.form("llm_model_name_form"):
    col1, col2 = st.columns(2)
    with col1:
        gemini_model = st.text_input(
            "Gemini 메인 모델명 (GEMINI_MODEL)",
            value=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            help="Google AI Studio 구동 시 사용할 최종 답변 생성 모델 ID."
        )
        openai_main = st.text_input(
            "OpenAI 메인 모델명 (OPENAI_MAIN_MODEL)",
            value=os.getenv("OPENAI_MAIN_MODEL", "gpt-4o"),
            help="최종 답변 생성에 사용할 모델. 예: gpt-4o, gpt-4-turbo"
        )
        ollama_main = st.text_input(
            "로컬 AI 메인 모델명 (MAIN_LLM_MODEL)",
            value=os.getenv("MAIN_LLM_MODEL", "qwen2.5:14b"),
            help="Ollama 구동 시 사용할 메인 답변 모델. 예: qwen2.5:14b, llama3"
        )
    with col2:
        gemini_router = st.text_input(
            "Gemini 라우터 모델명 (GEMINI_ROUTER_MODEL)",
            value=os.getenv("GEMINI_ROUTER_MODEL", "gemini-3.1-flash-lite-preview"),
            help="질문 분류 등 경량 처리에 사용할 모델."
        )
        anthropic_model = st.text_input(
            "Anthropic 모델명 (ANTHROPIC_MODEL)",
            value=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
            help="Anthropic 구동 시 사용할 모델 ID. 예: claude-3-7-sonnet-latest"
        )
        openai_router = st.text_input(
            "OpenAI 라우터(경량) 모델명 (OPENAI_ROUTER_MODEL)",
            value=os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini"),
            help="질문 분류 등 경량 처리에 사용할 모델. 예: gpt-4o-mini"
        )
        ollama_router = st.text_input(
            "로컬 AI 라우터 모델명 (ROUTER_LLM_MODEL)",
            value=os.getenv("ROUTER_LLM_MODEL", "exaone3.5:2.4b"),
            help="Ollama 구동 시 사용할 질문 분류용 경량 모델. 예: exaone3.5:2.4b"
        )

    submitted_model = st.form_submit_button("모델명 저장")
    if submitted_model:
        if not os.path.exists(ENV_PATH):
            with open(ENV_PATH, "w") as f:
                f.write("\n")
        safe_set_key(ENV_PATH, "GEMINI_MODEL", gemini_model.strip())
        safe_set_key(ENV_PATH, "GEMINI_ROUTER_MODEL", gemini_router.strip())
        safe_set_key(ENV_PATH, "OPENAI_MAIN_MODEL", openai_main.strip())
        safe_set_key(ENV_PATH, "OPENAI_ROUTER_MODEL", openai_router.strip())
        safe_set_key(ENV_PATH, "ANTHROPIC_MODEL", anthropic_model.strip())
        safe_set_key(ENV_PATH, "MAIN_LLM_MODEL", ollama_main.strip())
        safe_set_key(ENV_PATH, "ROUTER_LLM_MODEL", ollama_router.strip())
        st.success("LLM 모델명이 성공적으로 저장되었습니다. 서버 재기동 없이 다음 질문부터 즉시 반영됩니다.")
        load_dotenv(ENV_PATH, override=True)  # 즉시 환경변수 갱신

st.markdown("---")
# API 연결 및 통신 테스트 추가
if st.button("현재 LLM 제공자 API 연결 및 모델 테스트", use_container_width=True):
    provider = os.getenv("GLOBAL_LLM_PROVIDER", "local").lower()
    with st.spinner(f"현재 활성화된 API ({provider}) 연결 및 모델 동작 확인 중..."):
        try:
            if provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                r_model = os.getenv("GEMINI_ROUTER_MODEL", "gemini-3.1-flash-lite-preview")
                m_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
                llm_r = ChatGoogleGenerativeAI(model=r_model, temperature=0, max_output_tokens=10)
                llm_r.invoke("test")
                llm_m = ChatGoogleGenerativeAI(model=m_model, temperature=0, max_output_tokens=10)
                llm_m.invoke("test")
                st.success(f"✅ Gemini 통신 정상! (라우터: {r_model}, 메인: {m_model})")

            elif provider == "openai":
                from langchain_openai import ChatOpenAI
                r_model = os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini")
                m_model = os.getenv("OPENAI_MAIN_MODEL", "gpt-4o")
                llm_r = ChatOpenAI(model=r_model, temperature=0, max_tokens=10)
                llm_r.invoke("test")
                llm_m = ChatOpenAI(model=m_model, temperature=0, max_tokens=10)
                llm_m.invoke("test")
                st.success(f"✅ OpenAI 통신 정상! (라우터: {r_model}, 메인: {m_model})")

            elif provider == "anthropic":
                from langchain_anthropic import ChatAnthropic
                m_model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
                llm_m = ChatAnthropic(model=m_model, temperature=0, max_tokens=10)
                llm_m.invoke("test")
                st.success(f"✅ Anthropic 통신 정상! (공용 모델: {m_model})")

            else:
                import requests
                ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                resp = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=5)
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    r_model = os.getenv("ROUTER_LLM_MODEL", "exaone3.5:2.4b")
                    m_model = os.getenv("MAIN_LLM_MODEL", "qwen2.5:14b")
                    r_ok = r_model in models
                    m_ok = m_model in models
                    if r_ok and m_ok:
                        st.success(f"✅ Ollama 연결 성공! 라우터({r_model}) 및 메인({m_model}) 모두 설치 가능")
                    else:
                        st.warning(f"⚠️ Ollama 연결은 되었으나 모델 설치 확인이 필요합니다. (라우터 보유:{r_ok}, 메인 보유:{m_ok})")
                        st.info(f"선택된 모델: [라우터: {r_model}, 메인: {m_model}], 보유 모델: " + ", ".join(models[:5]))
                else:
                    st.error("❌ Ollama 서버 응답 오류")
        except Exception as e:
            st.error(f"❌ LLM 테스트 실패: {str(e)}")

# ─────────────────────────────
# 탭 X: 온톨로지 관리 
# ─────────────────────────────
