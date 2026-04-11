"""
admin_console.py
NuriNamu 관리자 콘솔 - Multi-Page App 진입점
실행: streamlit run admin_console.py
"""
import streamlit as st
import os, sys
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
load_dotenv(os.path.join(BASE_DIR, ".env"))

st.set_page_config(
    page_title="NuriNamu 관리자 콘솔",
    page_icon="⚖️",
    layout="wide",
)

# ── 내비게이션 구성 ──
pages = {
    "📊 시스템 현황": [
        st.Page("admin_pages/01_monitor.py", title="배치 모니터링", icon="📈"),
        st.Page("admin_pages/06_billing.py", title="API 사용량", icon="💰"),
    ],
    "🧪 디버그 & 벤치마크": [
        st.Page("admin_pages/02_benchmark.py", title="모델 성능 비교", icon="⚖️"),
        st.Page("admin_pages/03_debug.py", title="검색 품질 디버그", icon="🔎"),
        st.Page("admin_pages/12_similarity_lab.py", title="유사도 분석 실험실", icon="🧪"),
        st.Page("admin_pages/07_accuracy.py", title="정확도 평가", icon="🎯"),
        st.Page("admin_pages/08_security.py", title="입력 보안 테스트", icon="🛡️"),
    ],
    "🗂️ 데이터베이스": [
        st.Page("admin_pages/04_doc_manage.py", title="지식 문서 관리", icon="📂"),
        st.Page("admin_pages/05_graph.py", title="지식 그래프 뷰어", icon="🕸️"),
        st.Page("admin_pages/10_ontology.py", title="온톨로지 관리", icon="🧠"),
    ],
    "📚 지식 활용": [
        st.Page("admin_pages/13_notebook_chat.py", title="노트북 채팅 (문서 지정)", icon="📚"),
    ],
    "⚙️ 시스템 설정": [
        st.Page("admin_pages/09_config.py", title="코어 설정", icon="⚙️"),
        st.Page("admin_pages/11_prompts.py", title="프롬프트 관리", icon="📝"),
    ],
}

pg = st.navigation(pages)
pg.run()
