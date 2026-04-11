import os, psycopg2
from dotenv import load_dotenv
from cryptography.fernet import Fernet

load_dotenv()
cipher = Fernet(os.getenv('MASTER_KEY').encode())
db_url = cipher.decrypt(os.getenv('ENCRYPTED_DATABASE_URL').encode()).decode()

conn = psycopg2.connect(db_url)
with conn.cursor() as cur:
    sql = """
        SELECT c.name, COUNT(*)
        FROM langchain_pg_embedding e
        JOIN langchain_pg_collection c ON e.collection_id = c.uuid
        WHERE e.cmetadata->>'source' LIKE '%청탁금지법%'
          AND (e.cmetadata->>'source' LIKE '%유권해석%' OR e.cmetadata->>'source' LIKE '%해석%')
        GROUP BY c.name;
    """
    cur.execute(sql)
    rows = cur.fetchall()
    if not rows:
        print('해당 문서를 찾을 수 없습니다.')
    for r in rows:
        print(f"Collection: {r[0]}, Count: {r[1]}")
conn.close()
