import streamlit as st
import os, sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# 권한 모듈 임포트
from server.admin_auth import verify_login, has_access, ROLE_DISPLAY

st.set_page_config(
    page_title="NuriNamu 관리자 콘솔",
    page_icon="⚖️",
    layout="wide",
)

# ── Session State 초기화 ──
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "username" not in st.session_state:
    st.session_state["username"] = None
if "role" not in st.session_state:
    st.session_state["role"] = None
if "display_name" not in st.session_state:
    st.session_state["display_name"] = None

def handle_login():
    """로그인 처리"""
    username = st.session_state.tmp_username
    password = st.session_state.tmp_password
    user = verify_login(username, password)
    if user:
        st.session_state["authenticated"] = True
        st.session_state["username"] = user["username"]
        st.session_state["role"] = user["role"]
        st.session_state["display_name"] = user["display_name"]
    else:
        st.error("❌ 아이디 또는 비밀번호가 올바르지 않거나, 비활성화된 계정입니다.")

def handle_logout():
    st.session_state["authenticated"] = False
    st.session_state["username"] = None
    st.session_state["role"] = None
    st.session_state["display_name"] = None

# ── 로그인 화면 ──
if not st.session_state["authenticated"]:
    # 컬럼으로 로그인 화면 가운데 정렬
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("⚖️ NuriNamu 관리자 로그인")
        st.markdown("엔터프라이즈 하이브리드 RAG 통합관리시스템")
        with st.form("login_form"):
            st.text_input("아이디 (Username)", key="tmp_username")
            st.text_input("비밀번호 (Password)", type="password", key="tmp_password")
            submit_btn = st.form_submit_button("로그인", on_click=handle_login)
    st.stop()  # 로그인되지 않은 경우 이후 코드 실행 안함

# ── 사이드바 ──
current_role = st.session_state["role"]
role_str = ROLE_DISPLAY.get(current_role, current_role)

st.sidebar.markdown(f"**👤 {st.session_state['display_name']}**님 환영합니다.")
st.sidebar.markdown(f"🏷️ 권한: `{role_str}`")
st.sidebar.button("로그아웃", on_click=handle_logout)

# ── 전체 내비게이션 구성 (권한별 제어) ──
ALL_PAGES = {
    "📊 시스템 현황": [
        ("monitor", "admin_pages/01_monitor.py", "배치 모니터링", "📈"),
        ("usage", "admin_pages/06_billing.py", "API 사용량", "💰"),
    ],
    "🧪 디버그 & 벤치마크": [
        ("benchmark", "admin_pages/02_benchmark.py", "모델 성능 비교", "⚖️"),
        ("debug", "admin_pages/03_debug.py", "검색 품질 디버그", "🔎"),
        ("debug", "admin_pages/12_similarity_lab.py", "유사도 분석 실험실", "🧪"),
        ("accuracy", "admin_pages/07_accuracy.py", "정확도 평가", "🎯"),
        ("security", "admin_pages/08_security.py", "입력 보안 테스트", "🛡️"),
    ],
    "🗂️ 데이터베이스": [
        ("manage", "admin_pages/04_doc_manage.py", "지식 문서 관리", "📂"),
        ("graph", "admin_pages/05_graph.py", "지식 그래프 뷰어", "🕸️"),
        ("ontology", "admin_pages/10_ontology.py", "온톨로지 관리", "🧠"),
    ],
    "📚 지식 활용": [
        ("monitor", "admin_pages/13_notebook_chat.py", "노트북 채팅 (문서 지정)", "📚"),
    ],
    "⚙️ 시스템 설정": [
        ("config", "admin_pages/09_config.py", "코어 설정", "⚙️"),
        ("prompt", "admin_pages/11_prompts.py", "프롬프트 관리", "📝"),
    ],
    "👥 사용자 관리": [
        ("users", "admin_pages/14_users.py", "사용자 계정 관리", "👥"),
    ]
}

allowed_pages = {}
for category, page_list in ALL_PAGES.items():
    valid_pages = []
    for tab_key, py_file, title, icon in page_list:
        if has_access(current_role, tab_key):
            if os.path.exists(os.path.join(BASE_DIR, py_file)):
                valid_pages.append(st.Page(py_file, title=title, icon=icon))
    if valid_pages:
        allowed_pages[category] = valid_pages

if not allowed_pages:
    st.error("접근 가능한 메뉴가 없습니다. 관리자에게 권한을 요청하세요.")
    st.stop()

pg = st.navigation(allowed_pages)
pg.run()
