"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  📊 LLM API 사용량 추적기 (usage_tracker.py)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  - 매 LLM 호출마다 토큰 사용량, 예상 비용, 성공/실패를 기록
  - SQLite 경량 DB에 저장 (PostgreSQL 부하 없이 독립 운용)
  - 관리자 대시보드에서 일별/모델별 통계를 조회
"""

import os
import sqlite3
import threading
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "logs", "usage_stats.db")

# ─── 모델별 토큰 단가 (USD per 1M tokens, 2024~2025 기준) ───
PRICING = {
    # Google Gemini
    "gemini-2.5-flash":    {"input": 0.15,  "output": 0.60},
    "gemini-2.5-pro":      {"input": 1.25,  "output": 10.00},
    "gemini-2.0-flash":    {"input": 0.10,  "output": 0.40},
    "gemini-1.5-pro":      {"input": 3.50,  "output": 10.50},
    # OpenAI
    "gpt-4o":              {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":         {"input": 10.00, "output": 30.00},
    # Anthropic
    "claude-3-5-sonnet-latest":  {"input": 3.00, "output": 15.00},
    "claude-3-7-sonnet-latest":  {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514":  {"input": 3.00, "output": 15.00},
    # Google Embedding
    "text-embedding-004":        {"input": 0.00625, "output": 0.0},
    "embedding-001":             {"input": 0.00625, "output": 0.0},
    # OpenAI Embedding
    "text-embedding-3-small":    {"input": 0.02,    "output": 0.0},
    "text-embedding-3-large":    {"input": 0.13,    "output": 0.0},
    "text-embedding-ada-002":    {"input": 0.10,    "output": 0.0},
    # 기본값 (로컬 / 알 수 없는 모델)
    "_default":            {"input": 0.0,   "output": 0.0},
}

# ─── DB 초기화 (싱글턴) ───
_db_lock = threading.Lock()
_initialized = False

def _ensure_db():
    """사용량 기록 DB를 초기화합니다 (최초 1회)."""
    global _initialized
    if _initialized:
        return
    with _db_lock:
        if _initialized:
            return
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT    NOT NULL,
                provider    TEXT    NOT NULL,
                model       TEXT    NOT NULL,
                call_type   TEXT    DEFAULT 'main',
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                total_tokens  INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0.0,
                latency_ms  INTEGER DEFAULT 0,
                status      TEXT    DEFAULT 'success',
                error_msg   TEXT    DEFAULT '',
                question_preview TEXT DEFAULT '',
                session_id  TEXT    DEFAULT ''
            );
        """)
        # 세션별 조회를 위한 인덱스 추가
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_session ON llm_usage(session_id);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON llm_usage(timestamp);
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_provider ON llm_usage(provider);
        """)
        conn.commit()
        conn.close()
        _initialized = True
        logger.info("[UsageTracker] DB 초기화 완료: %s", DB_PATH)

def _get_pricing(model_name: str) -> dict:
    """모델명으로 토큰 단가를 조회합니다."""
    model_lower = model_name.lower()
    for key, price in PRICING.items():
        if key != "_default" and key.lower() in model_lower:
            return price
    return PRICING["_default"]

def calc_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """예상 비용을 USD로 계산합니다."""
    price = _get_pricing(model_name)
    cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
    return round(cost, 6)


# ─── 공개 API ───

def record_usage(
    provider: str,
    model: str,
    call_type: str = "main",
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
    status: str = "success",
    error_msg: str = "",
    question_preview: str = "",
    session_id: str = ""
):
    """LLM 호출 결과를 기록합니다."""
    try:
        _ensure_db()
        total_tokens = input_tokens + output_tokens
        cost = calc_cost(model, input_tokens, output_tokens)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        question_short = question_preview[:100] if question_preview else ""

        conn = sqlite3.connect(DB_PATH)
        conn.execute("""
            INSERT INTO llm_usage
            (timestamp, provider, model, call_type, input_tokens, output_tokens, total_tokens,
             estimated_cost_usd, latency_ms, status, error_msg, question_preview, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (now, provider, model, call_type, input_tokens, output_tokens, total_tokens,
              cost, latency_ms, status, error_msg, question_short, session_id))
        conn.commit()
        conn.close()
        logger.debug("[UsageTracker] 기록 완료: %s/%s tokens=%d cost=$%.4f", provider, model, total_tokens, cost)
    except Exception as e:
        logger.warning("[UsageTracker] 기록 실패: %s", e)

def record_error(
    provider: str,
    model: str,
    call_type: str = "main",
    error_msg: str = "",
    latency_ms: int = 0,
    question_preview: str = ""
):
    """LLM 호출 실패를 기록합니다."""
    record_usage(
        provider=provider, model=model, call_type=call_type,
        status="error", error_msg=error_msg[:500],
        latency_ms=latency_ms, question_preview=question_preview
    )


# ─── 통계 조회 API (관리자 대시보드용) ───

def get_daily_stats(days: int = 30) -> list:
    """최근 N일간 일별 사용량 통계를 반환합니다."""
    _ensure_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            DATE(timestamp) as day,
            COUNT(*) as total_calls,
            SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
            SUM(input_tokens) as total_input,
            SUM(output_tokens) as total_output,
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost_usd) as total_cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage
        WHERE DATE(timestamp) >= ?
        GROUP BY day
        ORDER BY day DESC;
    """, (since,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "날짜": r[0], "총 호출": r[1], "성공": r[2], "실패": r[3],
            "입력 토큰": r[4] or 0, "출력 토큰": r[5] or 0,
            "총 토큰": r[6] or 0, "예상 비용($)": round(r[7] or 0, 4),
            "평균 응답(ms)": int(r[8] or 0)
        }
        for r in rows
    ]

def get_model_stats(days: int = 30) -> list:
    """최근 N일간 모델별 사용량 통계를 반환합니다."""
    _ensure_db()
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT
            provider, model,
            COUNT(*) as total_calls,
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as error_count,
            SUM(total_tokens) as total_tokens,
            SUM(estimated_cost_usd) as total_cost,
            AVG(latency_ms) as avg_latency
        FROM llm_usage
        WHERE DATE(timestamp) >= ?
        GROUP BY provider, model
        ORDER BY total_calls DESC;
    """, (since,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "제공사": r[0], "모델": r[1], "총 호출": r[2],
            "실패": r[3], "총 토큰": r[4] or 0,
            "예상 비용($)": round(r[5] or 0, 4),
            "평균 응답(ms)": int(r[6] or 0)
        }
        for r in rows
    ]

def get_recent_errors(limit: int = 20) -> list:
    """최근 실패 로그를 반환합니다."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT timestamp, provider, model, error_msg, question_preview
        FROM llm_usage
        WHERE status = 'error'
        ORDER BY id DESC
        LIMIT ?;
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [
        {"시간": r[0], "제공사": r[1], "모델": r[2], "오류": r[3], "질문": r[4]}
        for r in rows
    ]

def get_summary() -> dict:
    """전체 요약 통계를 반환합니다."""
    _ensure_db()
    conn = sqlite3.connect(DB_PATH)
    
    # 전체 통계
    cur = conn.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END),
            SUM(total_tokens),
            SUM(estimated_cost_usd),
            AVG(latency_ms)
        FROM llm_usage;
    """)
    all_row = cur.fetchone()

    # 오늘 통계
    today = datetime.now().strftime("%Y-%m-%d")
    cur2 = conn.execute("""
        SELECT
            COUNT(*),
            SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END),
            SUM(total_tokens),
            SUM(estimated_cost_usd)
        FROM llm_usage
        WHERE DATE(timestamp) = ?;
    """, (today,))
    today_row = cur2.fetchone()
    conn.close()

    return {
        "total_calls": all_row[0] or 0,
        "total_errors": all_row[1] or 0,
        "total_tokens": all_row[2] or 0,
        "total_cost": round(all_row[3] or 0, 4),
        "avg_latency": int(all_row[4] or 0),
        "today_calls": today_row[0] or 0,
        "today_errors": today_row[1] or 0,
        "today_tokens": today_row[2] or 0,
        "today_cost": round(today_row[3] or 0, 4),
    }

def get_session_stats(session_id: str) -> dict:
    """특정 세션의 누적 통계를 반환합니다."""
    _ensure_db()
    if not session_id:
        return {}
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        SELECT
            COUNT(*),
            SUM(total_tokens),
            SUM(estimated_cost_usd),
            AVG(latency_ms)
        FROM llm_usage
        WHERE session_id = ?;
    """, (session_id,))
    row = cur.fetchone()
    conn.close()
    
    return {
        "calls": row[0] or 0,
        "total_tokens": row[1] or 0,
        "total_cost": round(row[2] or 0, 6),
        "avg_latency": int(row[3] or 0)
    }
