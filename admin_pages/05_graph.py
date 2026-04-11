"""
🕸️ 지식 그래프 뷰어 페이지
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

st.markdown("### 법률 관계 지식 그래프 시각화")
st.info("법령 간의 참조, 준용, 위임 관계를 시각적인 네트워크 그래프로 확인합니다.")

try:
    from streamlit_agraph import agraph, Node, Edge, Config
    graph_path = os.path.join(BASE_DIR, "logs", "law_graph.json")
    if os.path.exists(graph_path):
        with open(graph_path, "r", encoding="utf-8") as f:
            gdata = json.load(f)
        
        if gdata.get("nodes"):
            # 중심 법령 선택 콤보박스
            node_ids = sorted([n["id"] for n in gdata["nodes"]])
            selected_law = st.selectbox("조회할 중심 법령 선택", ["전체 보기"] + node_ids)

            filtered_nodes_data = gdata["nodes"]
            filtered_edges_data = gdata.get("edges", [])

            if selected_law != "전체 보기":
                # 선택된 법령과 1촌 관계인 엣지만 추출
                filtered_edges_data = [e for e in gdata.get("edges", []) if e["source"] == selected_law or e["target"] == selected_law]
                
                # 연결된 노드들만 추출
                connected_node_ids = {selected_law}
                for e in filtered_edges_data:
                    connected_node_ids.add(e["source"])
                    connected_node_ids.add(e["target"])
                filtered_nodes_data = [n for n in gdata["nodes"] if n["id"] in connected_node_ids]

            # agraph 용 객체 생성
            nodes = []
            for n in filtered_nodes_data:
                # 선택된 중심 법령은 크고 빨간 별모양으로 강조
                if n["id"] == selected_law:
                    nodes.append(Node(id=n["id"], label=n["id"], size=35, shape="star", color="#ff4b4b"))
                else:
                    nodes.append(Node(id=n["id"], label=n["id"], size=20, shape="dot", color="#90cdf4"))
            
            edges = []
            for e in filtered_edges_data:
                article_text = e.get("article", "").strip()
                edge_label = f"{article_text}\n({e['relation']})" if article_text else e["relation"]
                
                edges.append(Edge(
                    source=e["source"], 
                    target=e["target"], 
                    label=edge_label, 
                    title=f"{article_text}: {e.get('detail', '')}", # 마우스 오버(Hover) 시 원문 내용 표시
                    color="#A0AEC0",
                    type="CURVE_SMOOTH"
                ))
            
            config = Config(
                width=1000, height=600, directed=True, 
                nodeHighlightBehavior=True, highlightColor="#F7A7A6",
                collapsible=True, 
                node={
                    'labelProperty': 'label',
                    'font': {'color': 'white', 'size': 16, 'face': 'sans-serif', 'strokeWidth': 1, 'strokeColor': '#000000'}
                },
                link={'labelProperty': 'label', 'renderLabel': True, 'font': {'color': 'gray', 'size': 12}}
            )
            
            if selected_law != "전체 보기":
                st.caption(f"🎯 중심 법령 ['{selected_law}'] 중심 지식 그래프 / 노드: {len(nodes)}개, 관계 엣지: {len(edges)}개")
            else:
                st.caption(f"추출된 전체 법률 노드: {len(nodes)}개 / 전체 관계 엣지: {len(edges)}개")
                
            agraph(nodes=nodes, edges=edges, config=config)
        else:
            st.warning("생성된 그래프 데이터가 비어있습니다. 인덱서를 실행하여 그래프를 추출하세요.")
    else:
        st.warning("`logs/law_graph.json` 파일이 없습니다. 문서 인덱싱 시 자동 생성됩니다.")
except ImportError:
    st.error("그래프 시각화를 위해 패키지 설치가 필요합니다.")
    st.code("pip install streamlit-agraph", language="bash")

# ─────────────────────────────
# 탭 3: API 사용량 모니터링
# ─────────────────────────────
