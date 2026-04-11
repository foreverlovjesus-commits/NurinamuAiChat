"""
admin_dashboard.py → admin_console.py (Multi-Page App) 자동 빌드 스크립트
기존 admin_dashboard.py는 절대 수정하지 않습니다.
"""
import os
import textwrap

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_FILE = os.path.join(BASE_DIR, "admin_dashboard.py")
PAGES_DIR = os.path.join(BASE_DIR, "admin_pages")
UTILS_FILE = os.path.join(BASE_DIR, "admin_shared_utils.py")
CONSOLE_FILE = os.path.join(BASE_DIR, "admin_console.py")

os.makedirs(PAGES_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────────
# 1. 원본 읽기
# ─────────────────────────────────────────────────────────────────
with open(SRC_FILE, "r", encoding="utf-8") as f:
    src_lines = f.readlines()

total_lines = len(src_lines)
print(f"[빌드 시작] 원본 파일: {total_lines}줄")

# ─────────────────────────────────────────────────────────────────
# 2. 공통 헤더 구역 (탭 정의 이전까지)
# ─────────────────────────────────────────────────────────────────
TAB_DEF_LINE = 248  # st.tabs() 코드가 있는 라인 (1-indexed)
header_block = "".join(src_lines[:TAB_DEF_LINE - 1])

# ─────────────────────────────────────────────────────────────────
# 3. 탭별 블록 분리 정의 (라인 번호는 1-indexed)
# ─────────────────────────────────────────────────────────────────
TAB_BLOCKS = [
    # (파일명, 변수명, 시작라인, 끝라인, 아이콘, 메뉴명, 그룹)
    ("01_monitor.py",    "tab_monitor",   255,  741,  "📈", "배치 모니터링",       "📊 시스템 현황"),
    ("02_benchmark.py",  "tab_benchmark", 742,  847,  "⚖️", "모델 성능 비교",       "🧪 디버그 & 벤치마크"),
    ("03_debug.py",      "tab_debug",     848,  945,  "🔎", "검색 품질 디버그",     "🧪 디버그 & 벤치마크"),
    ("04_doc_manage.py", "tab_manage",    946, 1585,  "📂", "지식 문서 관리",       "🗂️ 데이터베이스"),
    ("05_graph.py",      "tab_graph",    1586, 1666,  "🕸️", "지식 그래프 뷰어",     "🗂️ 데이터베이스"),
    ("06_billing.py",    "tab_usage",    1667, 1737,  "💰", "API 사용량",           "📊 시스템 현황"),
    ("07_accuracy.py",   "tab_accuracy", 1738, 1891,  "🎯", "정확도 평가",          "🧪 디버그 & 벤치마크"),
    ("08_security.py",   "tab_security", 1892, 2027,  "🛡️", "입력 보안 테스트",     "🧪 디버그 & 벤치마크"),
    ("09_config.py",     "tab_config",   2028, 2270,  "⚙️", "코어 설정",            "⚙️ 시스템 설정"),
    ("10_ontology.py",   "tab_ontology", 2271, 2326,  "🧠", "온톨로지 관리",        "🗂️ 데이터베이스"),
    ("11_prompts.py",    "tab_prompt",   2327, total_lines, "📝", "프롬프트 관리", "⚙️ 시스템 설정"),
]

# ─────────────────────────────────────────────────────────────────
# 4. 공통 imports + 유틸 함수 (admin_shared_utils.py)
# ─────────────────────────────────────────────────────────────────
UTILS_CODE = textwrap.dedent("""\
    \"\"\"
    admin_shared_utils.py
    admin_console.py / admin_pages/*.py 공통 유틸리티 모듈
    \"\"\"
    import os
    import json
    import time
    import psycopg2
    from cryptography.fernet import Fernet
    from dotenv import load_dotenv

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ENV_PATH = os.path.join(BASE_DIR, ".env")
    load_dotenv(ENV_PATH)


    def safe_set_key(dotenv_path, key_to_set, value_to_set):
        \"\"\"Windows 파일 잠금/백신 프로그램 간섭 우회용 안전한 환경변수 쓰기 함수\"\"\"
        from dotenv import set_key
        for _ in range(5):
            try:
                set_key(dotenv_path, key_to_set, value_to_set)
                return
            except PermissionError:
                time.sleep(0.2)
        set_key(dotenv_path, key_to_set, value_to_set)


    def get_db_url():
        try:
            cipher = Fernet(os.getenv("MASTER_KEY").encode())
            return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
        except Exception:
            return None


    def fetch_indexed_files(collection_name):
        db_url = get_db_url()
        if not db_url:
            return []
        try:
            conn = psycopg2.connect(db_url)
            with conn.cursor() as cur:
                sql = \"\"\"
                    SELECT DISTINCT e.cmetadata->>'source'
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE c.name = %s;
                \"\"\"
                cur.execute(sql, (collection_name,))
                rows = cur.fetchall()
            conn.close()
            return [r[0] for r in rows if r[0]]
        except Exception:
            return []


    def fetch_indexed_collections():
        \"\"\"DB에서 임베딩된 컬렉션 목록을 조회하고, 포함된 문서 수와 함께 반환합니다.\"\"\"
        db_url = get_db_url()
        if not db_url:
            return []
        try:
            conn = psycopg2.connect(db_url)
            with conn.cursor() as cur:
                cur.execute(\"\"\"
                    SELECT c.name, COUNT(*) as doc_count
                    FROM langchain_pg_collection c
                    LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                    GROUP BY c.name
                    ORDER BY c.name;
                \"\"\")
                rows = cur.fetchall()
            conn.close()
            return [(r[0], r[1]) for r in rows if r[0]]
        except Exception:
            return []


    def delete_collection(collection_name):
        \"\"\"컬렉션과 해당 임베딩 데이터를 삭제합니다.\"\"\"
        db_url = get_db_url()
        if not db_url:
            return False, "DB 연결 실패"
        try:
            conn = psycopg2.connect(db_url)
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT uuid FROM langchain_pg_collection WHERE name = %s;", (collection_name,))
                row = cur.fetchone()
                if not row:
                    conn.close()
                    return False, "컬렉션을 찾을 수 없습니다"
                uuid = row[0]
                cur.execute("DELETE FROM langchain_pg_embedding WHERE collection_id = %s;", (uuid,))
                deleted_count = cur.rowcount
                cur.execute("DELETE FROM langchain_pg_collection WHERE uuid = %s;", (uuid,))
            conn.close()
            return True, f"{deleted_count:,}개 청크 삭제 완료"
        except Exception as e:
            return False, str(e)


    def fetch_file_model_matrix():
        \"\"\"파일명 x 임베딩 모델 매트릭스\"\"\"
        db_url = get_db_url()
        if not db_url:
            return {}
        try:
            conn = psycopg2.connect(db_url)
            with conn.cursor() as cur:
                cur.execute(\"\"\"
                    SELECT
                        e.cmetadata->>'source' AS filename,
                        c.name AS collection_name,
                        COUNT(*) AS chunk_count,
                        COALESCE(SUM(LENGTH(e.document)), 0) AS total_chars
                    FROM langchain_pg_embedding e
                    JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                    WHERE e.cmetadata->>'source' IS NOT NULL
                    GROUP BY filename, collection_name
                    ORDER BY filename, collection_name;
                \"\"\")
                rows = cur.fetchall()
            conn.close()
            matrix = {}
            for filename, collection_name, chunk_count, total_chars in rows:
                if filename not in matrix:
                    matrix[filename] = {}
                matrix[filename][collection_name] = {"chunks": chunk_count, "chars": total_chars}
            return matrix
        except Exception:
            return {}


    PROGRESS_FILE = os.path.join(os.path.dirname(BASE_DIR), "logs", "progress.json") \\
        if os.path.basename(BASE_DIR) == "admin_pages" \\
        else os.path.join(BASE_DIR, "logs", "progress.json")


    def load_progress():
        _pf = os.path.join(BASE_DIR, "logs", "progress.json")
        if os.path.exists(_pf):
            try:
                with open(_pf, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return None
        return None


    def read_tail_logs(lines_count=10):
        log_path = os.path.join(BASE_DIR, "logs", "indexer.log")
        if not os.path.exists(log_path):
            return "로그 파일이 생성되지 않았습니다. 인덱서를 실행해 주세요."
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return "".join(lines[-lines_count:])
        except Exception:
            return "로그를 읽어오는 중 오류가 발생했습니다."
""")

with open(UTILS_FILE, "w", encoding="utf-8") as f:
    f.write(UTILS_CODE)
print(f"[생성] admin_shared_utils.py")

# ─────────────────────────────────────────────────────────────────
# 5. 각 페이지 파일 추출 및 생성
# ─────────────────────────────────────────────────────────────────
PAGE_IMPORT_HEADER = """\
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

"""

for filename, tab_var, start_ln, end_ln, icon, menu_name, group in TAB_BLOCKS:
    page_path = os.path.join(PAGES_DIR, filename)

    # 원본 with tab_xxx: 블록에서 실제 body 추출 (들여쓰기 제거)
    block_lines = src_lines[start_ln - 1:end_ln]

    # 첫 줄이 'with tab_xxx:' 이면 제거하고 4칸 들여쓰기 해제
    body_lines = []
    for i, line in enumerate(block_lines):
        if i == 0 and line.strip().startswith(f"with {tab_var}:"):
            continue  # with 헤더 제거
        # 4칸 들여쓰기 제거
        if line.startswith("    "):
            body_lines.append(line[4:])
        else:
            body_lines.append(line)

    page_code = (
        f'"""\n{icon} {menu_name} 페이지\n그룹: {group}\n"""\n'
        + PAGE_IMPORT_HEADER
        + "".join(body_lines)
    )

    with open(page_path, "w", encoding="utf-8") as f:
        f.write(page_code)
    print(f"[생성] admin_pages/{filename}  ({len(body_lines)}줄)")

# ─────────────────────────────────────────────────────────────────
# 6. admin_console.py (진입점) 생성
# ─────────────────────────────────────────────────────────────────
# 그룹별로 페이지 분류
groups = {}
for filename, tab_var, start_ln, end_ln, icon, menu_name, group in TAB_BLOCKS:
    groups.setdefault(group, []).append((filename, icon, menu_name))

nav_code_lines = []
nav_code_lines.append('"""')
nav_code_lines.append('admin_console.py')
nav_code_lines.append('NuriNamu 관리자 콘솔 - Multi-Page App 진입점')
nav_code_lines.append('실행: streamlit run admin_console.py')
nav_code_lines.append('"""')
nav_code_lines.append('import streamlit as st')
nav_code_lines.append('import os, sys')
nav_code_lines.append('from dotenv import load_dotenv')
nav_code_lines.append('')
nav_code_lines.append('BASE_DIR = os.path.dirname(os.path.abspath(__file__))')
nav_code_lines.append('sys.path.insert(0, BASE_DIR)')
nav_code_lines.append('load_dotenv(os.path.join(BASE_DIR, ".env"))')
nav_code_lines.append('')
nav_code_lines.append('st.set_page_config(')
nav_code_lines.append('    page_title="NuriNamu 관리자 콘솔",')
nav_code_lines.append('    page_icon="⚖️",')
nav_code_lines.append('    layout="wide",')
nav_code_lines.append(')')
nav_code_lines.append('')
nav_code_lines.append('# ── 내비게이션 구성 ──')
nav_code_lines.append('pages = {')

for group, items in groups.items():
    nav_code_lines.append(f'    "{group}": [')
    for filename, icon, menu_name in items:
        nav_code_lines.append(f'        st.Page("admin_pages/{filename}", title="{menu_name}", icon="{icon}"),')
    nav_code_lines.append('    ],')

nav_code_lines.append('}')
nav_code_lines.append('')
nav_code_lines.append('pg = st.navigation(pages)')
nav_code_lines.append('pg.run()')

console_code = "\n".join(nav_code_lines) + "\n"

with open(CONSOLE_FILE, "w", encoding="utf-8") as f:
    f.write(console_code)
print(f"[생성] admin_console.py")

# ─────────────────────────────────────────────────────────────────
# 7. 구문 검사
# ─────────────────────────────────────────────────────────────────
import ast

print("\n[구문 검사 시작]")
all_ok = True
check_files = [UTILS_FILE, CONSOLE_FILE] + [
    os.path.join(PAGES_DIR, f[0]) for f in TAB_BLOCKS
]
for fp in check_files:
    try:
        with open(fp, "r", encoding="utf-8") as fh:
            ast.parse(fh.read())
        print(f"  [OK] {os.path.basename(fp)}")
    except SyntaxError as e:
        print(f"  [FAIL] {os.path.basename(fp)}: 라인 {e.lineno} - {e.msg}")
        all_ok = False

print()
if all_ok:
    print("[BUILD OK] 빌드 완료! 모든 파일 구문 이상 없음.")
    print("   실행: streamlit run admin_console.py --server.port 8502")
else:
    print("[WARN] 일부 파일에 구문 오류가 있습니다. 위 목록을 확인하세요.")
