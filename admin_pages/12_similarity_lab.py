"""
🧪 유사도 분석 실험실 페이지 (v2)
그룹: 🧪 디버그 & 벤치마크
"""
import streamlit as st
import os
import sys
import asyncio
import pandas as pd
from dotenv import load_dotenv

# 공통 유틸리티 로드
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BASE)
load_dotenv(os.path.join(_BASE, ".env"))
from admin_shared_utils import get_db_url, fetch_indexed_files, fetch_indexed_collections

st.set_page_config(page_title="유사도 분석 실험실", layout="wide")

st.title("🧪 유사도 분석 실험실 (Multi-Doc)")
st.markdown("복수 문서를 선택하여 질문과의 유사도를 비교하고, 부과된 가중치(Bonus)가 포함된 최종 점수를 시뮬레이션합니다.")

db_url = get_db_url()
if not db_url:
    st.error("DB 연결 정보를 찾을 수 없습니다.")
    st.stop()

# 1. 문서 선택 및 가중치 설정 로드
st.sidebar.subheader("1. 분석 대상 및 가중치")
collections = fetch_indexed_collections()
if not collections:
    st.warning("DB에 색인된 컬렉션이 없습니다.")
    st.stop()

col_names = [c[0] for c in collections]
selected_col = st.sidebar.selectbox("컬럭션 선택", col_names)

all_files = fetch_indexed_files(selected_col)
if not all_files:
    st.warning("해당 컬렉션에 문서가 없습니다.")
    st.stop()

# 가중치 설정 로드
type_weights = {
    "case": float(os.getenv("WEIGHT_CASE", "2.0")),
    "faq": float(os.getenv("WEIGHT_FAQ", "1.0")),
    "legal": float(os.getenv("WEIGHT_LEGAL", "0.0")),
    "general": float(os.getenv("WEIGHT_GENERAL", "0.0"))
}

with st.sidebar.expander("현재 시스템 가중치 확인"):
    st.write(f"- 유권해석/판례(case): `+{type_weights['case']}`")
    st.write(f"- 사례집/FAQ(faq): `+{type_weights['faq']}`")
    st.write(f"- 법령/일반: `+0.0`")

# 파일명 검색 필터
search_file_query = st.sidebar.text_input("🔍 문서 검색 (파일명)", placeholder="예: 청탁금지법")
filtered_files = all_files
if search_file_query:
    filtered_files = [f for f in all_files if search_file_query.lower() in f.lower()]

if not filtered_files:
    st.sidebar.error("검색 결과가 없습니다.")
    st.stop()

# 복수 선택 (Multiselect)
default_files = []
for f in filtered_files:
    if "유권해석" in f and "사례집" in f:
        default_files.append(f)
        break

target_files = st.sidebar.multiselect(
    f"분석 대상 문서 선택 ({len(filtered_files)}개 중)", 
    filtered_files, 
    default=default_files
)

# 2. 질문 입력
st.subheader("2. 유사도 측정 및 가중치 시뮬레이션")
query = st.text_input("분석할 질문을 입력하세요", placeholder="예: 명절에 교사에게 선물을 보내도 되나요?")

if query and target_files:
    with st.spinner("복수 문서 교차 검색 중..."):
        from retriever.factory import get_retriever
        retriever = get_retriever(db_url)
        
        # 모든 선택된 파일에 대해 검색 수행
        all_results = []
        
        # PGVector 검색 (L2 Distance 기반)
        for t_file in target_files:
            filter_dict = {"source": t_file}
            docs_with_score = asyncio.run(asyncio.to_thread(
                retriever.vectorstore.similarity_search_with_score,
                query,
                k=5, 
                filter=filter_dict
            ))
            
            for doc, dist in docs_with_score:
                dt = doc.metadata.get("doc_type", "general")
                bonus = type_weights.get(dt, 0.0)
                
                # 유사도율 계산 (임시 로직: 1 - dist 를 백분율로, 거리가 1.0 이상이면 0%에 가까워짐)
                # 보통 BGE-M3 L2 거리는 0.2~0.8 사이
                sim_rate = max(0.0, (1.0 - dist)) * 100
                
                # 최종 시뮬레이션 점수 (하이브리드: 유사도율 / 10 + 가중치)
                # 위원님이 최근 보신 "높을수록 좋은 점수" 체계로 변환
                final_sim_score = (sim_rate / 10.0) + bonus
                
                all_results.append({
                    "문서명": os.path.basename(t_file),
                    "유형": dt,
                    "거리(Dist)": round(dist, 4),
                    "유사도율": f"{sim_rate:.1f}%",
                    "가중치": f"+{bonus}",
                    "최종 시뮬레이션 점수": round(final_sim_score, 2),
                    "본문": doc.page_content
                })
        
        if not all_results:
            st.error("결과를 찾을 수 없습니다.")
        else:
            # 데이터프레임 변환 및 정렬
            df = pd.DataFrame(all_results)
            # 최종 점수 기준 내림차순 정렬
            df = df.sort_values(by="최종 시뮬레이션 점수", ascending=False).reset_index(drop=True)
            df.index += 1 # 1부터 시작
            
            st.success(f"총 {len(target_files)}개 문서에서 {len(all_results)}개의 관련 지점을 찾았습니다.")
            
            # 테이블 출력
            st.dataframe(
                df[["최종 시뮬레이션 점수", "유사도율", "가중치", "유형", "문서명", "거리(Dist)"]],
                use_container_width=True
            )
            
            # 상세 내용 상세 보기
            st.subheader("📄 매칭된 본문 상세 내역")
            for idx, row in df.iterrows():
                with st.expander(f"[{idx}위] {row['문서명']} (점수: {row['최종 시뮬레이션 점수']})"):
                    st.write(f"**문서 유형**: {row['유형']} | **순수 유사도**: {row['유사도율']}")
                    st.info(row["본문"])

elif query and not target_files:
    st.info("왼쪽 사이드바에서 분석할 문서를 1개 이상 선택해 주세요.")

st.sidebar.info("""
💡 **점수 계산 공식 (실험실)**
1. **유사도율**: 벡터 간의 거리(Distance)를 확률(0~100%)로 변환한 값입니다.
2. **최종 점수**: (유사도율 ÷ 10) + 가중치 점수
   - 예: 유사도 80% (8.0점) + 유권해석 가중치 (2.0점) = **10.0점**
   - 이 점수가 높을수록 채팅 답변의 최우선 근거로 채택됩니다.
""")
