"""
admin_shared_utils.py
admin_console.py / admin_pages/*.py 공통 유틸리티 모듈
"""
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
    """Windows 파일 잠금/백신 프로그램 간섭 우회용 안전한 환경변수 쓰기 함수"""
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
            sql = """
                SELECT DISTINCT e.cmetadata->>'source'
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = %s;
            """
            cur.execute(sql, (collection_name,))
            rows = cur.fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []


def fetch_indexed_collections():
    """DB에서 임베딩된 컬렉션 목록을 조회하고, 포함된 문서 수와 함께 반환합니다."""
    db_url = get_db_url()
    if not db_url:
        return []
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.name, COUNT(*) as doc_count
                FROM langchain_pg_collection c
                LEFT JOIN langchain_pg_embedding e ON c.uuid = e.collection_id
                GROUP BY c.name
                ORDER BY c.name;
            """)
            rows = cur.fetchall()
        conn.close()
        return [(r[0], r[1]) for r in rows if r[0]]
    except Exception:
        return []


def delete_collection(collection_name):
    """컬렉션과 해당 임베딩 데이터를 삭제합니다."""
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
    """파일명 x 임베딩 모델 매트릭스"""
    db_url = get_db_url()
    if not db_url:
        return {}
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute("""
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
            """)
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


PROGRESS_FILE = os.path.join(os.path.dirname(BASE_DIR), "logs", "progress.json") \
    if os.path.basename(BASE_DIR) == "admin_pages" \
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
