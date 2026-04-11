"""
audit_logger.py — 공공기관 납품 감사 로그 모듈
조달청 납품 요건: 모든 API 호출 이력을 비식별화하여 기록

환경변수:
    AUDIT_STORE_QUESTION_PREVIEW (bool, 기본 false)
        true 설정 시 질문 앞 50자를 question_preview 필드에 추가 저장합니다.
        오류 원인 추적에 유용하며, 개인정보보호법 제3조(최소수집 원칙) 상 민감정보가
        포함될 우려가 있는 경우 false(기본값)를 유지하세요.
"""
import hashlib
import logging
import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── 환경변수 설정 ────────────────────────────────────────────────────────────
_STORE_PREVIEW: bool = os.getenv("AUDIT_STORE_QUESTION_PREVIEW", "false").lower() == "true"
_PREVIEW_LENGTH: int = int(os.getenv("AUDIT_QUESTION_PREVIEW_LENGTH", "50"))


def _make_question_preview(question: str) -> Optional[str]:
    """
    질문 미리보기 문자열 생성.
    환경변수 비활성화 시 None 반환 → DB 저장 필드 미포함.
    """
    if not _STORE_PREVIEW:
        return None
    preview = question[:_PREVIEW_LENGTH].strip()
    # 마지막 단어가 잘리지 않도록 마지막 공백 기준 절단 (선택)
    if len(question) > _PREVIEW_LENGTH and " " in preview:
        preview = preview.rsplit(" ", 1)[0]
    return preview + ("…" if len(question) > _PREVIEW_LENGTH else "")


# ── 비동기 감사 로그 기록 ──────────────────────────────────────────────────────
async def log_audit_event(
    db_manager,
    session_id: str,
    user_ip: str,
    question: str,
    request_id: str,
    response_time_ms: int,
    success: bool,
    error_code: Optional[str] = None,
) -> None:
    """
    감사 로그를 DB에 비동기 기록합니다.

    개인정보 비식별화 정책:
        - 질문 원문: SHA-256 해시값만 저장 (기본)
        - 질문 미리보기: AUDIT_STORE_QUESTION_PREVIEW=true 시 앞 50자 추가 저장
        - IP 주소: SHA-256 해시 앞 16자만 저장
    """
    question_hash   = hashlib.sha256(question.encode("utf-8")).hexdigest()
    ip_hash         = hashlib.sha256(user_ip.encode("utf-8")).hexdigest()[:16]
    question_preview = _make_question_preview(question)

    record = {
        "timestamp":        datetime.now(timezone.utc).isoformat(),
        "session_id":       session_id,
        "user_ip_hash":     ip_hash,
        "question_hash":    question_hash,
        "question_length":  len(question),
        "request_id":       request_id,
        "response_time_ms": response_time_ms,
        "success":          success,
        "error_code":       error_code,
    }

    # 미리보기가 활성화된 경우에만 필드 추가 (비활성 시 키 자체 미포함)
    if question_preview is not None:
        record["question_preview"] = question_preview

    try:
        if db_manager:
            await db_manager.save_audit_log(record)
    except Exception as exc:
        # 감사 로그 실패가 서비스에 영향을 주지 않도록 예외를 삼킵니다.
        logger.warning("감사 로그 저장 실패 (non-critical): %s", exc)

    # 구조화된 서버 로그도 병행 기록
    preview_log = f" preview={question_preview!r}" if question_preview else ""
    logger.info(
        "[AUDIT] request_id=%s session=%s ip_hash=%s q_len=%d resp_ms=%d success=%s error=%s%s",
        request_id,
        session_id[:8],
        ip_hash,
        len(question),
        response_time_ms,
        success,
        error_code or "-",
        preview_log,
    )
