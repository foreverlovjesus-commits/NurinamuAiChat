import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
from cryptography.fernet import Fernet
import psycopg2

cipher = Fernet(os.getenv('MASTER_KEY').encode())
db_url = cipher.decrypt(os.getenv('ENCRYPTED_DATABASE_URL').encode()).decode()
conn = psycopg2.connect(db_url)
with conn.cursor() as cur:
    cur.execute("SELECT name FROM langchain_pg_collection ORDER BY name;")
    for (name,) in cur.fetchall():
        print(f"  - {name}")
conn.close()
print("완료")
