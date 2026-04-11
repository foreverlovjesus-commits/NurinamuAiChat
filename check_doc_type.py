import os
import psycopg2
import json
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()

def get_db_url():
    try:
        cipher = Fernet(os.getenv("MASTER_KEY").encode())
        return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
    except Exception as e:
        print(f"Error decrypting DB URL: {e}")
        return None

try:
    db_url = get_db_url()
    if not db_url:
        exit(1)
    
    conn = psycopg2.connect(db_url)
    with conn.cursor() as cur:
        # '해석' 이 포함된 모든 파일 소스 조회
        sql = """
            SELECT cmetadata->>'source', cmetadata->>'doc_type', COUNT(*)
            FROM langchain_pg_embedding
            WHERE cmetadata->>'source' LIKE '%해석%'
            GROUP BY cmetadata->>'source', cmetadata->>'doc_type'
            ORDER BY cmetadata->>'source';
        """
        cur.execute(sql)
        rows = cur.fetchall()
        print("--- DB 내 '해석' 관련 문서 태깅 현황 ---")
        if not rows:
            print("해석이라는 단어가 포함된 파일이 DB에 없습니다.")
        for r in rows:
            print(f"문서명: {r[0]} | 분류(doc_type): {r[1]} | 청크 수: {r[2]}")
            
except Exception as e:
    print(f"DB 오류: {e}")
