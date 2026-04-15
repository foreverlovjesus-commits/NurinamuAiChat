"""
관리자 사용자 DB 초기화 스크립트
- admin_users 테이블 생성 (없을 경우)
- 최고관리자(superadmin) 계정 등록
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import dotenv_values
from cryptography.fernet import Fernet
import psycopg2
import bcrypt

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
env = dotenv_values(ENV_PATH)

def get_db_url():
    try:
        cipher = Fernet(env["MASTER_KEY"].encode())
        return cipher.decrypt(env["ENCRYPTED_DATABASE_URL"].encode()).decode()
    except Exception as e:
        print(f"DB URL 복호화 실패: {e}")
        return None

# ── 초기 관리자 계정 정보 ──────────────────────
ADMIN_USERNAME = "acrcaimanager"
ADMIN_PASSWORD = "Acrc2026!@#$%"
ADMIN_DISPLAY  = "최고관리자"
ADMIN_ROLE     = "superadmin"   # superadmin / admin / viewer
# ─────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS admin_users (
    id            SERIAL PRIMARY KEY,
    username      VARCHAR(64)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(100) NOT NULL DEFAULT '',
    role          VARCHAR(32)  NOT NULL DEFAULT 'viewer',
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_login    TIMESTAMPTZ
);
"""

UPSERT_SQL = """
INSERT INTO admin_users (username, password_hash, display_name, role)
VALUES (%s, %s, %s, %s)
ON CONFLICT (username) DO UPDATE
    SET password_hash = EXCLUDED.password_hash,
        display_name  = EXCLUDED.display_name,
        role          = EXCLUDED.role,
        is_active     = TRUE;
"""

def main():
    db_url = get_db_url()
    if not db_url:
        print("❌ DB 연결 정보를 가져올 수 없습니다.")
        sys.exit(1)

    # bcrypt 해시 생성
    hashed = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            # 테이블 생성
            cur.execute(CREATE_TABLE_SQL)
            print("✅ admin_users 테이블 확인/생성 완료")

            # 계정 등록(또는 갱신)
            cur.execute(UPSERT_SQL, (ADMIN_USERNAME, hashed, ADMIN_DISPLAY, ADMIN_ROLE))
            print(f"✅ 관리자 계정 등록 완료")
            print(f"   아이디: {ADMIN_USERNAME}")
            print(f"   권한: {ADMIN_ROLE}")
            print(f"   표시명: {ADMIN_DISPLAY}")

            # 등록된 전체 관리자 출력
            cur.execute("SELECT username, display_name, role, is_active, created_at FROM admin_users ORDER BY id;")
            rows = cur.fetchall()
            print("\n── 등록된 관리자 목록 ──────────────────")
            for r in rows:
                status = "활성" if r[3] else "비활성"
                print(f"  {r[0]} ({r[1]}) | 권한: {r[2]} | {status} | 생성: {r[4].strftime('%Y-%m-%d %H:%M')}")
        conn.close()
        print("\n✅ 완료!")
    except Exception as e:
        print(f"❌ 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
