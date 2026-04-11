import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
from cryptography.fernet import Fernet
import psycopg2

TO_DELETE = ["enterprise_knowledge_v3", "std_ops_guidelines"]

cipher = Fernet(os.getenv('MASTER_KEY').encode())
db_url = cipher.decrypt(os.getenv('ENCRYPTED_DATABASE_URL').encode()).decode()
conn = psycopg2.connect(db_url)

try:
    with conn.cursor() as cur:
        for name in TO_DELETE:
            # 1. UUID 조회
            cur.execute("SELECT uuid FROM langchain_pg_collection WHERE name = %s;", (name,))
            row = cur.fetchone()
            if not row:
                print(f"  ⚠️  [{name}] 컬렉션 없음 (이미 삭제됐거나 이름 불일치)")
                continue
            uuid = row[0]
            # 2. 임베딩 삭제
            cur.execute("DELETE FROM langchain_pg_embedding WHERE collection_id = %s;", (uuid,))
            deleted_emb = cur.rowcount
            # 3. 컬렉션 삭제
            cur.execute("DELETE FROM langchain_pg_collection WHERE uuid = %s;", (uuid,))
            print(f"  ✅ [{name}] 삭제 완료 (임베딩 {deleted_emb}개 제거)")
    conn.commit()
    print("\n🎉 레거시 컬렉션 정리 완료!")
except Exception as e:
    conn.rollback()
    print(f"❌ 오류 발생 (롤백): {e}")
finally:
    conn.close()
