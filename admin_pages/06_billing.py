"""
💰 API 사용량 페이지
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

st.markdown("### LLM API 사용량 모니터링")
st.info("체팅봇 서버에서 매 LLM 호출마다 토큰 수, 응답 시간, 성공/실패 여부를 자동으로 기록합니다. 예상 비용은 각 모델의 공식 단가 기준으로 계산됩니다.")

summary = usage_tracker.get_summary()

# 요약 카드
c1, c2, c3, c4 = st.columns(4)
c1.metric("오늘 호출", f"{summary['today_calls']:,}회")
c2.metric("오늘 토큰", f"{summary['today_tokens']:,}")
c3.metric("오늘 예상 비용", f"${summary['today_cost']:.4f}")
c4.metric("오늘 실패", f"{summary['today_errors']:,}회",
         delta=None if summary['today_errors'] == 0 else f"{summary['today_errors']}",
         delta_color="inverse")

st.markdown("---")
c5, c6, c7, c8 = st.columns(4)
c5.metric("누적 호출", f"{summary['total_calls']:,}회")
c6.metric("누적 토큰", f"{summary['total_tokens']:,}")
c7.metric("누적 예상 비용", f"${summary['total_cost']:.4f}")
c8.metric("평균 응답시간", f"{summary['avg_latency']:,}ms")

# 일별 통계 테이블
st.markdown("---")
st.markdown("#### 일별 사용량 통계")
daily_stats = usage_tracker.get_daily_stats(days=30)
if daily_stats:
    df_daily = pd.DataFrame(daily_stats)
    st.dataframe(df_daily, use_container_width=True, hide_index=True)

    # 차트: 일별 토큰 사용량 추이
    if len(df_daily) > 1:
        chart_data = df_daily[['날짜', '입력 토큰', '출력 토큰']].copy()
        chart_data = chart_data.set_index('날짜')
        st.bar_chart(chart_data)
else:
    st.caption("아직 사용 데이터가 없습니다. 체팅봇에서 질문을 하면 자동으로 기록됩니다.")

# 모델별 통계 테이블
st.markdown("---")
st.markdown("#### 모델별 사용량 통계")
model_stats = usage_tracker.get_model_stats(days=30)
if model_stats:
    df_model = pd.DataFrame(model_stats)
    st.dataframe(df_model, use_container_width=True, hide_index=True)
else:
    st.caption("아직 모델별 데이터가 없습니다.")

# 최근 오류 로그
st.markdown("---")
with st.expander("최근 실패 로그 (20건)"):
    errors = usage_tracker.get_recent_errors(limit=20)
    if errors:
        df_err = pd.DataFrame(errors)
        st.dataframe(df_err, use_container_width=True, hide_index=True)
    else:
        st.success("실패 기록이 없습니다.")

# 단가 참고표
with st.expander("모델별 토큰 단가 참고표 (USD / 100만 토큰)"):
    pricing_rows = []
    for model, prices in usage_tracker.PRICING.items():
        if model != "_default":
            pricing_rows.append({"Model": model, "Input ($/1M)": prices['input'], "Output ($/1M)": prices['output']})
    st.dataframe(pd.DataFrame(pricing_rows), use_container_width=True, hide_index=True)
    st.caption("단가는 2024~2025년 기준이며, 변동될 수 있습니다. usage_tracker.py 의 PRICING 딕셔너리에서 수정 가능합니다.")


# ─────────────────────────────
# 탭: 🎯 정확도 평가
# ─────────────────────────────
