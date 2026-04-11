"""
🎯 정확도 평가 페이지
그룹: 🧪 디버그 & 벤치마크
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

st.markdown("### 🎯 RAG 응답 정확도 평가 (골든 테스트셋)")
st.info(
    "미리 정의된 골든 테스트셋(46개 질문)을 이용하여 RAG 시스템의 법령 분류 정확도와 "
    "검색 히트율을 자동으로 측정합니다. **DB와 LLM 서버가 모두 가동 중일 때 실행하세요.**"
)

DATASET_FILE   = os.path.join(BASE_DIR, "tests", "golden_dataset.json")
LATEST_REPORT  = os.path.join(BASE_DIR, "logs", "accuracy_reports", "latest.json")
REPORT_DIR_ACC = os.path.join(BASE_DIR, "logs", "accuracy_reports")

# 골든 데이터셋 미리보기
with st.expander("📋 골든 테스트셋 내용 보기", expanded=False):
    if os.path.exists(DATASET_FILE):
        with open(DATASET_FILE, encoding="utf-8") as _f:
            _ds = json.load(_f)
        _df = pd.DataFrame([{
            "ID": c["id"], "질문": c["question"],
            "정답 카테고리": c["expected_category"],
            "기대 키워드": ", ".join(c["expected_keywords"]),
        } for c in _ds])
        st.dataframe(_df, use_container_width=True, hide_index=True)
        _cat = _df["정답 카테고리"].value_counts().reset_index()
        _cat.columns = ["카테고리", "문항 수"]
        st.markdown("**카테고리별 문항 분포**")
        st.dataframe(_cat, use_container_width=True, hide_index=True)
    else:
        st.warning("`tests/golden_dataset.json` 파일을 찾을 수 없습니다.")

st.markdown("---")
st.markdown("#### ▶ 평가 실행")
_c1, _c2, _c3 = st.columns([2, 5, 3])
with _c1:
    _topk = st.number_input("Top-K (검색 개수)", 1, 10, 3, key="acc_topk")
with _c2:
    _all_ids = []
    if os.path.exists(DATASET_FILE):
        with open(DATASET_FILE, encoding="utf-8") as _f:
            _all_ids = [c["id"] for c in json.load(_f)]
    _sel_ids = st.multiselect("평가 케이스 선택 (비워두면 전체 실행)", _all_ids, key="acc_ids")
with _c3:
    st.markdown("<br>", unsafe_allow_html=True)
    _run = st.button("🚀 평가 실행", type="primary", use_container_width=True, key="acc_run")

if _run:
    _cmd = [sys.executable, "-m", "tests.test_rag_accuracy",
            "--top-k", str(_topk), "--report", "json", "--quiet"]
    if _sel_ids:
        _cmd += ["--ids"] + _sel_ids
    try:
        _env2 = os.environ.copy(); _env2["PYTHONIOENCODING"] = "utf-8"
        with st.spinner("🔍 정확도 평가 진행 중... (LLM 호출 포함, 수분 소요)"):
            _proc = subprocess.run(_cmd, cwd=BASE_DIR, capture_output=True,
                                   text=True, encoding="utf-8", timeout=600, env=_env2)
        if _proc.returncode == 0:
            st.success("✅ 평가 완료! 아래에서 결과를 확인하세요.")
        else:
            st.error(f"❌ 평가 실패\n```\n{_proc.stderr[-2000:]}\n```")
    except subprocess.TimeoutExpired:
        st.error("⏱️ 평가 시간 초과 (10분). LLM 서버 응답 속도를 확인하세요.")
    except Exception as _e:
        st.error(f"실행 오류: {_e}")
    time.sleep(0.5)
    st.rerun()

st.markdown("---")
st.markdown("#### 📊 최근 평가 결과")
if not os.path.exists(LATEST_REPORT):
    st.info("아직 평가 결과가 없습니다. 위에서 '평가 실행' 버튼을 눌러주세요.")
else:
    with open(LATEST_REPORT, encoding="utf-8") as _f:
        _rpt = json.load(_f)
    _sum  = _rpt.get("summary", {})
    _dets = _rpt.get("details", [])

    _ma, _mb, _mc, _md = st.columns(4)
    _cp = float(_sum.get("category_accuracy", 0)) * 100
    _hp = float(_sum.get("retrieval_hit_rate", 0)) * 100
    _ma.metric("카테고리 분류 정확도", _sum.get("category_accuracy_pct", "-"),
               delta=f"목표 90% {'✅' if _cp >= 90 else '❌'}",
               delta_color="normal" if _cp >= 90 else "inverse")
    _mb.metric("검색 히트율 @K", _sum.get("retrieval_hit_rate_pct", "-"),
               delta=f"목표 85% {'✅' if _hp >= 85 else '❌'}",
               delta_color="normal" if _hp >= 85 else "inverse")
    _mc.metric("평균 키워드 커버리지",
               f"{float(_sum.get('avg_keyword_coverage', 0)) * 100:.1f}%")
    _md.metric("평균 응답 지연", f"{_sum.get('avg_latency_ms', 0):,}ms")
    st.caption(
        f"📅 평가 시각: {_sum.get('evaluated_at', '-')}  "
        f"| 총 {_sum.get('total_cases', 0)}개 케이스  "
        f"| Top-{_sum.get('top_k', 3)}"
    )

    _wrong = _sum.get("misclassified", [])
    if _wrong:
        st.warning(f"⚠️ 카테고리 오분류 {len(_wrong)}건 — 아래 상세 결과에서 확인하세요.")

    st.markdown("---")
    st.markdown("#### 케이스별 상세 결과")
    _ff, _ = st.columns([3, 7])
    with _ff:
        _filt = st.selectbox("필터", ["전체", "오분류만", "검색 미스만", "통과만"], key="acc_filter")

    _rows = []
    for _r in _dets:
        if _filt == "오분류만"    and _r["category_correct"]: continue
        if _filt == "검색 미스만" and _r["hit_at_k"]: continue
        if _filt == "통과만"      and not (_r["category_correct"] and _r["hit_at_k"]): continue
        _rows.append({
            "ID": _r["id"], "질문": _r["question"][:35] + "...",
            "정답": _r["expected_category"], "예측": _r["predicted_category"] or "-",
            "분류": "✅" if _r["category_correct"] else "❌",
            "검색히트": "✅" if _r["hit_at_k"] else "❌",
            "키워드": f"{_r['keyword_coverage'] * 100:.0f}%",
            "ms": _r["latency_ms"],
        })
    if _rows:
        st.dataframe(pd.DataFrame(_rows), use_container_width=True, hide_index=True)
    else:
        st.info("해당 필터 조건에 맞는 결과가 없습니다.")

    if _dets:
        st.markdown("#### 카테고리별 분류 정확도")
        _cs: dict = {}
        for _r in _dets:
            _cat2 = _r["expected_category"]
            _cs.setdefault(_cat2, {"total": 0, "correct": 0})
            _cs[_cat2]["total"] += 1
            if _r["category_correct"]: _cs[_cat2]["correct"] += 1
        _cdf = pd.DataFrame([
            {"카테고리": c, "정확도(%)": round(v["correct"] / v["total"] * 100, 1),
             "정답": v["correct"], "전체": v["total"]}
            for c, v in _cs.items()
        ]).sort_values("정확도(%)", ascending=False)
        st.dataframe(_cdf, use_container_width=True, hide_index=True)

    with st.expander("📁 과거 평가 리포트 목록", expanded=False):
        if os.path.exists(REPORT_DIR_ACC):
            _rfs = sorted([f for f in os.listdir(REPORT_DIR_ACC)
                           if f.startswith("accuracy_") and f.endswith(".json")], reverse=True)[:20]
            for _rf in _rfs:
                try:
                    with open(os.path.join(REPORT_DIR_ACC, _rf), encoding="utf-8") as _ff2:
                        _rd = json.load(_ff2)
                    _rs = _rd.get("summary", {})
                    st.caption(f"📄 `{_rf}` — 분류 {_rs.get('category_accuracy_pct', '-')} / "
                               f"검색 {_rs.get('retrieval_hit_rate_pct', '-')} / "
                               f"{_rs.get('total_cases', 0)}건 / {_rs.get('evaluated_at', '-')[:16]}")
                except Exception:
                    st.caption(f"📄 {_rf}")

# ─────────────────────────────
# 탭: 🛡️ 입력 보안 관리
# ─────────────────────────────
