import os
import sys
import psycopg2
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# 프로젝트 루트 추가
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv()

def run_migration():
    try:
        master_key = os.getenv("MASTER_KEY")
        encrypted_url = os.getenv("ENCRYPTED_DATABASE_URL")
        cipher = Fernet(master_key.encode())
        db_url = cipher.decrypt(encrypted_url.encode()).decode()

        print("🚀 DB 마이그레이션 V2 시작...")
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            with open("scripts/migrate_v2.sql", "r", encoding="utf-8") as f:
                cur.execute(f.read())
        conn.commit()
        conn.close()
        print("✅ DB 마이그레이션 완료!")
    except Exception as e:
        print(f"❌ 마이그레이션 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
