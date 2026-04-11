import streamlit as st
import requests
import json
import time

# --- 💡 페이지 기본 설정 ---
st.set_page_config(page_title="고성능 Cloud RAG 챗봇", page_icon="☁️", layout="wide")

# 커스텀 CSS 주입 (FIRAC 아코디언 UI 및 마크다운 스타일링)
custom_css = """
<style>
details { border: 1px solid rgba(49, 51, 63, 0.2); border-radius: 0.5rem; padding: 0.5rem 1rem; margin-bottom: 0.8rem; background-color: rgba(249, 249, 251, 0.5); box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
summary { font-weight: 600; font-size: 1.05rem; cursor: pointer; color: #1f77b4; margin: -0.5rem -1rem; padding: 0.5rem 1rem; border-radius: 0.5rem; transition: background-color 0.2s ease; }
summary:hover { background-color: rgba(49, 51, 63, 0.05); }
details[open] summary { border-bottom: 1px solid rgba(49, 51, 63, 0.2); margin-bottom: 0.5rem; border-radius: 0.5rem 0.5rem 0 0; }
</style>
"""
st.markdown(custom_css.replace('\n', ' '), unsafe_allow_html=True)

st.title("☁️ 하이브리드 Cloud RAG (Gemini 1.5)")
st.caption("로컬 지식베이스(Vector DB)와 구글의 강력한 클라우드 모델을 결합한 지능형 시스템")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 대화 기록 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)
        if message.get("sources"):
            with st.expander("📚 참고 문서 출처"):
                for src in message["sources"]: st.write(f"- {src}")

# 채팅 입력창
if prompt := st.chat_input("클라우드 엔진에게 질문해 보세요 (예: 올해 신규 사업 리스트 알려줘)"):

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        sources = []

        start_time = time.time()

        try:
            # 8001번 포트(Cloud 서버) 호출
            response = requests.post(
                "http://localhost:8001/ask",
                json={"question": prompt},
                stream=True,
                timeout=120
            )

            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data = json.loads(decoded[6:])

                        if data["type"] == "docs":
                            sources = data["sources"]
                            with st.expander("📚 지식베이스 검색 완료"):
                                for src in sources: st.write(f"📄 {src}")

                        elif data["type"] == "chunk":
                            full_response += data["content"]
                            message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)

                        elif data["type"] == "done":
                            duration = time.time() - start_time
                            message_placeholder.markdown(full_response, unsafe_allow_html=True)
                            st.caption(f"⏱️ 클라우드 응답 속도: {duration:.1f}초")

        except Exception as e:
            st.error(f"⚠️ 연결 오류: 클라우드 API 서버(8001)가 실행 중인지 확인하세요. ({e})")

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": sources,
            "duration": duration if 'duration' in locals() else 0.0
        })
