"""
메타데이터 태거 모듈 — 범용 스키마 기반 LLM 자동 태깅

인덱싱 시: 각 청크에서 구조화된 메타데이터 태그를 추출하여 cmetadata에 저장
검색 시:  사용자 질문에서 메타데이터를 추출하여 필터 검색에 활용
"""
import json
import re
import logging
import asyncio
import os

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# ── 범용 태그 스키마 ──────────────────────────────────────────
# 모든 권익위 소관 법률에 공통 적용 가능한 상위 태그
DOMAIN_TAGS_SCHEMA = {
    "law_category": {
        "description": "관련 법률 분류",
        "enum": [
            "청탁금지법", "이해충돌방지법", "공익신고자보호법",
            "공공재정환수법", "부패방지법", "행정심판법",
            "공무원행동강령", "기타"
        ],
    },
    "subject_type": {
        "description": "적용 대상자 유형",
        "enum": [
            "공무원", "교사", "언론인", "공직유관단체임직원",
            "공무수행사인", "신고자", "민원인", "일반인", "해당없음"
        ],
    },
    "counterpart_type": {
        "description": "상대방 유형",
        "enum": [
            "학부모", "민원인", "이해관계자", "직무관련자",
            "피신고자", "일반인", "해당없음"
        ],
    },
    "act_type": {
        "description": "행위 유형",
        "enum": [
            "금품수수", "부정청탁", "이해충돌", "공익신고",
            "부정청구", "외부강의", "부패행위신고", "행정심판청구",
            "사적이해관계신고", "직무관련자거래", "기타", "해당없음"
        ],
    },
    "provision_type": {
        "description": "조항 성격",
        "enum": [
            "정의", "의무", "금지", "예외허용", "벌칙",
            "신고절차", "보호조치", "환수", "기타"
        ],
    },
    "exception_flag": {
        "description": "예외/허용 조항 포함 여부",
        "enum": ["예", "아니오"],
    },
}

# 태그 키 화이트리스트 (SQL 인젝션 방지용)
VALID_TAG_KEYS = frozenset(DOMAIN_TAGS_SCHEMA.keys())


def _build_schema_description() -> str:
    """프롬프트용 스키마 설명 문자열 생성"""
    lines = []
    for key, spec in DOMAIN_TAGS_SCHEMA.items():
        enum_str = " | ".join(spec["enum"])
        lines.append(f'- {key} ({spec["description"]}): {enum_str}')
    return "\n".join(lines)


_SCHEMA_DESC = _build_schema_description()

_SYSTEM_PROMPT_CHUNK = (
    "당신은 대한민국 공공기관 법률 문서의 메타데이터 분류 전문가입니다.\n"
    "주어진 텍스트를 분석하여 아래 스키마에 따라 JSON 객체를 출력하세요.\n\n"
    "각 필드의 값은 반드시 제시된 선택지 중 하나여야 합니다.\n"
    "판단이 불확실하면 '해당없음' 또는 '기타'를 사용하세요.\n"
    "JSON 외의 어떤 텍스트도 출력하지 마세요.\n\n"
    f"스키마:\n{_SCHEMA_DESC}"
)

_SYSTEM_PROMPT_QUERY = (
    "당신은 대한민국 공공기관 법률 질문 분석 전문가입니다.\n"
    "사용자 질문에서 아래 스키마 중 확실한 태그만 추출하여 JSON으로 출력하세요.\n"
    "확실하지 않은 태그는 포함하지 마세요. '해당없음'도 포함하지 마세요.\n"
    "JSON 외의 어떤 텍스트도 출력하지 마세요.\n\n"
    f"스키마:\n{_SCHEMA_DESC}"
)


def _parse_json_response(text: str) -> dict:
    """LLM 응답에서 JSON을 안전하게 추출"""
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, dict) and 'text' in item:
                parts.append(item['text'])
            else:
                parts.append(str(item))
        text = " ".join(parts)
    elif not isinstance(text, str):
        text = str(text)
    text = text.strip()
    # 1) 직접 파싱
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 2) 마크다운 코드 펜스 안의 JSON 추출
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # 3) 첫 번째 { ... } 블록 추출
    match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _validate_tags(tags: dict) -> dict:
    """유효한 태그만 필터링"""
    valid = {}
    for key, value in tags.items():
        if key not in VALID_TAG_KEYS:
            continue
        allowed = DOMAIN_TAGS_SCHEMA[key]["enum"]
        if value in allowed:
            valid[key] = value
    return valid


def _compute_confidence(llm_tags: dict, rule_tags: dict) -> float:
    """LLM 태그와 Rule-based 태그의 일치율로 신뢰도(0.0~1.0)를 계산합니다.

    - LLM이 생성한 의미 있는 태그 수가 많을수록 신뢰도 상승
    - 핵심 필드(law_category, act_type)가 포함되면 가산점
    - LLM과 Rule-based 결과가 일치하는 항목이 많으면 가산점
    """
    if not llm_tags:
        return 0.0  # LLM 완전 실패

    # 핵심 필드 포함 여부
    core_fields = {"law_category", "act_type"}
    core_score  = sum(1 for f in core_fields if f in llm_tags) / len(core_fields)  # 0~1

    # 전체 태그 수 기반 (최대 6개 필드)
    tag_count_score = min(len(llm_tags) / 3, 1.0)  # 3개 이상이면 만점

    # LLM ↔ Rule-based 일치 보너스
    common_keys = set(llm_tags) & set(rule_tags)
    if common_keys:
        agree = sum(1 for k in common_keys if llm_tags[k] == rule_tags[k])
        agree_score = agree / len(common_keys)
    else:
        agree_score = 0.5  # 비교 불가 시 중립

    confidence = (core_score * 0.5) + (tag_count_score * 0.3) + (agree_score * 0.2)
    return round(min(confidence, 1.0), 3)


def _rule_based_fallback(query: str, tags: dict) -> dict:
    """LLM 태그를 규칙 기반으로 보완/교정. 오탐 방지를 위해 복합 조건 사용."""
    q = query

    # --- 법률 분류 ---
    if tags.get("law_category") not in ("청탁금지법", "이해충돌방지법", "공익신고자보호법",
                                         "공공재정환수법", "부패방지법", "행정심판법", "공무원행동강령"):
        if any(k in q for k in ["청탁금지", "김영란법"]):
            tags["law_category"] = "청탁금지법"
        elif any(k in q for k in ["이해충돌", "이해충돌방지"]):
            tags["law_category"] = "이해충돌방지법"
        elif any(k in q for k in ["공익신고", "내부고발"]):
            tags["law_category"] = "공익신고자보호법"
        elif any(k in q for k in ["행정심판", "재결"]):
            tags["law_category"] = "행정심판법"
        elif ("사례금" in q or "외부강의" in q) and ("공직" in q or "공무원" in q):
            tags["law_category"] = "청탁금지법"
        elif ("선물" in q or "금품" in q) and ("공직" in q or "공무원" in q):
            tags["law_category"] = "청탁금지법"

    # --- 행위 유형 (법률 분류 확정 후에만) ---
    if tags.get("law_category") == "청탁금지법" and tags.get("act_type") not in (
            "금품수수", "부정청탁", "외부강의"):
        if any(k in q for k in ["외부강의", "강연", "사례금", "강의료"]):
            tags["act_type"] = "외부강의"
        elif any(k in q for k in ["선물", "금품", "경조사", "식사"]):
            tags["act_type"] = "금품수수"
        elif any(k in q for k in ["부정청탁", "알선", "청탁"]):
            tags["act_type"] = "부정청탁"

    # --- 대상자 유형 ---
    if tags.get("subject_type") not in ("공무원", "교사", "언론인", "공직유관단체임직원"):
        if any(k in q for k in ["공무원", "공직자"]):
            tags["subject_type"] = "공무원"
        elif any(k in q for k in ["교사", "교직원", "교수", "선생님"]):
            tags["subject_type"] = "교사"

    return tags


class MetadataTagger:
    """LLM 기반 메타데이터 태거"""

    def __init__(self, llm_client):
        """
        Args:
            llm_client: LangChain 호환 채팅 모델 (ChatOllama, ChatOpenAI, etc.)
        """
        self.llm = llm_client

    def tag_chunk_sync(self, chunk_text: str) -> dict:
        """인덱싱용 동기 태깅. 실패 시 빈 dict 반환."""
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT_CHUNK),
            HumanMessage(content=f"다음 문서 청크를 분석하세요:\n---\n{chunk_text[:2000]}\n---"),
        ]
        try:
            res = self.llm.invoke(messages)
            tags = _parse_json_response(res.content)
            return _validate_tags(tags)
        except Exception as e:
            logger.warning(f"태깅 실패 (건너뜀): {e}")
            return {}

    async def _tag_one_async(self, chunk_text: str, sem: asyncio.Semaphore, delay: float = 0) -> dict:
        """세마포어로 동시성을 제한하며 단일 청크를 비동기 태깅 (지수 백오프 재시도)."""
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT_CHUNK),
            HumanMessage(content=f"다음 문서 청크를 분석하세요:\n---\n{chunk_text[:2000]}\n---"),
        ]
        max_retries = 3
        async with sem:
            for attempt in range(max_retries):
                try:
                    res = await asyncio.wait_for(self.llm.ainvoke(messages), timeout=120)
                    tags = _parse_json_response(res.content)
                    return _validate_tags(tags)
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "resource_exhausted" in err_str or "rate" in err_str:
                        wait = (2 ** attempt) * 2  # 2s, 4s, 8s
                        logger.info(f"Rate limit 감지, {wait}초 대기 후 재시도 ({attempt+1}/{max_retries})")
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(f"태깅 실패 (건너뜀): {e}")
                    return {}
            logger.warning("태깅 최대 재시도 초과 (건너뜀)")
            return {}

    async def tag_chunks_batch_async(self, chunk_texts: list[str], max_concurrency: int = 3, delay: float = 0) -> list[dict]:
        """여러 청크를 병렬로 태깅. max_concurrency로 동시 호출 수 제한, delay로 호출 간격 조절.

        Returns:
            입력 순서와 동일한 태그 dict 리스트
        """
        sem = asyncio.Semaphore(max_concurrency)
        results = [None] * len(chunk_texts)

        async def _tag_with_delay(idx, text):
            if delay > 0 and idx > 0:
                await asyncio.sleep(delay * (idx % max_concurrency))
            results[idx] = await self._tag_one_async(text, sem)

        # 배치 단위로 처리하여 고정 딜레이 적용
        batch_size = max_concurrency
        for batch_start in range(0, len(chunk_texts), batch_size):
            batch_end = min(batch_start + batch_size, len(chunk_texts))
            batch_tasks = [
                _tag_with_delay(i, chunk_texts[i]) for i in range(batch_start, batch_end)
            ]
            await asyncio.gather(*batch_tasks)
            if delay > 0:
                await asyncio.sleep(delay)

        return results

    async def tag_query(self, query: str) -> dict:
        """검색용 비동기 태깅. LLM 실패 또는 신뢰도 낮음 시 Rule-based 우선 적용.

        Returns:
            태그 dict. '_confidence' 키에 0.0~1.0 신뢰도 포함.
            '_source' 키에 'llm', 'llm+rule', 'rule' 중 실제 사용된 방식 기록.
        """
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT_QUERY),
            HumanMessage(content=f"다음 사용자 질문에서 관련 태그만 추출하세요:\n---\n{query}\n---"),
        ]

        # 1) LLM 태깅 시도 — 타임아웃 혜택 (로컬 렌더링 딜레이를 고려하여 600초 넉넉하게 대기)
        llm_tags: dict = {}
        llm_success = False
        timeout_sec = int(os.getenv("LLM_TIMEOUT", "1200"))
        try:
            res = await asyncio.wait_for(self.llm.ainvoke(messages), timeout=timeout_sec)
            llm_tags = _validate_tags(_parse_json_response(res.content))
            llm_success = True
        except asyncio.TimeoutError:
            logger.warning(f"쿼리 태깅 LLM 타임아웃 ({timeout_sec}초) — Rule-based 단독 적용")
        except Exception as e:
            logger.warning(f"쿼리 태깅 LLM 실패 (Rule-based로 계속): {e}")

        # 2) Rule-based fallback — 항상 독립 실행 (교정용 기준)
        rule_tags = _rule_based_fallback(query, {})

        # 3) 신뢰도 계산
        confidence = _compute_confidence(llm_tags, rule_tags) if llm_success else 0.0

        # 4) 신뢰도 임계값 (0.4 미만) 또는 핵심 필드 누락 시 Rule-based 결과 우선
        LOW_CONFIDENCE_THRESHOLD = float(os.getenv("TAGGING_CONFIDENCE_THRESHOLD", "0.4"))
        missing_core = "law_category" not in llm_tags and "act_type" not in llm_tags

        if not llm_success or confidence < LOW_CONFIDENCE_THRESHOLD or missing_core:
            # Rule-based 결과를 기반으로 LLM의 추가 태그를 선택적으로 병합
            merged = {**rule_tags}
            for k, v in llm_tags.items():
                if k not in merged:  # rule-based에 없는 보조 태그만 추가
                    merged[k] = v
            source = "rule" if not llm_success else "rule+llm"
            logger.info(
                f"태깅 전략: {source} (confidence={confidence:.2f}, missing_core={missing_core})"
            )
            final_tags = merged
        else:
            # LLM 결과를 기반으로 Rule-based의 보완 적용
            final_tags = _rule_based_fallback(query, llm_tags)
            source = "llm+rule"

        # 5) 무의미 태그 제거 후 메타 필드 추가
        result = {k: v for k, v in final_tags.items() if v not in ("해당없음", "기타")}
        result["_confidence"] = confidence
        result["_source"] = source
        return result
