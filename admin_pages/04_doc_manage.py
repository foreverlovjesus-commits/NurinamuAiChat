"""
📂 지식 문서 관리 페이지
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

st.markdown("### 새 문서 업로드 및 즉시 색인")
with st.form("upload_form", clear_on_submit=True):
    subfolder = st.selectbox("저장 위치 (문서 유형 폴더)", ["법령", "판례", "FAQ", "일반"])
    uploaded_files = st.file_uploader("파일 선택 (PDF, HWPX, XLSX 등 다중 선택 가능)", accept_multiple_files=True)
    submit_upload = st.form_submit_button("업로드 및 부분 색인 실행")
    
    if submit_upload and uploaded_files:
        save_dir = os.path.join(BASE_DIR, os.getenv("DOC_ARCHIVE_DIR", "doc_archive"), subfolder)
        os.makedirs(save_dir, exist_ok=True)
        target_files = []
        for uf in uploaded_files:
            file_path = os.path.join(save_dir, uf.name)
            with open(file_path, "wb") as f:
                f.write(uf.getbuffer())
            target_files.append(file_path)
        
        # target_files.json 생성 및 인덱서 백그라운드 실행
        target_json_path = os.path.join(BASE_DIR, "logs", "target_files.json")
        os.makedirs(os.path.dirname(target_json_path), exist_ok=True)
        with open(target_json_path, "w", encoding="utf-8") as f:
            json.dump(target_files, f, ensure_ascii=False)
            
        log_path = os.path.join(BASE_DIR, "logs", "indexer.log")
        if os.path.exists(log_path):
            open(log_path, 'w', encoding='utf-8').close()
            
        indexer_path = os.path.join(BASE_DIR, "indexer", "rag_indexer.py")
        subprocess.Popen([sys.executable, indexer_path], cwd=BASE_DIR)
        st.success(f"{len(target_files)}개 파일 업로드 완료! 백그라운드 색인을 시작합니다.")

st.markdown("---")
st.markdown("### 문서(PDF, 엑셀 등) → 마크다운 변환 도구")
st.info("문서의 특성에 맞게 변환 방식을 선택할 수 있습니다. 복잡한 문서나 이미지가 많다면 LlamaParse를, 빠르고 무료로 텍스트나 엑셀 표를 추출하려면 로컬 변환을 추천합니다.")

parse_method = st.radio("변환 방식 선택", ["LlamaParse (고품질/클라우드 API)", "로컬 변환 (pdfplumber/Pandas, 빠름/무료)"], horizontal=True)
doc_to_md_file = st.file_uploader("변환할 파일 선택 (PDF, Excel, CSV 지원)", type=["pdf", "xlsx", "xls", "csv"], key="doc_to_md_uploader")

if st.button("마크다운 변환 실행", type="primary", disabled=not doc_to_md_file):
    import tempfile
    
    with st.spinner(f"문서를 마크다운으로 변환 중입니다 ({parse_method.split()[0]} 사용)..."):
        try:
            ext = os.path.splitext(doc_to_md_file.name)[1].lower()
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(doc_to_md_file.getbuffer())
                tmp_path = tmp.name
            
            if "LlamaParse" in parse_method:
                from llama_parse import LlamaParse
                # LlamaParse API 호출
                parser = LlamaParse(
                    api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
                    result_type="markdown",
                    num_workers=4,
                    language="ko"
                )
                parsed_docs = parser.load_data(tmp_path)
                full_md = "\n\n".join([doc.text for doc in parsed_docs])
            else:
                # 로컬 변환 분기 처리
                if ext == ".pdf":
                    import pdfplumber
                    md_parts = []
                    with pdfplumber.open(tmp_path) as pdf:
                        for i, page in enumerate(pdf.pages):
                            text = page.extract_text()
                            if text:
                                md_parts.append(f"## 📄 페이지 {i+1}\n\n{text}")
                    full_md = "\n\n---\n\n".join(md_parts)
                elif ext in [".xlsx", ".xls"]:
                    import pandas as pd
                    dfs = pd.read_excel(tmp_path, sheet_name=None)
                    md_parts = []
                    for sheet_name, df in dfs.items():
                        df_clean = df.dropna(how='all')
                        if not df_clean.empty:
                            md_parts.append(f"## 📊 시트명: {sheet_name}")
                            # 각 행(Row)을 개별 헤딩(###)과 리스트로 변환
                            for idx, row in df_clean.iterrows():
                                row_md = [f"### 📍 {sheet_name} - 행 {idx + 1}"]
                                for col, val in row.items():
                                    if pd.notna(val) and str(val).strip():
                                        val_str = str(val).replace('\n', '<br>')
                                        row_md.append(f"- **{col}**: {val_str}")
                                md_parts.append("\n".join(row_md))
                        else:
                            md_parts.append(f"## 📊 시트명: {sheet_name}\n\n*(빈 시트 또는 데이터 없음)*")
                    full_md = "\n\n---\n\n".join(md_parts)
                elif ext == ".csv":
                    import pandas as pd
                    df = pd.read_csv(tmp_path)
                    df_clean = df.dropna(how='all')
                    if not df_clean.empty:
                        row_mds = ["## 📊 CSV 데이터"]
                        for idx, row in df_clean.iterrows():
                            row_md = [f"### 📍 행 {idx + 1}"]
                            for col, val in row.items():
                                if pd.notna(val) and str(val).strip():
                                    val_str = str(val).replace('\n', '<br>')
                                    row_md.append(f"- **{col}**: {val_str}")
                            row_mds.append("\n".join(row_md))
                        full_md = "\n\n".join(row_mds)
                    else:
                        full_md = "*(빈 CSV 파일 또는 데이터 없음)*"
                else:
                    full_md = "지원하지 않는 파일 형식입니다."
            
            # 최종 결과물이 아예 비어있는 경우 방어 (에러 방지)
            if not full_md or not full_md.strip():
                full_md = "⚠️ 변환된 텍스트가 없습니다. (빈 문서이거나 데이터를 추출할 수 없는 형식입니다.)"

            os.remove(tmp_path) # 임시 파일 삭제
            
            st.success("✅ 변환이 완료되었습니다!")
            
            # 다운로드 버튼 및 미리보기
            st.download_button(
                label="마크다운(.md) 파일 다운로드",
                data=full_md,
                file_name=f"{os.path.splitext(doc_to_md_file.name)[0]}.md",
                mime="text/markdown"
            )
            
            with st.expander("마크다운 결과 미리보기", expanded=True):
                st.markdown(full_md)
                
        except Exception as e:
            st.error(f"변환 중 오류가 발생했습니다: {e}")
            if "LlamaParse" in parse_method:
                st.caption("`.env` 파일에 `LLAMA_CLOUD_API_KEY`가 정상적으로 설정되어 있는지 확인해주세요.")
            else:
                st.caption("오류 발생 시 터미널에서 `pip install pdfplumber pandas openpyxl`이 설치되어 있는지 확인해주세요.")

st.markdown("---")
st.markdown("### 관련 법령 등록 관리")
st.info("MCP 법령 인덱서가 자동으로 가져올 법령 목록을 관리합니다. 여기서 등록한 법령은 법령 인덱싱 및 다운로드 시 대상으로 사용됩니다.")

TARGET_LAWS_PATH = os.path.join(BASE_DIR, "logs", "target_laws.json")

def _load_target_laws():
    if os.path.exists(TARGET_LAWS_PATH):
        try:
            with open(TARGET_LAWS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _save_target_laws(laws):
    os.makedirs(os.path.dirname(TARGET_LAWS_PATH), exist_ok=True)
    with open(TARGET_LAWS_PATH, "w", encoding="utf-8") as f:
        json.dump(laws, f, ensure_ascii=False, indent=2)

current_laws = _load_target_laws()

# 현재 등록된 법령 목록 표시
if current_laws:
    st.markdown(f"**등록된 법령: {len(current_laws)}건**")
    law_table = []
    for i, law in enumerate(current_laws):
        law_table.append({"선택": False, "No": i + 1, "법령명": law})
    df_laws = pd.DataFrame(law_table)
    edited_laws = st.data_editor(
        df_laws,
        column_config={
            "선택": st.column_config.CheckboxColumn("삭제", default=False),
            "No": st.column_config.NumberColumn("No", width="small"),
        },
        disabled=["No", "법령명"],
        hide_index=True,
        use_container_width=True,
        key="law_registry_editor",
    )

    if st.button("선택 법령 삭제", key="delete_selected_laws"):
        selected_rows = edited_laws[edited_laws["선택"] == True]
        if selected_rows.empty:
            st.warning("삭제할 법령을 선택하세요.")
        else:
            names_to_delete = set(selected_rows["법령명"].tolist())
            updated = [l for l in current_laws if l not in names_to_delete]
            _save_target_laws(updated)
            st.success(f"{len(names_to_delete)}건 삭제 완료")
            time.sleep(0.5)
            st.rerun()
else:
    st.caption("등록된 법령이 없습니다.")

# 새 법령 추가
st.markdown("**법령 추가**")
col_add_input, col_add_btn = st.columns([8, 2])
with col_add_input:
    new_law_name = st.text_input("추가할 법령명", placeholder="예: 공익신고자 보호법", key="new_law_input", label_visibility="collapsed")
with col_add_btn:
    if st.button("추가", use_container_width=True, key="add_law_btn"):
        if new_law_name and new_law_name.strip():
            name = new_law_name.strip()
            if name in current_laws:
                st.warning("이미 등록된 법령입니다.")
            else:
                current_laws.append(name)
                _save_target_laws(current_laws)
                st.success(f"'{name}' 추가 완료")
                time.sleep(0.5)
                st.rerun()
        else:
            st.warning("법령명을 입력하세요.")

# 기관별 검색으로 일괄 추가
with st.expander("기관별 법령 일괄 등록", expanded=False):
    col_org_reg, col_org_btn = st.columns([8, 2])
    with col_org_reg:
        org_for_reg = st.text_input("기관명", placeholder="예: 국민권익위원회", key="org_for_registry", label_visibility="collapsed")
    with col_org_btn:
        search_for_reg = st.button("검색", use_container_width=True, key="search_org_for_reg")

    if search_for_reg and org_for_reg:
        async def _search_org_for_reg(query):
            mcp_url = os.getenv("MCP_SERVER_URL")
            client = McpLawClient(base_url=mcp_url)
            if not await client.is_healthy():
                return [], "MCP 서버에 연결할 수 없습니다."
            if not await client.initialize():
                return [], "MCP 세션 초기화 실패"

            import re
            res = await client.call_tool("search_law", {"query": query})
            if not res or "[MCP" in res or "[결과 없음]" in res:
                res = await client.call_tool("search_laws", {"query": query})
            await client.close()

            if not res or "[MCP" in res or "[결과 없음]" in res:
                return [], "검색 결과가 없습니다."

            names = re.findall(r'(?:법령명|법률명|이름|name|법명)[^\n:：]*[:：\s]+([^\n,]+)', str(res))
            return [n.strip() for n in names if len(n.strip()) > 2], None

        with st.spinner("검색 중..."):
            found_names, reg_err = asyncio.run(_search_org_for_reg(org_for_reg))

        if reg_err:
            st.error(f"{reg_err}")
        elif found_names:
            st.session_state["reg_found_laws"] = found_names
        else:
            st.warning("검색된 법령이 없습니다.")

    if "reg_found_laws" in st.session_state and st.session_state["reg_found_laws"]:
        found = st.session_state["reg_found_laws"]
        reg_selections = {}
        for name in found:
            already = " (등록됨)" if name in current_laws else ""
            reg_selections[name] = st.checkbox(f"{name}{already}", value=(name not in current_laws), key=f"reg_{name}")

        if st.button("선택 법령 일괄 등록", key="bulk_register"):
            added = 0
            for name, checked in reg_selections.items():
                if checked and name not in current_laws:
                    current_laws.append(name)
                    added += 1
            if added > 0:
                _save_target_laws(current_laws)
                st.success(f"{added}건 추가 완료")
                del st.session_state["reg_found_laws"]
                time.sleep(0.5)
                st.rerun()
            else:
                st.info("새로 추가할 법령이 없습니다.")

st.markdown("---")
st.markdown("### 법제처 MCP 연동 법령 다운로드")
st.info("MCP 서버를 통해 법령(법, 시행령, 시행규칙) 전문을 마크다운(.md) 파일로 다운로드하고 화면에 미리보기를 제공합니다.")

dl_mode = st.radio("법령 지정 방식", ["등록 법령 일괄", "직접 입력", "기관별 검색"], horizontal=True, key="dl_mode")

targets = []
submit_mcp = False

# ── 모드 1: 등록 법령 일괄 ──
if dl_mode == "등록 법령 일괄":
    if not current_laws:
        st.warning("등록된 법령이 없습니다. 위의 '관련 법령 등록 관리'에서 먼저 법령을 추가하세요.")
    else:
        st.markdown(f"**등록된 법령 {len(current_laws)}건을 일괄 다운로드합니다.**")
        for law in current_laws:
            st.caption(f"  - {law}")

        st.markdown("**다운로드 범위 선택**")
        col_r1, col_r2, col_r3 = st.columns(3)
        with col_r1:
            dl_law = st.checkbox("법률 본안", value=True, key="reg_dl_law")
        with col_r2:
            dl_decree = st.checkbox("시행령", value=True, key="reg_dl_decree")
        with col_r3:
            dl_rule = st.checkbox("시행규칙", value=True, key="reg_dl_rule")

        auto_index_after_dl = st.checkbox("다운로드 완료 후 전체 재색인 자동 실행", value=True, key="reg_auto_index")
        st.caption("활성화 시, 다운로드 성공 후 배치 모니터링 탭의 '전체 문서 재색인 실행'이 자동으로 시작됩니다.")

        submit_mcp = st.button("등록 법령 전체 다운로드 및 저장", type="primary", use_container_width=True)

        if submit_mcp:
            for law in current_laws:
                if dl_law: targets.append(law)
                if dl_decree: targets.append(law + " 시행령")
                if dl_rule: targets.append(law + " 시행규칙")

# ── 모드 2: 직접 입력 ──
elif dl_mode == "직접 입력":
    with st.form("mcp_download_form"):
        col1, col2 = st.columns([6, 4])
        with col1:
            law_query = st.text_input("법령 기본 명칭", value="부정청탁 및 금품등 수수의 금지에 관한 법률", help="정확한 법령 명칭을 입력하세요.")
        with col2:
            st.markdown("**다운로드 범위 선택**")
            dl_law = st.checkbox("법률 본안", value=True)
            dl_decree = st.checkbox("시행령", value=True)
            dl_rule = st.checkbox("시행규칙", value=True)
        submit_mcp = st.form_submit_button("법령 전문 다운로드 및 저장")

    if submit_mcp and law_query:
        if dl_law: targets.append(law_query)
        if dl_decree: targets.append(law_query + " 시행령")
        if dl_rule: targets.append(law_query + " 시행규칙")

# ── 모드 3: 기관별 검색 ──
elif dl_mode == "기관별 검색":
    st.markdown("#### 기관별 소관 법령 검색")
    col_org, col_search = st.columns([6, 2])
    with col_org:
        org_query = st.text_input("기관명 입력", value="국민권익위원회", help="예: 국민권익위원회, 교육부, 공정거래위원회", key="org_query")
    with col_search:
        st.markdown("<br>", unsafe_allow_html=True)
        search_org = st.button("소관 법령 검색", use_container_width=True)

    if search_org and org_query:
        async def search_org_laws(query):
            mcp_url = os.getenv("MCP_SERVER_URL")
            client = McpLawClient(base_url=mcp_url)
            if not await client.is_healthy():
                return [], "MCP 서버에 연결할 수 없습니다."
            if not await client.initialize():
                return [], "MCP 세션 초기화 실패"

            import re
            res = await client.call_tool("search_law", {"query": query})
            if not res or "[MCP" in res or "[결과 없음]" in res:
                res = await client.call_tool("search_laws", {"query": query})

            await client.close()

            if not res or "[MCP" in res or "[결과 없음]" in res:
                return [], "검색 결과가 없습니다."

            laws = []
            blocks = re.split(r'\n{2,}|---+|={2,}', str(res))
            for block in blocks:
                name_match = re.search(r'(?:법령명|법률명|이름|name|법명)[^\n:：]*[:：\s]+([^\n,]+)', block)
                mst_match = re.search(r'(?:[Mm][Ss][Tt]|lawId|일련번호)[^\d]*(\d{4,8})', block)
                if name_match and mst_match:
                    laws.append({"name": name_match.group(1).strip(), "mst": mst_match.group(1)})

            if not laws:
                names = re.findall(r'(?:법령명|법률명|이름|name|법명)[^\n:：]*[:：\s]+([^\n,]+)', str(res))
                msts = re.findall(r'(?:[Mm][Ss][Tt]|lawId|일련번호)[^\d]*(\d{4,8})', str(res))
                for i, name in enumerate(names):
                    if i < len(msts):
                        laws.append({"name": name.strip(), "mst": msts[i]})

            if not laws:
                return [], f"법령 목록 파싱 실패\n[MCP 응답]:\n{str(res)[:500]}"

            return laws, None

        with st.spinner("기관 소관 법령을 검색하는 중..."):
            found_laws, search_err = asyncio.run(search_org_laws(org_query))
        if search_err:
            st.error(f"{search_err}")
        elif found_laws:
            st.session_state["org_laws"] = found_laws
            st.session_state["org_name"] = org_query
        else:
            st.warning("검색된 법령이 없습니다.")

    if "org_laws" in st.session_state and st.session_state["org_laws"]:
        org_laws = st.session_state["org_laws"]
        st.success(f"'{st.session_state.get('org_name', '')}' 소관 법령 {len(org_laws)}건 발견")

        law_selections = {}
        for law in org_laws:
            label = f"{law['name']} (MST: {law['mst']})"
            law_selections[label] = st.checkbox(label, value=True, key=f"org_law_{law['mst']}")

        st.markdown("**다운로드 범위 선택**")
        col_dl1, col_dl2, col_dl3 = st.columns(3)
        with col_dl1:
            dl_law = st.checkbox("법률 본안", value=True, key="org_dl_law")
        with col_dl2:
            dl_decree = st.checkbox("시행령", value=True, key="org_dl_decree")
        with col_dl3:
            dl_rule = st.checkbox("시행규칙", value=True, key="org_dl_rule")

        submit_mcp = st.button("선택 법령 전문 다운로드 및 저장", type="primary", use_container_width=True)

        if submit_mcp:
            selected_laws = [org_laws[i] for i, (label, checked) in enumerate(law_selections.items()) if checked]
            for law in selected_laws:
                if dl_law: targets.append(law["name"])
                if dl_decree: targets.append(law["name"] + " 시행령")
                if dl_rule: targets.append(law["name"] + " 시행규칙")

# ── 공통 함수 정의 (참조 법령 다운로드에서도 재사용) ──
async def fetch_all_targets(target_list, progress_bar):
    mcp_url = os.getenv("MCP_SERVER_URL")
    client = McpLawClient(base_url=mcp_url)
    if not await client.is_healthy():
        return None, "MCP 서버에 연결할 수 없습니다."

    if not await client.initialize():
        return None, "MCP 세션 초기화 실패"

    import re
    res_dict = {}
    for idx, t_name in enumerate(target_list):
        progress_bar.progress(idx / len(target_list), text=f"[{idx+1}/{len(target_list)}] '{t_name}' 추출 중...")

        # 1단계: 법령 검색 → MST 추출
        search_res = ""
        for tool in ["search_law", "search_laws", "chain_full_research"]:
            res = await client.call_tool(tool, {"query": t_name})
            if res and "[MCP" not in res and "[결과 없음]" not in res and len(str(res).strip()) > 20:
                search_res = str(res)
                break

        if not search_res:
            res_dict[t_name] = {"error": "MCP 검색 결과 없음"}
            continue

        mst = None
        for pat in [r'[Mm][Ss][Tt][\s"\':=]+(\d{4,8})', r'lawId[\s"\':=]+(\d{4,8})', r'(?:법령)?일련번호[\s"\':=]+(\d{4,8})']:
            m = re.search(pat, search_res, re.IGNORECASE)
            if m:
                mst = m.group(1)
                break

        if not mst:
            debug = search_res[:300].replace('\n', ' ')
            res_dict[t_name] = {"error": f"MST 추출 실패\n[응답]: {debug}"}
            continue

        # 2단계: get_law_markdown으로 전문 마크다운 가져오기
        markdown = await client.call_tool("get_law_markdown", {"mst": mst})

        if not markdown or "[MCP" in markdown or "[결과 없음]" in markdown or len(markdown.strip()) < 50:
            res_dict[t_name] = {"error": f"마크다운 전문을 가져오지 못했습니다. (MST: {mst})"}
        else:
            res_dict[t_name] = {"text": markdown}

        await asyncio.sleep(0.5)

    await client.close()
    return res_dict, None

def _extract_referenced_laws(all_texts: dict, already_downloaded: set) -> list:
    """다운로드된 마크다운에서 「법률명」 패턴의 참조 법령을 추출한다."""
    import re
    ref_pattern = re.compile(r'「([^」]{3,50})」')
    # 법/령/규칙/강령 으로 끝나는 것만 법령명으로 인정
    suffix_pattern = re.compile(r'(?:법률?|법|령|규칙|강령|조례)$')
    refs = set()
    for t_name, data in all_texts.items():
        if "text" not in data:
            continue
        source_short = t_name.split("(")[0].strip()
        for m in ref_pattern.finditer(data["text"]):
            name = m.group(1).strip()
            if name == source_short or name in already_downloaded:
                continue
            if suffix_pattern.search(name) and len(name) >= 4:
                refs.add(name)
    return sorted(refs)

# ── 공통 다운로드 실행 ──
if submit_mcp and targets:
    progress_text = "MCP 서버에서 법령을 추출하는 중..."
    my_bar = st.progress(0, text=progress_text)

    results_data, err = asyncio.run(fetch_all_targets(targets, my_bar))

    if err:
        st.error(f"{err}")
    else:
        my_bar.progress(1.0, text="1차 다운로드 완료!")
        success_count = 0
        preview_data = {}

        for t_name, data in results_data.items():
            if "error" in data:
                st.error(f"{t_name}: {data['error']}")
            else:
                safe_name = t_name.replace(" ", "_").replace("/", "_")
                save_path = os.path.join(BASE_DIR, os.getenv("DOC_ARCHIVE_DIR", "doc_archive"), "법령", f"{safe_name}_전문.md")
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write(f"# {t_name}\n\n{data['text']}")
                success_count += 1
                preview_data[t_name] = {"path": save_path, "text": data["text"]}

        if success_count > 0:
            st.success(f"총 {success_count}건의 문서를 성공적으로 저장했습니다.")

            # 다운로드 후 자동 재색인 실행
            if dl_mode == "등록 법령 일괄" and auto_index_after_dl:
                st.toast("잠시 후 전체 문서 재색인을 시작합니다...")
                time.sleep(2)
                try:
                    target_json_path = os.path.join(BASE_DIR, "logs", "target_files.json")
                    if os.path.exists(target_json_path): os.remove(target_json_path)
                    log_path = os.path.join(BASE_DIR, "logs", "indexer.log")
                    if os.path.exists(log_path): open(log_path, 'w', encoding='utf-8').close()
                    indexer_path = os.path.join(BASE_DIR, "indexer", "rag_indexer.py")
                    env = os.environ.copy(); env["PYTHONIOENCODING"] = "utf-8"
                    subprocess.Popen([sys.executable, indexer_path], cwd=BASE_DIR, env=env)
                    st.success("백그라운드 재색인이 시작되었습니다. [배치 모니터링] 탭에서 진행 상황을 확인하세요.")
                except Exception as e:
                    st.error(f"자동 재색인 실행 실패: {e}")

        # ── 연계/참조 법령 자동 탐지 → session_state에 보존 ──
        already_names = set(targets) | set(t.split(" 시행")[0] for t in targets)
        ref_laws = _extract_referenced_laws(results_data, already_names)
        if ref_laws:
            st.session_state["ref_laws"] = ref_laws
        st.session_state["dl_preview_data"] = preview_data

        # 미리보기 탭
        if preview_data:
            st.markdown("---")
            st.markdown("#### 다운로드 미리보기")
            preview_tabs = st.tabs(list(preview_data.keys()))
            for i, (t_name, t_data) in enumerate(preview_data.items()):
                with preview_tabs[i]:
                    st.caption(f"저장 위치: `{t_data['path']}`")
                    with st.container(height=400):
                        st.markdown(t_data['text'])

# ── 참조 법령 다운로드 (session_state 기반, rerun에도 유지) ──
if "ref_laws" in st.session_state and st.session_state["ref_laws"]:
    ref_laws = st.session_state["ref_laws"]
    st.markdown("---")
    st.markdown(f"#### 참조 법령 {len(ref_laws)}건 발견")
    st.info("다운로드된 법령 텍스트에서 「법률명」으로 인용된 참조 법령입니다. 선택하여 추가 다운로드할 수 있습니다.")

    ref_selections = {}
    for ref_name in ref_laws:
        ref_selections[ref_name] = st.checkbox(ref_name, value=True, key=f"ref_dl_{ref_name}")

    st.markdown("**참조 법령 다운로드 범위**")
    col_ref1, col_ref2, col_ref3 = st.columns(3)
    with col_ref1:
        ref_dl_law = st.checkbox("법률 본안", value=True, key="ref_scope_law")
    with col_ref2:
        ref_dl_decree = st.checkbox("시행령", value=True, key="ref_scope_decree")
    with col_ref3:
        ref_dl_rule = st.checkbox("시행규칙", value=False, key="ref_scope_rule")

    if st.button("참조 법령 추가 다운로드", type="secondary", use_container_width=True):
        ref_targets = []
        for ref_name, checked in ref_selections.items():
            if checked:
                if ref_dl_law: ref_targets.append(ref_name)
                if ref_dl_decree: ref_targets.append(ref_name + " 시행령")
                if ref_dl_rule: ref_targets.append(ref_name + " 시행규칙")

        if ref_targets:
            ref_bar = st.progress(0, text="참조 법령 다운로드 중...")
            ref_data, ref_err = asyncio.run(fetch_all_targets(ref_targets, ref_bar))
            ref_bar.progress(1.0, text="참조 법령 다운로드 완료!")

            if ref_err:
                st.error(f"{ref_err}")
            else:
                ref_success = 0
                for rt_name, rt_data in ref_data.items():
                    if "error" in rt_data:
                        st.warning(f"{rt_name}: {rt_data['error']}")
                    else:
                        safe_name = rt_name.replace(" ", "_").replace("/", "_")
                        save_path = os.path.join(BASE_DIR, os.getenv("DOC_ARCHIVE_DIR", "doc_archive"), "법령", f"{safe_name}_전문.md")
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        with open(save_path, "w", encoding="utf-8") as f:
                            f.write(f"# {rt_name}\n\n{rt_data['text']}")
                        ref_success += 1
                if ref_success > 0:
                    st.success(f"참조 법령 {ref_success}건 추가 저장 완료.")
                    # 다운로드 완료 후 참조 목록 초기화
                    del st.session_state["ref_laws"]
                    time.sleep(1)
                    st.rerun()

st.markdown("---")
st.markdown("### 저장된 청크 및 메타데이터 태그 검수")
all_cols = fetch_indexed_collections()
if all_cols:
    col_sel, col_lim, col_btn = st.columns([5, 3, 2])
    with col_sel:
        selected_col = st.selectbox("조회할 컬렉션 선택", [c[0] for c in all_cols], label_visibility="collapsed")
    with col_lim:
        limit = st.slider("조회 건수", 10, 500, 50, label_visibility="collapsed")
    with col_btn:
        if st.button("데이터 조회", use_container_width=True):
            db_url = get_db_url()
            try:
                conn = psycopg2.connect(db_url)
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT e.document, e.cmetadata 
                        FROM langchain_pg_embedding e
                        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                        WHERE c.name = %s LIMIT %s;
                    """, (selected_col, limit))
                    rows = cur.fetchall()
                conn.close()
                
                df_chunks = pd.DataFrame([{
                    "내용(미리보기)": r[0][:100] + "..." if len(r[0])>100 else r[0],
                    "메타데이터(JSON)": json.dumps(r[1], ensure_ascii=False) if r[1] else "{}",
                    "출처": r[1].get("source", "") if r[1] else "",
                    "문서유형": r[1].get("doc_type", "") if r[1] else ""
                } for r in rows])
                st.dataframe(df_chunks, use_container_width=True)
            except Exception as e:
                st.error(f"DB 조회 에러: {e}")
else:
    st.info("조회할 컬렉션이 없습니다.")

# ─────────────────────────────
# 탭 5: 지식 그래프 시각화
# ─────────────────────────────
