import os
import psycopg2
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# 1. 환경변수 및 암호화 키 로드
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

def get_db_url():
    try:
        cipher = Fernet(os.getenv("MASTER_KEY").encode())
        return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
    except: return None

def check_database():
    DB_URL = get_db_url()
    if not DB_URL:
        print("🚨 보안 키가 설정되지 않았거나 잘못되었습니다. .env를 확인하세요.")
        return

    print("🔍 [V3] 시스템 데이터베이스 정밀 진단 중...\n")
    try:
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()

        # 1. 전체 데이터 개수 (V3 컬렉션 기준 필터링 권장)
        cursor.execute("SELECT count(*) FROM langchain_pg_embedding;")
        count = cursor.fetchone()[0]
        print(f"📊 총 저장된 지식 조각(Chunks): {count}개")

        # 2. 인덱스 생성 여부 확인 (HNSW, FTS)
        cursor.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'langchain_pg_embedding';")
        indexes = [row[0] for row in cursor.fetchall()]

        has_hnsw = any('hnsw' in idx.lower() for idx in indexes)
        has_fts = any('fts' in idx.lower() or 'gin' in idx.lower() for idx in indexes)

        print(f"⚡ HNSW 벡터 인덱스: {'✅ 활성화' if has_hnsw else '❌ 미생성'}")
        print(f"🔎 FTS 키워드 인덱스: {'✅ 활성화' if has_fts else '❌ 미생성'}")

        # 3. 테이블 구조(컬럼) 확인
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'langchain_pg_embedding';")
        columns = [row[0] for row in cursor.fetchall()]
        print(f"📋 보유 컬럼: {', '.join(columns)}")

        # 4. 최근 적재된 문서 샘플 (V3 메타데이터 확인)
        if count > 0:
            cursor.execute("SELECT document, cmetadata FROM langchain_pg_embedding ORDER BY uuid DESC LIMIT 1;")
            sample = cursor.fetchone()
            print("\n" + "="*50)
            print(" 📄 [최신 적재 데이터 샘플]")
            print("="*50)
            print(f"▶️ 내용: {sample[0][:200]}...")
            print(f"▶️ 메타데이터: {sample[1]}")
            print("="*50)

    except Exception as e:
        print(f"❌ DB 진단 에러: {e}")
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    check_database()
