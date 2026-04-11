import streamlit as st
import requests
import json

# 💡 페이지 기본 설정
st.set_page_config(page_title="누리나무 AI 법률통합지원 시스템", page_icon="🏛️", layout="centered")

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

st.title("🏛️ 누리나무 AI 법률통합지원 시스템")
st.caption("국민권익위원회 가이드라인 기반 폐쇄망(On-Premise) RAG 시스템")

# 세션 상태 초기화 (대화 기록을 기억하기 위함)
if "messages" not in st.session_state:
    st.session_state.messages = []

# 이전 대화 내용 화면에 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"], unsafe_allow_html=True)
        # 참고 문서 출처가 있다면 접이식(Expander)으로 표시
        if message.get("sources"):
            with st.expander("📚 참고 문서 출처"):
                for src in message["sources"]:
                    st.write(f"- {src}")

# 사용자 입력창
if prompt := st.chat_input("ITSM 매뉴얼이나 규정에 대해 질문해 주세요. (예: 장애 1등급 보고 체계는?)"):

    # 1. 사용자 질문을 화면에 표시하고 기록에 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. AI 답변 영역 (스트리밍으로 글자가 채워질 빈 공간)
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = ""
        sources = []

        # 💡 백엔드 API 서버(FastAPI) 호출
        try:
            # stream=True로 설정하여 서버가 보내는 조각(chunk)을 실시간으로 받음
            response = requests.post(
                "http://localhost:8000/ask",
                json={"question": prompt},
                stream=True,
                timeout=120
            )
            response.raise_for_status()

            # SSE(Server-Sent Events) 데이터 한 줄씩 파싱
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:] # "data: " 꼬리표 떼어내기
                        try:
                            data = json.loads(data_str)

                            # 문서 출처가 도착했을 때
                            if data["type"] == "docs":
                                sources = data["sources"]
                                with st.expander("📚 검색된 참고 문서", expanded=False):
                                    for src in sources:
                                        st.write(f"📄 {src}")

                            # 글자 조각이 도착했을 때 (타자기 효과)
                            elif data["type"] == "chunk":
                                full_response += data["content"]
                                message_placeholder.markdown(full_response + "▌", unsafe_allow_html=True)

                            # 에러가 발생했을 때
                            elif data["type"] == "error":
                                st.error(data["content"])

                            # 답변이 모두 끝났을 때
                            elif data["type"] == "done":
                                message_placeholder.markdown(full_response, unsafe_allow_html=True)

                        except json.JSONDecodeError:
                            pass

        except requests.exceptions.RequestException:
            full_response = "⚠️ 서버와 연결할 수 없습니다. 백엔드 API 서버(FastAPI)가 포트 8000번에서 실행 중인지 확인해 주세요."
            message_placeholder.error(full_response)

        # 3. 완성된 AI 답변을 대화 기록에 저장
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "sources": sources
        })
