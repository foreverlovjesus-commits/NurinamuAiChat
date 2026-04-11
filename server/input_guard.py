"""
server/input_guard.py — 입력 보안 가드 모듈
==========================================
공공기관 납품용 2중 입력 보안:

1. 프롬프트 인젝션 방지 (Prompt Injection Guard)
   - 시스템 역할 덮어쓰기 패턴 탐지 ("Ignore previous", "You are now" 등)
   - 탈출 시도 패턴 탐지 (<|end|>, [INST] 등 모델 특수 토큰)
   - 역할극(Jailbreak) 패턴 탐지

2. 개인 민감정보 감지 및 처리 (PII Guard)
   - 주민등록번호 (6자리-7자리)
   - 운전면허번호 / 여권번호
   - 금융 카드번호 (16자리)
   - 계좌번호
   - 전화번호 (선택적 마스킹)
   - 이메일 주소 (선택적 마스킹)

환경변수:
    INPUT_GUARD_ENABLED        (bool, 기본 true)  — 전체 가드 활성화
    INPUT_GUARD_PII_BLOCK      (bool, 기본 false) — PII 감지 시 요청 거부 (true) vs 마스킹 후 허용 (false)
    INPUT_GUARD_INJECTION_BLOCK (bool, 기본 true) — 인젝션 시도 시 요청 차단
    INPUT_MAX_LENGTH           (int,  기본 2000)  — 입력 최대 길이 (초과 시 거부)
"""
import re
import os
import logging
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


def _normalize_input(text: str) -> str:
    """
    2바이트 특수문자(전각 숫자·알파벳·하이픈 등) 우회 방지를 위한 전처리.

    NFKC 정규화 효과:
      ０ → 0,  １ → 1, ..., ９ → 9   (전각 숫자 → 반각)
      Ａ → A,  ａ → a                 (전각 영문 → 반각)
      ‐ → -,  － → -                 (유니코드 하이픈 변종 → ASCII 하이픈)
      \u2007 → (공백류 정규화)
    이모지·한글·한자 등 정상 문자는 그대로 유지됩니다.
    """
    normalized = unicodedata.normalize("NFKC", text)
    if normalized != text:
        logger.info(
            "[InputGuard] 입력 유니코드 정규화 적용 (전각→반각 변환 포함): %d자 → %d자",
            len(text), len(normalized)
        )
    return normalized


# ── 환경변수 ──────────────────────────────────────────────────────────────────
_ENABLED           = os.getenv("INPUT_GUARD_ENABLED", "true").lower() == "true"
_PII_BLOCK         = os.getenv("INPUT_GUARD_PII_BLOCK", "false").lower() == "true"
_INJECTION_BLOCK   = os.getenv("INPUT_GUARD_INJECTION_BLOCK", "true").lower() == "true"
_MAX_LENGTH        = int(os.getenv("INPUT_MAX_LENGTH", "2000"))


class GuardAction(Enum):
    ALLOW   = "allow"    # 정상 통과
    MASKED  = "masked"   # PII 마스킹 후 허용
    BLOCKED = "blocked"  # 차단


@dataclass
class GuardResult:
    action:       GuardAction
    sanitized:    str                     # 처리된 입력 (마스킹 적용 시 원본과 다름)
    reasons:      list[str] = field(default_factory=list)  # 탐지 이유 목록
    pii_detected: list[str] = field(default_factory=list)  # 탐지된 PII 유형 목록
    injection_detected: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 프롬프트 인젝션 패턴
# ═══════════════════════════════════════════════════════════════════════════════

# 영문 인젝션 패턴 (대소문자 무시)
_INJECTION_PATTERNS_EN: list[tuple[str, str]] = [
    # 역할 덮어쓰기
    (r"ignore\s+(all\s+)?(previous|above|prior)\s+(instruction|context|prompt|system)",
     "역할 덮어쓰기 시도 (ignore previous)"),
    (r"(you\s+are\s+now|act\s+as|pretend\s+(you\s+are|to\s+be))\s+",
     "역할극 전환 시도 (act as)"),
    (r"(new|updated|revised|actual)\s+(instruction|prompt|system\s+prompt|rule|directive)",
     "시스템 프롬프트 교체 시도"),
    (r"(forget|disregard|override|bypass|circumvent)\s+(your|the|all)\s+(instruction|rule|guideline|constraint|restriction)",
     "지시 무시 시도"),
    (r"(do\s+not\s+follow|stop\s+following)\s+(your|the)\s+(instruction|rule|system)",
     "지시 거부 유도"),
    # 탈출 토큰
    (r"<\|?(system|user|assistant|end|im_start|im_end|endoftext)\|?>",
     "모델 특수 토큰 삽입 시도"),
    (r"\[INST\]|\[/?SYS\]|<<SYS>>|###\s*(Human|Assistant|System)\s*:",
     "채팅 포맷 토큰 삽입 시도"),
    # DAN / Jailbreak
    (r"\b(DAN|jailbreak|developer\s+mode|god\s+mode|unlimited\s+mode)\b",
     "잘 알려진 탈옥 키워드"),
    (r"(reveal|show|print|output|display)\s+(your|the)\s+(system\s+)?prompt",
     "시스템 프롬프트 추출 시도"),
    (r"what\s+(is|are|was)\s+your\s+(instruction|prompt|system\s+message)",
     "시스템 프롬프트 질의"),
]

# 한글 인젝션 패턴
_INJECTION_PATTERNS_KO: list[tuple[str, str]] = [
    (r"(이전|위의|기존|앞서|앞의)\s*(지시|명령|프롬프트|설정|내용|규칙)\s*(무시|잊어|삭제|제거|초기화)",
     "이전 지시 무시 시도"),
    # '무시하고 너는/당신은 이제' 패턴 (공백·구두점 허용)
    (r"무시.{0,10}(너는|당신은|ai는|챗봇은).{0,20}(이다|입니다|야|이야|로\s*행동|이(라고|라는))",
     "역할 재정의 시도 (무시+역할)"),
    (r"(지금부터|이제부터|앞으로)\s*(너는|당신은|AI는|챗봇은)\s+.{1,30}\s*(이다|입니다|야|이야|로\s*행동)",
     "역할 재정의 시도"),
    (r"(시스템\s*프롬프트|system\s*prompt|시스템\s*메시지)\s*(알려줘|보여줘|출력해|알려주세요|보여주세요)",
     "시스템 프롬프트 추출 시도"),
    (r"(개발자\s*모드|관리자\s*모드|슈퍼유저|루트\s*권한)\s*(활성화|켜|on|enable)",
     "특수 모드 활성화 시도"),
    (r"(규칙|제약|필터|안전장치)\s*(없이|무시|우회|해제|비활성)",
     "보안 제약 우회 시도"),
    (r"(롤플레이|역할극)\s*[:：]\s*.{1,50}\s*(로서|로|으로서|이(라고|라는|야|야!|야\.))",
     "역할극을 통한 우회 시도"),
    (r"(위|상단|앞|이전)\s*(프롬프트|지시|내용)\s*(무시|잊어|초기화)",
     "프롬프트 초기화 시도"),
]

_COMPILED_INJECTION = [
    (re.compile(p, re.IGNORECASE | re.DOTALL), desc)
    for p, desc in (_INJECTION_PATTERNS_EN + _INJECTION_PATTERNS_KO)
]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 개인 민감정보(PII) 패턴 및 마스킹
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class _PiiRule:
    name:        str          # 표시명
    pattern:     re.Pattern   # 탐지 정규식
    mask:        str          # 마스킹 대체 문자열 (예: "[주민번호 삭제]")
    severity:    str          # "high" | "medium" | "low"


_PII_RULES: list[_PiiRule] = [
    _PiiRule(
        name="주민등록번호",
        pattern=re.compile(
            r"(?<![0-9])([0-9]{6})[^0-9A-Za-z]?([0-9]{7})(?![0-9])"
        ),
        mask="[주민번호 삭제]",
        severity="high",
    ),
    _PiiRule(
        name="외국인등록번호",
        pattern=re.compile(
            r"(?<![0-9])([0-9]{6})[^0-9A-Za-z]?([5-8][0-9]{6})(?![0-9])"
        ),
        mask="[외국인등록번호 삭제]",
        severity="high",
    ),
    _PiiRule(
        name="여권번호",
        pattern=re.compile(
            r"\b[MmSs][0-9]{8}\b"          # 한국 여권: M + 8자리
        ),
        mask="[여권번호 삭제]",
        severity="high",
    ),
    _PiiRule(
        name="운전면허번호",
        pattern=re.compile(
            r"(?<![0-9])[0-9]{2}[^0-9A-Za-z]?[0-9]{2}[^0-9A-Za-z]?[0-9]{6}[^0-9A-Za-z]?[0-9]{2}(?![0-9])"
        ),
        mask="[운전면허번호 삭제]",
        severity="high",
    ),
    _PiiRule(
        name="신용/체크카드번호",
        pattern=re.compile(
            r"(?<![0-9])(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|"
            r"6(?:011|5[0-9]{2})[0-9]{12}|"
            r"[0-9]{4}[^0-9A-Za-z]?[0-9]{4}[^0-9A-Za-z]?[0-9]{4}[^0-9A-Za-z]?[0-9]{4})(?![0-9])"
        ),
        mask="[카드번호 삭제]",
        severity="high",
    ),
    _PiiRule(
        name="계좌번호",
        pattern=re.compile(
            r"(?<![0-9])[0-9]{3,4}[^0-9A-Za-z]?[0-9]{4,6}[^0-9A-Za-z]?[0-9]{2,7}(?![0-9])(?=\s*(계좌|통장|입금|이체|account))"
        ),
        mask="[계좌번호 삭제]",
        severity="high",
    ),
    _PiiRule(
        name="전화번호",
        pattern=re.compile(
            r"(?<![0-9])(02|01[016789]|0[3-9][0-9])[^0-9A-Za-z]?[0-9]{3,4}[^0-9A-Za-z]?[0-9]{4}(?![0-9])"
        ),
        mask="[전화번호 삭제]",
        severity="medium",
    ),
    _PiiRule(
        name="이메일주소",
        pattern=re.compile(
            r"(?<![a-zA-Z0-9._%+-])[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}(?![a-zA-Z])"
        ),
        mask="[이메일 삭제]",
        severity="medium",
    ),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 메인 가드 함수
# ═══════════════════════════════════════════════════════════════════════════════

def check_and_sanitize(question: str) -> GuardResult:
    """
    입력 문자열을 검사하고 필요시 마스킹/차단합니다.

    Args:
        question: 사용자 입력 원문

    Returns:
        GuardResult — action(ALLOW/MASKED/BLOCKED), sanitized(정화된 텍스트), 탐지 목록
    """
    if not _ENABLED:
        return GuardResult(action=GuardAction.ALLOW, sanitized=question)

    # ── 전처리: 2바이트 전각 문자 → 반각 정규화 (우회 방지) ──────────────────
    # 예) ９００１０１－１２３４５６７ → 900101-1234567
    # 정규화된 텍스트로 탐지하되, 출력(sanitized)도 정규화본 사용
    question = _normalize_input(question)

    result = GuardResult(action=GuardAction.ALLOW, sanitized=question)

    # ── 0. 길이 검사 (정규화 후 기준) ────────────────────────────────────────
    if len(question) > _MAX_LENGTH:
        result.action = GuardAction.BLOCKED
        result.reasons.append(f"입력 길이 초과 ({len(question)} > {_MAX_LENGTH}자)")
        logger.warning("[InputGuard] 입력 길이 초과 차단: %d자", len(question))
        return result

    # ── 1. 프롬프트 인젝션 탐지 ──────────────────────────────────────────────
    for compiled, desc in _COMPILED_INJECTION:
        if compiled.search(question):
            result.injection_detected = True
            result.reasons.append(f"인젝션 패턴: {desc}")
            logger.warning("[InputGuard] 프롬프트 인젝션 탐지: %s", desc)

    if result.injection_detected:
        if _INJECTION_BLOCK:
            result.action = GuardAction.BLOCKED
            return result
        # 비차단 모드: 경고만 기록하고 통과 (로그 기반 모니터링)

    # ── 2. PII 탐지 및 마스킹 ────────────────────────────────────────────────
    sanitized = result.sanitized
    pii_found_high = False

    for rule in _PII_RULES:
        if rule.pattern.search(sanitized):
            result.pii_detected.append(rule.name)
            result.reasons.append(f"개인정보 탐지: {rule.name}")
            logger.warning("[InputGuard] PII 탐지 (%s, severity=%s)", rule.name, rule.severity)
            if rule.severity == "high":
                pii_found_high = True
            # 마스킹: 항상 수행 (차단 모드에서는 이후 차단)
            sanitized = rule.pattern.sub(rule.mask, sanitized)

    result.sanitized = sanitized

    if result.pii_detected:
        if _PII_BLOCK and pii_found_high:
            result.action = GuardAction.BLOCKED
            result.reasons.append("고위험 개인정보(주민번호/카드번호 등) 입력 차단")
            return result
        else:
            # 마스킹 후 허용
            result.action = GuardAction.MASKED

    return result


def get_block_message(result: GuardResult) -> str:
    """차단 시 사용자에게 반환할 안전한 한국어 메시지"""
    if result.injection_detected:
        return (
            "입력하신 내용에 시스템 명령어로 해석될 수 있는 패턴이 포함되어 있어 "
            "처리할 수 없습니다. 일반적인 법률 질문을 입력해 주세요."
        )
    if result.pii_detected:
        types_str = ", ".join(result.pii_detected)
        return (
            f"입력하신 내용에 개인정보({types_str})가 포함되어 있습니다. "
            "개인정보를 제거하고 다시 질문해 주세요. "
            "본 시스템은 개인정보를 수집·저장하지 않습니다."
        )
    if any("초과" in r for r in result.reasons):
        return f"질문이 너무 깁니다. {_MAX_LENGTH}자 이내로 입력해 주세요."
    return "입력 내용을 처리할 수 없습니다. 다시 시도해 주세요."
