import streamlit as st
import requests
import json
import time

# --- 💡 페이지 기본 설정 ---
st.set_page_config(page_title="국민권익 지능형 가이드", page_icon="🏛️", layout="wide")

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

# 사이드바 구성
with st.sidebar:
    st.image("https://img.icons8.com/clouds/100/000000/government.png", width=80)
    st.title("Admin Console")
    st.info("🏛️ GovOps RAG v3 (Guiding)")
    st.divider()
    st.subheader("⚙️ System Status")
    st.success("Main LLM: Active")
    st.success("Router LLM: Active")
    st.divider()
    if st.button("🗑️ 대화 기록 초기화"):
        st.session_state.messages = []
        st.rerun()

# 메인 헤더
st.title("🏛️ 국민권익 지능형 가이드 AI")
st.caption("민원인의 어려움을 분석하여 최적의 구제 절차와 답변을 안내해 드립니다.")

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []

# 대화 기록 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # 💡 개선된 가이드 박스 표시
        if "category" in message and "reason" in message:
            st.info(f"💡 **AI 가이드 추천:** 이 질의는 **[{message['category']}]** 절차에 해당합니다.\n\n({message['reason']})")

        st.markdown(message["content"], unsafe_allow_html=True)
        if message.get("sources"):
            with st.expander("📚 답변의 근거가 된 지침서"):
                for src in message["sources"]:
                    st.write(f"- {src}")
        if message["role"] == "assistant" and "response_time" in message:
            st.caption(f"⏱️ 응답 시간: {message['response_time']:.1f}초")

# 채팅 입력창
if prompt := st.chat_input("궁금하신 점이나 겪고 계신 어려움을 입력해 주세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        guide_placeholder = st.empty() # 친절한 가이드 공간
        full_response = ""
        sources = []
        category = None
        reason = None

        start_time = time.time()

        try:
            response = requests.post("http://localhost:8000/ask", json={"question": prompt}, stream=True, timeout=300)

            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data = json.loads(decoded[6:])

                        # 💡 실시간 라우팅 및 이유 수신
                        if data["type"] == "category":
                            category = data["content"]
                            reason = data["reason"]
                            guide_placeholder.info(f"💡 **AI 가이드 추천:** 이 질의는 **[{category}]** 절차에 해당합니다.\n\n({reason})")

                        elif data["type"] == "docs":
                            sources = data["sources"]
                            with st.expander("📚 답변의 근거 확인"):
                                for src in sources:
                                    st.write(f"📄 {src}")

                        elif data["type"] == "chunk":
                            full_response += data["content"]
                            message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)

                        elif data["type"] == "done":
                            duration = time.time() - start_time
                            message_placeholder.markdown(full_response, unsafe_allow_html=True)
                            st.caption(f"⏱️ 응답 시간: {duration:.1f}초")

        except Exception as e:
            st.error(f"⚠️ 연결 오류: {e}")

        # 기록 저장
        msg_obj = {
            "role": "assistant",
            "content": full_response,
            "sources": sources,
            "response_time": time.time() - start_time,
            "category": category,
            "reason": reason
        }
        st.session_state.messages.append(msg_obj)
