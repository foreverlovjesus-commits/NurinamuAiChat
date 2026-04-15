"""
관리자 인증 및 RBAC 모듈
- DB 기반 로그인 검증 (bcrypt)
- 역할별 메뉴 접근 권한 정의
"""
import os
import psycopg2
import bcrypt
from dotenv import dotenv_values
from cryptography.fernet import Fernet

# ── 역할 계층 정의 ──────────────────────────────────────
# superadmin > admin > viewer
ROLE_HIERARCHY = {"superadmin": 3, "admin": 2, "viewer": 1}

# ── 탭별 최소 필요 역할 (이 역할 이상만 접근 가능) ──────────
TAB_MIN_ROLE = {
    "monitor":   "viewer",       # 배치 모니터링
    "benchmark": "admin",        # 모델 성능 비교
    "accuracy":  "admin",        # 정확도 평가
    "security":  "superadmin",   # 입력 보안
    "debug":     "admin",        # 검색 디버그
    "manage":    "admin",        # 문서 관리
    "graph":     "viewer",       # 지식 그래프
    "ontology":  "superadmin",   # 온톨로지 관리
    "prompt":    "admin",        # 프롬프트 관리
    "usage":     "admin",        # API 사용량
    "config":    "superadmin",   # 환경 설정
    "users":     "superadmin",   # 사용자 관리
}

ROLE_DISPLAY = {
    "superadmin": "최고관리자",
    "admin":      "일반관리자",
    "viewer":     "읽기전용",
}


def _get_db_url() -> str | None:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dotenv_values(os.path.join(base_dir, ".env"))
    try:
        cipher = Fernet(env["MASTER_KEY"].encode())
        return cipher.decrypt(env["ENCRYPTED_DATABASE_URL"].encode()).decode()
    except Exception:
        return None


def verify_login(username: str, password: str) -> dict | None:
    """로그인 검증. 성공 시 사용자 정보 dict 반환, 실패 시 None."""
    db_url = _get_db_url()
    if not db_url:
        return None
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash, display_name, role, is_active "
                "FROM admin_users WHERE username = %s;",
                (username,)
            )
            row = cur.fetchone()
        conn.close()

        if not row:
            return None
        hash_, display, role, is_active = row
        if not is_active:
            return None
        if bcrypt.checkpw(password.encode("utf-8"), hash_.encode("utf-8")):
            # 마지막 로그인 시간 갱신
            try:
                conn2 = psycopg2.connect(db_url)
                conn2.autocommit = True
                with conn2.cursor() as cur:
                    cur.execute(
                        "UPDATE admin_users SET last_login = NOW() WHERE username = %s;",
                        (username,)
                    )
                conn2.close()
            except Exception:
                pass
            return {"username": username, "display_name": display, "role": role}
        return None
    except Exception:
        return None


def has_access(user_role: str, tab_key: str) -> bool:
    """현재 역할이 해당 탭에 접근 가능한지 확인."""
    min_role = TAB_MIN_ROLE.get(tab_key, "superadmin")
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(min_role, 99)


def get_all_users() -> list[dict]:
    """전체 관리자 목록 조회 (superadmin 전용)."""
    db_url = _get_db_url()
    if not db_url:
        return []
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, username, display_name, role, is_active, created_at, last_login "
                "FROM admin_users ORDER BY id;"
            )
            rows = cur.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "username": r[1], "display_name": r[2],
                "role": r[3], "is_active": r[4],
                "created_at": r[5].strftime("%Y-%m-%d %H:%M") if r[5] else "-",
                "last_login": r[6].strftime("%Y-%m-%d %H:%M") if r[6] else "없음",
            }
            for r in rows
        ]
    except Exception:
        return []


def upsert_user(username: str, password: str, display_name: str, role: str) -> tuple[bool, str]:
    """사용자 추가 또는 수정."""
    db_url = _get_db_url()
    if not db_url:
        return False, "DB 연결 실패"
    try:
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_users (username, password_hash, display_name, role)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                    SET password_hash = EXCLUDED.password_hash,
                        display_name  = EXCLUDED.display_name,
                        role          = EXCLUDED.role;
                """,
                (username, hashed, display_name, role)
            )
        conn.close()
        return True, "저장 완료"
    except Exception as e:
        return False, str(e)


def toggle_user_active(username: str, is_active: bool) -> tuple[bool, str]:
    """계정 활성/비활성 토글."""
    db_url = _get_db_url()
    if not db_url:
        return False, "DB 연결 실패"
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE admin_users SET is_active = %s WHERE username = %s;",
                (is_active, username)
            )
        conn.close()
        return True, "상태 변경 완료"
    except Exception as e:
        return False, str(e)


def delete_user(username: str) -> tuple[bool, str]:
    """사용자 삭제 (superadmin 계정은 삭제 불가)."""
    if username == "acrcaimanager":
        return False, "최고관리자 계정은 삭제할 수 없습니다."
    db_url = _get_db_url()
    if not db_url:
        return False, "DB 연결 실패"
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("DELETE FROM admin_users WHERE username = %s;", (username,))
        conn.close()
        return True, "삭제 완료"
    except Exception as e:
        return False, str(e)
