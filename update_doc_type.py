import os
import psycopg2
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

def update_metadata():
    db_url = get_db_url()
    if not db_url:
        return
    
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            # 1. '사례집'이 포함된 문서 -> faq 로 변경 (먼저 실행)
            sql_faq = """
                UPDATE langchain_pg_embedding
                SET cmetadata = jsonb_set(cmetadata::jsonb, '{doc_type}', '"faq"'::jsonb, true)
                WHERE cmetadata->>'source' LIKE '%사례집%';
            """
            cur.execute(sql_faq)
            faq_updates = cur.rowcount
            
            # 2. '해석' 또는 '지침'이 포함된 문서 -> case 로 변경 (나중에 실행하여 덮어쓰기 권한 확보)
            sql_case = """
                UPDATE langchain_pg_embedding
                SET cmetadata = jsonb_set(cmetadata::jsonb, '{doc_type}', '"case"'::jsonb, true)
                WHERE cmetadata->>'source' LIKE '%해석%'
                   OR cmetadata->>'source' LIKE '%지침%';
            """
            cur.execute(sql_case)
            case_updates = cur.rowcount
            
            print("=== DB 업데이트 완료 ===")
            print(f"- 'case'(유권해석)로 변경된 청크 수: {case_updates}건")
            print(f"- 'faq'(사례집)로 변경된 청크 수: {faq_updates}건")
            
            # 업데이트 결과 요약본 출력
            cur.execute("""
                SELECT cmetadata->>'source', cmetadata->>'doc_type', COUNT(*)
                FROM langchain_pg_embedding
                WHERE cmetadata->>'source' LIKE '%해석%' 
                   OR cmetadata->>'source' LIKE '%지침%'
                   OR cmetadata->>'source' LIKE '%사례집%'
                GROUP BY cmetadata->>'source', cmetadata->>'doc_type'
                ORDER BY cmetadata->>'source';
            """)
            print("\n[현재 적용된 파일별 상태]")
            rows = cur.fetchall()
            for r in rows:
                print(f"[{r[1]}] {r[0]} ({r[2]}개 청크)")
                
    except Exception as e:
        print(f"DB 오류 발생: {e}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()

if __name__ == "__main__":
    update_metadata()
