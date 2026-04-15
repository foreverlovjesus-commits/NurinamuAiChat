"""
📚 NotebookLM 스타일 문서 채팅
그룹: 🧪 디버그 & 벤치마크
"""
import streamlit as st
import os
import sys
import time
import json
import asyncio
from dotenv import load_dotenv

# 공통 유틸리티 로드
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)
load_dotenv(os.path.join(_BASE, ".env"))

from admin_shared_utils import (
    get_db_url, fetch_file_model_matrix
)
from rag.rag_engine import RAGEngineV3
from retriever.factory import get_retriever

st.set_page_config(page_title="Notebook Chat", page_icon="📚", layout="wide")

st.markdown("### 📚 NotebookLM 스타일 문서 전용 채팅")
st.info("지정한 문서(들) 내의 내용으로만 답변을 제한합니다. 특정 법령 전문이나 내부 지침서만 골라서 질의하고 싶을 때 사용하세요.")

# ── 사이드바: 문서 선택 ──
with st.sidebar:
    st.header("📂 대상 문서 선택")
    file_matrix = fetch_file_model_matrix()
    all_files = sorted(list(file_matrix.keys()))
    
    if not all_files:
        st.warning("색인된 문서가 없습니다. [지식 문서 관리]에서 먼저 문서를 등록하세요.")
        selected_sources = []
    else:
        st.write(f"총 {len(all_files)}개의 문서를 찾았습니다.")
        select_all = st.checkbox("전체 선택", value=False)
        if select_all:
            selected_sources = st.multiselect("채팅에 사용할 문서들을 선택하세요", all_files, default=all_files)
        else:
            selected_sources = st.multiselect("채팅에 사용할 문서들을 선택하세요", all_files)
    
    st.divider()
    if st.button("대화 기록 초기화"):
        st.session_state.messages = []
        st.rerun()

# ── 채팅 인터페이스 ──
if "messages" not in st.session_state:
    st.session_state.messages = []

# 기존 메시지 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)

# 사용자 입력
if prompt := st.chat_input("선택한 문서에 대해 궁금한 점을 물어보세요"):
    if not selected_sources:
        st.error("최소 하나 이상의 문서를 선택해야 합니다.")
    else:
        # 사용자 메시지 저장 및 표시
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt, unsafe_allow_html=True)

        # AI 메시지 생성
        with st.chat_message("assistant"):
            status = st.status("🧠 답변 생성 파이프라인 (시각화)", expanded=True)
            status.write("⏳ 질의 분석 중...")
            
            response_placeholder = st.empty()
            global full_response
            full_response = ""
            source_placeholder = st.empty()
            
            # RAG 엔진 초기화
            db_url = get_db_url()
            retriever = get_retriever(db_url)
            rag_engine = RAGEngineV3(retriever)

            async def get_streaming_response():
                global full_response
                # include_sources 파라미터를 사용하여 특정 문서로 제한
                async for chunk_str in rag_engine.generate_stream(prompt, include_sources=selected_sources):
                    if chunk_str.startswith("data: "):
                        try:
                            data = json.loads(chunk_str[6:].strip())
                            if data["type"] == "category":
                                status.write(f"🎯 질문 카테고리/의도 판단 완료: **{data.get('content', '')}**")
                                status.write("📚 DB 문헌 탐색 및 검색 중...")
                            elif data["type"] == "sources":
                                sources = data.get("sources", [])
                                status.write(f"✅ 관련 문서 탐색 완료 (관련도 높은 {len(sources)}건 추출됨)")
                                if sources:
                                    status.write("📄 참조 출처: " + ", ".join(sources[:3]) + ("..." if len(sources)>3 else ""))
                                status.write("🤖 LLM 답변 생성 중...")
                            elif data["type"] == "chunk":
                                if not full_response:
                                    status.update(label="답변 출력 중...", state="running", expanded=False)
                                full_response += data["content"]
                                response_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)
                            elif data["type"] == "done":
                                status.update(label="✅ 답변 생성 완료", state="complete", expanded=False)
                        except Exception:
                            continue
                return full_response

            # 비동기 제너레이터 실행
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            final_ans = loop.run_until_complete(get_streaming_response())
            
            response_placeholder.markdown(final_ans, unsafe_allow_html=True)
            st.session_state.messages.append({"role": "assistant", "content": final_ans})

st.markdown("---")
if selected_sources:
    st.caption(f"현재 선택된 필터링 대상: {', '.join(selected_sources[:3])} {'외 ' + str(len(selected_sources)-3) + '건' if len(selected_sources) > 3 else ''}")
else:
    st.caption("문서를 선택하지 않으면 답변이 생성되지 않습니다.")
