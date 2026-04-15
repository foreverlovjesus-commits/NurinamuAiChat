"""
📈 배치 모니터링 페이지
그룹: 📊 시스템 현황
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

data = load_progress()

st.markdown("### 임베딩 모델 선택 및 재색인")

# 1. 임베딩 제공사 선택
embed_provider_options = {
    "local": "로컬 (Ollama)",
    "google": "Google (Gemini)",
    "openai": "OpenAI (ChatGPT)",
    # Anthropic은 현재 자체 임베딩 API를 제공하지 않으므로 제외
}
current_provider = os.getenv("GLOBAL_EMBEDDING_PROVIDER", "local").lower()
provider_idx = list(embed_provider_options.keys()).index(current_provider) if current_provider in embed_provider_options else 0

selected_provider_key = st.selectbox(
    "임베딩 모델 제공사 선택", 
    options=list(embed_provider_options.keys()), 
    index=provider_idx, 
    format_func=lambda x: embed_provider_options[x],
    key="embedding_provider_selector"
)

# 2. 선택된 제공사에 따라 세부 모델 목록 동적 생성
embed_options = {
    "jhgan/ko-sroberta-multitask": "초고속 경량 한국어 표준 (sroberta) [로컬/무료]",
    "BAAI/bge-m3": "다국어 최고성능 (BGE-M3, GPU 권장) [로컬/무료]",
    "intfloat/multilingual-e5-small": "고속 경량 다국어 (e5-small) [로컬/무료]",
    "custom": "기타 (오픈소스 / 상용API 모델명 직접 입력)"
}
google_embed_options = {
    "models/gemini-embedding-exp-03-07": "Gemini Embedding Exp 03-07 (최신, 3072차원)",
    "models/text-embedding-005": "Text Embedding 005 (768차원)",
    "custom": "기타 (Google 모델명 직접 입력)"
}
openai_embed_options = {
    "text-embedding-ada-002": "text-embedding-ada-002 (1536차원)",
    "text-embedding-3-small": "text-embedding-3-small (1536차원)",
    "text-embedding-3-large": "text-embedding-3-large (3072차원)",
    "custom": "기타 (OpenAI 모델명 직접 입력)"
}

current_embed_env = os.getenv("GLOBAL_EMBEDDING_MODEL", "BAAI/bge-m3")
custom_val = ""
selected_model_list = []
selected_model_display_map = {}

if selected_provider_key == "local":
    selected_model_list = list(embed_options.keys())
    selected_model_display_map = embed_options
elif selected_provider_key == "google":
    selected_model_list = list(google_embed_options.keys())
    selected_model_display_map = google_embed_options
elif selected_provider_key == "openai":
    selected_model_list = list(openai_embed_options.keys())
    selected_model_display_map = openai_embed_options

# 현재 환경변수 모델이 목록에 없으면 'custom'으로 자동 전환
if current_embed_env not in selected_model_list:
    current_embed_idx = len(selected_model_list) - 1 # custom
    custom_val = current_embed_env
else:
    current_embed_idx = selected_model_list.index(current_embed_env)

col_embed, col_custom = st.columns([5, 5])
with col_embed:
    selected_embed_key = st.selectbox(
        "세부 임베딩 모델 선택",
        options=selected_model_list,
        index=current_embed_idx,
        format_func=lambda x: selected_model_display_map[x],
        key=f"embedding_model_selector_{selected_provider_key}"
    )

final_embed = selected_embed_key
with col_custom:
    if selected_embed_key == "custom":
        placeholder = {
            "local": "intfloat/multilingual-e5-large",
            "google": "models/text-embedding-005",
            "openai": "text-embedding-3-small"
        }.get(selected_provider_key, "모델명 입력")
        final_embed = st.text_input(
            "모델명 자유 입력",
            value=custom_val,
            placeholder=placeholder,
            key=f"custom_embed_input_{selected_provider_key}"
        )
        
col_save, empty_space = st.columns([3, 7])
with col_save:
    if st.button("임베딩 모델 저장", use_container_width=True):
        final_embed_clean = final_embed.strip() if final_embed else "BAAI/bge-m3"
        if not os.path.exists(ENV_PATH):
            open(ENV_PATH, "w").close()
        safe_set_key(ENV_PATH, "GLOBAL_EMBEDDING_MODEL", final_embed_clean)
        safe_set_key(ENV_PATH, "GLOBAL_EMBEDDING_PROVIDER", selected_provider_key) # 제공사도 저장
        st.success(f"임베딩 모델이 [{final_embed_clean}]로 저장되었습니다.")
        time.sleep(1)
        st.rerun()

st.markdown("---")
with st.expander("메타데이터 태깅 설정", expanded=False):
    st.caption("인덱싱 시 각 청크에 법률 카테고리, 대상자 유형 등을 자동 태깅합니다. 검색 정밀도 향상에 기여하지만 인덱싱 시간이 증가합니다.")
    with st.form("tagging_config_form"):
        current_tagging = os.getenv("ENABLE_METADATA_TAGGING", "true").lower() == "true"
        enable_tagging = st.checkbox("메타데이터 자동 태깅 활성화", value=current_tagging)

        tagging_provider_options = {
            "local": "로컬 Ollama (무료/느림)",
            "gemini": "Google Gemini (유료/빠름)",
            "openai": "OpenAI (유료/빠름)",
        }
        current_tag_provider = os.getenv("TAGGING_LLM_PROVIDER", "local")
        if current_tag_provider not in tagging_provider_options:
            current_tag_provider = "local"
        tag_provider_idx = list(tagging_provider_options.keys()).index(current_tag_provider)
        selected_tag_provider = st.selectbox(
            "태깅 LLM 제공사",
            options=list(tagging_provider_options.keys()),
            index=tag_provider_idx,
            format_func=lambda x: tagging_provider_options[x]
        )

        default_tag_models = {"gemini": "gemini-2.5-flash", "openai": "gpt-4o-mini", "local": "exaone3.5:2.4b"}
        current_tag_model = os.getenv("TAGGING_LLM_MODEL", default_tag_models.get(current_tag_provider, ""))
        tag_model = st.text_input(
            "태깅 모델명",
            value=current_tag_model,
            help=f"비워두면 기본 모델 사용 ({', '.join(f'{k}: {v}' for k, v in default_tag_models.items())})"
        )

        submitted_tagging = st.form_submit_button("태깅 설정 저장")
        if submitted_tagging:
            safe_set_key(ENV_PATH, "ENABLE_METADATA_TAGGING", "true" if enable_tagging else "false")
            safe_set_key(ENV_PATH, "TAGGING_LLM_PROVIDER", selected_tag_provider)
            safe_set_key(ENV_PATH, "TAGGING_LLM_MODEL", tag_model.strip())
            st.success("태깅 설정 저장 완료. 다음 인덱싱부터 적용됩니다.")
            load_dotenv(ENV_PATH, override=True)

    # API 연결 테스트 (form 바깥)
    if st.button("API 연결 및 크레딧 테스트", key="test_tagging_api", use_container_width=True):
        test_provider = os.getenv("TAGGING_LLM_PROVIDER", "local").lower()
        test_model = os.getenv("TAGGING_LLM_MODEL", "")
        with st.spinner(f"{test_provider} 연결 테스트 중..."):
            try:
                if test_provider == "gemini":
                    from langchain_google_genai import ChatGoogleGenerativeAI
                    model_name = test_model or "gemini-2.5-flash"
                    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0, max_output_tokens=32)
                    res = llm.invoke("test")
                    tokens = res.usage_metadata.get("total_tokens", 0)
                    reasoning = res.usage_metadata.get("output_token_details", {}).get("reasoning", 0)
                    st.success(f"Google Gemini ({model_name}) 연결 성공 (사용 토큰: {tokens}, thinking: {reasoning})")
                    if reasoning > 0:
                        st.warning(f"이 모델은 thinking 토큰이 활성화되어 있어 비용이 예상보다 높을 수 있습니다.")
                elif test_provider == "openai":
                    from langchain_openai import ChatOpenAI
                    model_name = test_model or "gpt-4o-mini"
                    llm = ChatOpenAI(model=model_name, temperature=0, max_tokens=10)
                    res = llm.invoke("test")
                    tokens = res.usage_metadata.get("total_tokens", 0) if hasattr(res, "usage_metadata") else "N/A"
                    st.success(f"OpenAI ({model_name}) 연결 성공 (사용 토큰: {tokens})")
                else:
                    import requests
                    ollama_url = os.getenv("OLLAMA_BASE_URL")
                    resp = requests.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=5)
                    if resp.status_code == 200:
                        models = [m["name"] for m in resp.json().get("models", [])]
                        target = test_model or "exaone3.5:2.4b"
                        if target in models:
                            st.success(f"Ollama 연결 성공 — {target} 모델 사용 가능")
                        else:
                            st.warning(f"Ollama 연결됨, 하지만 [{target}] 모델 미설치. 설치된 모델: {', '.join(models[:5])}")
                    else:
                        st.error("Ollama 서버 응답 오류")
            except Exception as e:
                err = str(e).lower()
                if "429" in err or "resource_exhausted" in err or "quota" in err:
                    st.error("크레딧(무료 할당량)이 소진되었습니다. Google AI Studio에서 결제 설정을 확인하거나, 할당량이 초기화될 때까지 기다려주세요.")
                elif "401" in err or "403" in err or "unauthenticated" in err or "permission" in err:
                    st.error("API 키가 유효하지 않습니다. [환경 설정] 탭에서 올바른 API 키를 입력해주세요.")
                elif "404" in err or "not_found" in err or "not found" in err:
                    st.error(f"선택한 모델이 더 이상 지원되지 않거나 존재하지 않습니다. 다른 모델명으로 변경해주세요.")
                elif "400" in err or "invalid_argument" in err or "invalid argument" in err:
                    st.error("모델 설정에 문제가 있습니다. 모델명이 정확한지, 해당 모델이 현재 API 키에서 사용 가능한지 확인해주세요.")
                elif "timeout" in err or "timed out" in err:
                    st.error("서버 응답 시간이 초과되었습니다. 네트워크 연결을 확인하거나 잠시 후 다시 시도해주세요.")
                elif "connection" in err or "connect" in err:
                    st.error("서버에 연결할 수 없습니다. 인터넷 연결 또는 Ollama 서버 실행 상태를 확인해주세요.")
                else:
                    st.error(f"예상치 못한 오류가 발생했습니다: {str(e)[:300]}")

st.markdown("---")
st.markdown("### 파일별 임베딩 모델 색인 현황")

with st.expander("파일별 색인 현황 상세 보기", expanded=False):
    matrix_data = fetch_file_model_matrix()
    base_col = os.getenv("VECTOR_DB_COLLECTION", "enterprise_knowledge_v3")

    if not matrix_data:
        st.info("색인된 파일이 없거나 DB 연결에 실패했습니다.")
    else:
        all_cols = sorted(set(c for row in matrix_data.values() for c in row.keys()))

        def short_name(col):
            prefix = base_col + "_"
            return col[len(prefix):] if col.startswith(prefix) else col

        def _fmt_chars(n):
            if n >= 1_000_000:
                return f"{n/1_000_000:.1f}M"
            if n >= 1_000:
                return f"{n/1_000:.1f}K"
            return str(n)

        rows = []
        model_totals = {col: {"chunks": 0, "chars": 0} for col in all_cols}
        for fname, col_map in sorted(matrix_data.items()):
            row = {"파일명": fname}
            for col in all_cols:
                if col in col_map:
                    info = col_map[col]
                    row[short_name(col)] = f"{info['chunks']}청크 / {_fmt_chars(info['chars'])}자"
                    model_totals[col]["chunks"] += info["chunks"]
                    model_totals[col]["chars"] += info["chars"]
                else:
                    row[short_name(col)] = "-"
            rows.append(row)

        df_matrix = pd.DataFrame(rows)
        st.dataframe(df_matrix, use_container_width=True, hide_index=True)

        # 모델별 합계
        st.markdown("**모델별 총 사용량**")
        summary_rows = []
        for col in all_cols:
            t = model_totals[col]
            est_tokens = int(t["chars"] / 3.5)
            summary_rows.append({
                "임베딩 모델": short_name(col),
                "총 청크": f"{t['chunks']:,}",
                "총 문자 수": f"{_fmt_chars(t['chars'])}자",
                "추정 토큰": f"{est_tokens:,}",
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)
        st.caption(f"총 {len(matrix_data)}개 파일 · {len(all_cols)}개 임베딩 모델 컬렉션 | 추정 토큰 = 총 문자수 / 3.5 (한국어 평균)")

st.markdown("---")
st.markdown("### 실시간 지식 문서 벡터화 인덱싱 현황")


col_run, col_stop, col_auto = st.columns([3, 3, 4])
with col_run:
    if st.button("전체 문서 재색인 실행", help="모든 문서를 다시 확인하여 인덱서를 전체 가동합니다."):
        try:
            target_json_path = os.path.join(BASE_DIR, "logs", "target_files.json")
            if os.path.exists(target_json_path):
                os.remove(target_json_path)

            log_path = os.path.join(BASE_DIR, "logs", "indexer.log")
            if os.path.exists(log_path):
                open(log_path, 'w', encoding='utf-8').close()

            indexer_path = os.path.join(BASE_DIR, "indexer", "rag_indexer.py")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            subprocess.Popen([sys.executable, indexer_path], cwd=BASE_DIR, env=env)
            st.toast("전체 백그라운드 인덱싱이 시작되었습니다.", icon=None)
        except Exception as e:
            st.error(f"인덱서 전체 실행 실패: {e}")

with col_stop:
    if st.button("인덱서 중지", type="secondary", help="현재 실행 중인 인덱서 프로세스를 강제 종료합니다."):
        if os.name == 'nt':
            result = subprocess.run(
                ["powershell", "-Command",
                 "Get-CimInstance Win32_Process -Filter \"CommandLine like '%rag_indexer%' and name='python.exe'\" | "
                 "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; $_.ProcessId }"],
                capture_output=True, text=True
            )
            pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip().isdigit()]
        else:
            result = subprocess.run(["pgrep", "-f", "rag_indexer.py"], capture_output=True, text=True)
            pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip().isdigit()]
            subprocess.run(["pkill", "-f", "rag_indexer.py"], capture_output=True)
        if pids:
            progress_path = os.path.join(BASE_DIR, "logs", "progress.json")
            try:
                with open(progress_path, "w", encoding="utf-8") as f:
                    json.dump({"status": "stopped", "message": "사용자에 의해 중단됨", "overall_percent": 0, "stage_progress_current": 0, "stage_progress_total": 0, "file_index": 0, "total_files": 0, "current_file": ""}, f, ensure_ascii=False)
            except Exception:
                pass
            st.toast(f"인덱서 {len(pids)}개 프로세스를 중지했습니다.")
        else:
            st.info("실행 중인 인덱서가 없습니다.")

with col_auto:
    auto_refresh = st.checkbox("자동 새로고침(1초) 활성화", value=False)

status_placeholder = st.empty()
progress_bar = st.progress(0)
log_placeholder = st.empty()

if data:
    with status_placeholder.container():
        col1, col2, col3, col4 = st.columns(4)
        total_files = data.get('total_files', 0)
        file_index = data.get('file_index', 0)
        
        # 파일 인덱스 표시 보정 (진행 중일 때는 +1, 완료 시에는 total_files)
        display_index = min(file_index + 1, total_files) if data.get("status") != "completed" else total_files
        col1.metric("전체 파일 진행률", f"{display_index} / {total_files}" if total_files > 0 else "0 / 0")
        col2.metric("현재 처리 파일", data.get("current_file", "대기 중"))
        col3.metric("현재 단계", data.get("current_stage", "-"))
        
        stage_current = data.get('stage_progress_current', 0)
        stage_total = data.get('stage_progress_total', 0)
        col4.metric("단계별 진행률", f"{stage_current} / {stage_total}" if stage_total > 0 else "-")

    overall_percent = data.get('overall_percent', 0)
    progress_bar.progress(overall_percent / 100.0, text=f"전체 진행률: {overall_percent}%")

    if data.get("status") == "completed":
        st.success("모든 문서의 지식베이스 적재가 완료되었습니다.")
    elif data.get("status") == "error":
        st.error(f"오류 발생: {data.get('message', '')}")
    else:
        with log_placeholder.container():
            st.info("배치 적재가 진행 중입니다. 이 화면은 실시간으로 업데이트됩니다.")
            st.markdown("##### 실시간 백그라운드 인덱서 로그")
            st.code(read_tail_logs(15), language="text")

        if auto_refresh:
            time.sleep(1)
            st.rerun()
st.markdown("---")
st.markdown("### 문서별 개별 임베딩 관리")

current_embed = os.getenv("GLOBAL_EMBEDDING_MODEL", "BAAI/bge-m3")
safe_model_name = current_embed.replace("/", "_").replace("-", "_")
base_collection = os.getenv("VECTOR_DB_COLLECTION", "enterprise_knowledge_v3")
collection_name = f"{base_collection}_{safe_model_name}"

indexed_sources = fetch_indexed_files(collection_name)  # DB에 저장된 source 값 목록
indexed_basenames = set(os.path.basename(s) for s in indexed_sources)  # 파일명만 추출
indexed_set = set(indexed_sources) | indexed_basenames  # 둘 다 비교 가능하도록 합집합

doc_folder = os.path.join(BASE_DIR, os.getenv("DOC_ARCHIVE_DIR", "doc_archive"))
extensions = ['*.pdf', '*.txt', '*.md', '*.xlsx', '*.xls', '*.docx', '*.doc', '*.hwp', '*.hwpx', '*.csv']
local_files = []
for ext in extensions:
    local_files.extend(glob.glob(os.path.join(doc_folder, f"**/{ext}"), recursive=True))
    
table_data = []
# 1. 로컬 파일 목록
for lf in local_files:
    fname = os.path.basename(lf)
    status = "완료" if fname in indexed_set else "미색인"
    table_data.append({"선택": False, "우선순위": 0, "파일명": fname, "상태": status, "절대경로": lf})

# 2. DB에만 존재하는 source (법제처 MCP 등 외부 연동 데이터)
local_basenames = set(os.path.basename(lf) for lf in local_files)
for src in indexed_sources:
    if src not in local_basenames and os.path.basename(src) not in local_basenames:
        table_data.append({"선택": False, "우선순위": 0, "파일명": f"{src}", "상태": "완료 (외부연동)", "절대경로": ""})

df = pd.DataFrame(table_data)

if not df.empty:
    st.info(f"선택된 임베딩 모델({current_embed})을 기준으로 현재 색인 상태를 표시합니다. **우선순위**: 숫자가 작을수록 먼저 처리 (1=최우선, 0=미지정)")
    edited_df = st.data_editor(
        df,
        column_config={
            "선택": st.column_config.CheckboxColumn("부분 실행", default=False),
            "우선순위": st.column_config.NumberColumn("우선순위", min_value=0, max_value=999, step=1, default=0, help="1=최우선, 0=미지정"),
            "절대경로": None  # 숨기기
        },
        disabled=["파일명", "상태"],
        hide_index=True,
        use_container_width=True
    )

    selected_rows = edited_df[edited_df["선택"] == True]

    if not selected_rows.empty:
        # 우선순위 순 미리보기 (0은 맨 뒤로)
        sorted_preview = selected_rows.copy()
        sorted_preview["_sort_key"] = sorted_preview["우선순위"].apply(lambda x: x if x > 0 else 9999)
        sorted_preview = sorted_preview.sort_values("_sort_key")
        st.markdown(f"**선택된 {len(sorted_preview)}건 — 처리 순서 미리보기:**")
        for idx, (_, row) in enumerate(sorted_preview.iterrows(), 1):
            pri_label = f"#{row['우선순위']}" if row['우선순위'] > 0 else "(미지정)"
            st.caption(f"  {idx}. {row['파일명']}  {pri_label}")

    st.markdown("##### 태깅 속도 제어")
    col_conc, col_delay = st.columns(2)
    with col_conc:
        tagging_concurrency = st.number_input(
            "병렬 호출 수", min_value=1, max_value=10, value=int(os.getenv("TAGGING_CONCURRENCY", "3")),
            help="동시에 API를 호출하는 수. 높을수록 빠르지만 차단 위험 증가 (권장: 3)"
        )
    with col_delay:
        tagging_delay = st.number_input(
            "호출 간격 (초)", min_value=0.0, max_value=10.0, value=float(os.getenv("TAGGING_DELAY", "0.5")), step=0.1,
            help="각 API 호출 사이 대기 시간. 차단 방지용 (권장: 0.3~1.0초)"
        )

    if st.button("선택 파일 부분 색인 실행 (우선순위 순)", type="primary"):
        if selected_rows.empty:
            st.warning("선택된 파일이 없습니다.")
        else:
            # 우선순위 정렬: 0은 맨 뒤로, 나머지는 오름차순
            sorted_rows = selected_rows.copy()
            sorted_rows["_sort_key"] = sorted_rows["우선순위"].apply(lambda x: x if x > 0 else 9999)
            sorted_rows = sorted_rows.sort_values("_sort_key")

            target_files = sorted_rows["절대경로"].tolist()
            target_json_path = os.path.join(BASE_DIR, "logs", "target_files.json")
            os.makedirs(os.path.dirname(target_json_path), exist_ok=True)
            with open(target_json_path, "w", encoding="utf-8") as f:
                json.dump(target_files, f, ensure_ascii=False)

            # 병렬/딜레이 설정 저장
            safe_set_key(ENV_PATH, "TAGGING_CONCURRENCY", str(int(tagging_concurrency)))
            safe_set_key(ENV_PATH, "TAGGING_DELAY", str(tagging_delay))

            log_path = os.path.join(BASE_DIR, "logs", "indexer.log")
            if os.path.exists(log_path):
                open(log_path, 'w', encoding='utf-8').close()

            indexer_path = os.path.join(BASE_DIR, "indexer", "rag_indexer.py")
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"
            env["TAGGING_CONCURRENCY"] = str(int(tagging_concurrency))
            env["TAGGING_DELAY"] = str(tagging_delay)
            subprocess.Popen([sys.executable, indexer_path], cwd=BASE_DIR, env=env)
            st.toast(f"{len(target_files)}개 파일 색인 시작 (병렬 {int(tagging_concurrency)}, 딜레이 {tagging_delay}초)", icon=None)
else:
    st.warning("등록된 문서가 없습니다.")

st.markdown("---")
st.markdown("### 벡터 DB 컬렉션 관리")
st.info("기존 색인 데이터를 삭제하고 재색인할 수 있습니다. 삭제된 컬렉션은 복구할 수 없으므로 주의하세요.")

all_collections = fetch_indexed_collections()
if all_collections:
    col_del_list, col_del_action = st.columns([7, 3])
    with col_del_list:
        col_options = {f"{name} ({count:,}개 청크)": name for name, count in all_collections}
        selected_display = st.multiselect(
            "삭제할 컬렉션 선택",
            options=list(col_options.keys()),
            help="여러 개를 선택하여 한번에 삭제할 수 있습니다."
        )
    with col_del_action:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("선택 컬렉션 삭제", type="secondary", use_container_width=True):
            if not selected_display:
                st.warning("삭제할 컬렉션을 선택해주세요.")
            else:
                for display_name in selected_display:
                    real_name = col_options[display_name]
                    ok, msg = delete_collection(real_name)
                    if ok:
                        st.success(f"[{real_name}] {msg}")
                    else:
                        st.error(f"[{real_name}] {msg}")
                time.sleep(1)
                st.rerun()

    # 전체 삭제 버튼 (확인 필요)
    with st.expander("전체 초기화 (모든 컬렉션 삭제)", expanded=False):
        st.warning("이 작업은 모든 임베딩 데이터를 삭제합니다. 되돌릴 수 없습니다.")
        confirm_text = st.text_input("확인을 위해 '전체삭제'를 입력하세요", key="confirm_delete_all")
        if st.button("전체 컬렉션 삭제 실행", type="primary"):
            if confirm_text == "전체삭제":
                for name, count in all_collections:
                    ok, msg = delete_collection(name)
                    if ok:
                        st.success(f"[{name}] {msg}")
                    else:
                        st.error(f"[{name}] {msg}")
                time.sleep(1)
                st.rerun()
            else:
                st.error("확인 문구가 일치하지 않습니다. '전체삭제'를 정확히 입력해주세요.")
else:
    st.caption("현재 저장된 컬렉션이 없습니다.")

# ─────────────────────────────
# 탭 2: 모델 성능 비교
# ─────────────────────────────
