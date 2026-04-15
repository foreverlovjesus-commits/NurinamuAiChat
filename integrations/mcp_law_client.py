"""
Korean Law MCP Server HTTP 클라이언트.

MCP Streamable HTTP 프로토콜(JSON-RPC 2.0)로 법제처 법령 도구를 호출한다.
세션 관리, 자동 재연결, 도구 선택 로직을 포함.
"""

import logging
import os
import re
import time

import httpx

logger = logging.getLogger(__name__)


class McpLawClient:
    """MCP HTTP 클라이언트 — 세션 기반 도구 호출."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or os.getenv("MCP_SERVER_URL", "")).rstrip("/")
        self.mcp_url = f"{self.base_url}/mcp"
        self.api_key = api_key or os.getenv("LAW_API_KEY", "")
        self.session_id: str | None = None
        self._request_id = 0
        self._client: httpx.AsyncClient | None = None
        self._available_tools: list[dict] = []

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self, *, include_session: bool = True) -> dict[str, str]:
        h: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        if include_session and self.session_id:
            h["mcp-session-id"] = self.session_id
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def initialize(self) -> bool:
        """MCP 세션을 초기화한다. 성공 시 True 반환."""
        client = await self._get_client()
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "nurinamu-ai-chat", "version": "1.0.0"},
            },
        }
        try:
            resp = await client.post(
                self.mcp_url,
                json=body,
                headers=self._headers(include_session=False),
            )
            resp.raise_for_status()
            self.session_id = resp.headers.get("mcp-session-id")

            # initialized 알림 전송 (MCP 스펙)
            if self.session_id:
                await client.post(
                    self.mcp_url,
                    json={
                        "jsonrpc": "2.0",
                        "method": "notifications/initialized",
                    },
                    headers=self._headers(),
                )
                # 사용 가능한 도구 목록 조회
                await self._fetch_tools()
            return bool(self.session_id)
        except Exception:
            self.session_id = None
            return False

    async def _fetch_tools(self) -> None:
        """MCP 서버에서 사용 가능한 도구 목록을 조회하여 캐시한다."""
        try:
            client = await self._get_client()
            resp = await client.post(
                self.mcp_url,
                json={
                    "jsonrpc": "2.0",
                    "id": self._next_id(),
                    "method": "tools/list",
                },
                headers=self._headers(),
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            tools = data.get("result", {}).get("tools", [])
            self._available_tools = [
                {"name": t["name"], "description": t.get("description", "")}
                for t in tools
            ]
        except Exception:
            self._available_tools = []

    @staticmethod
    def _timeout_for(tool_name: str) -> float:
        """도구 유형에 따른 타임아웃(초)을 반환한다."""
        if tool_name.startswith("chain_"):
            return 90.0
        if tool_name.startswith("search_"):
            return 30.0
        if tool_name == "get_law_markdown":
            return 60.0
        if tool_name.startswith("get_"):
            return 20.0
        return 60.0

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """MCP 도구를 호출하고 텍스트 결과를 반환한다.

        세션이 만료(404)된 경우 자동 재초기화 후 1회 재시도.
        도구 유형별 타임아웃: chain 90s / search 30s / get 20s / 기타 60s.
        """
        if not self.session_id:
            if not await self.initialize():
                return "[MCP 서버 연결 실패] 법령 검색을 수행할 수 없습니다."

        client = await self._get_client()
        timeout = httpx.Timeout(self._timeout_for(tool_name))
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }

        try:
            resp = await client.post(
                self.mcp_url, json=body, headers=self._headers(), timeout=timeout,
            )

            # 세션 만료 → 재초기화 후 재시도 (1회)
            if resp.status_code == 404:
                self.session_id = None
                if not await self.initialize():
                    return "[MCP 세션 재연결 실패]"
                body["id"] = self._next_id()
                resp = await client.post(
                    self.mcp_url, json=body, headers=self._headers(), timeout=timeout,
                )

            resp.raise_for_status()
            data = resp.json()

            # JSON-RPC 에러 처리
            if "error" in data:
                return f"[MCP 오류] {data['error'].get('message', '알 수 없는 오류')}"

            # 결과에서 텍스트 추출
            result = data.get("result", {})
            content_list = result.get("content", [])
            texts = [item["text"] for item in content_list if item.get("type") == "text"]
            return "\n".join(texts) if texts else "[결과 없음]"

        except httpx.TimeoutException:
            return f"[MCP 서버 응답 시간 초과] {tool_name} ({self._timeout_for(tool_name):.0f}초 제한)"
        except Exception as e:
            return f"[MCP 호출 오류] {e}"

    async def close(self):
        """세션 종료 및 리소스 정리."""
        if self._client and not self._client.is_closed:
            if self.session_id:
                try:
                    await self._client.delete(self.mcp_url, headers=self._headers())
                except Exception:
                    pass
            await self._client.aclose()
            self._client = None
        self.session_id = None

    async def is_healthy(self) -> bool:
        """MCP 서버 상태 확인."""
        try:
            client = await self._get_client()
            resp = await client.get(f"{self.base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False


# ── 키워드 스코어링 기반 도구 선택 ─────────────────────────────
# 우선순위(낮을수록 높음), 도구명, 트리거 키워드 목록
_TOOL_MAP: list[tuple[int, str, list[str]]] = [
    (1,  "search_precedents",              ["판례", "판결", "대법원", "선고"]),
    (2,  "search_constitutional_decisions", ["헌법재판소", "헌재", "위헌", "헌법소원"]),
    (3,  "search_admin_appeals",           ["행정심판", "재결", "행심"]),
    (4,  "search_ordinance",               ["조례", "자치법규"]),
    (5,  "search_admin_rule",              ["훈령", "예규", "고시", "지침", "행정규칙"]),
    (6,  "search_interpretations",         ["해석례", "유권해석", "질의회신"]),
    (7,  "chain_amendment_track",          ["개정", "신구대조", "연혁"]),
    (8,  "chain_law_system",              ["법체계", "3단비교", "위임"]),
    (9,  "chain_dispute_prep",            ["불복", "소송", "쟁송", "구제", "취소소송"]),
    (10, "chain_action_basis",            ["처분", "허가", "인가", "과태료"]),
    (11, "chain_procedure_detail",        ["절차", "수수료", "서식"]),
    (12, "chain_ordinance_compare",       ["조례비교", "전국조례"]),
    (13, "search_legal_terms",            ["법률용어", "용어정의"]),
    (14, "get_annexes",                   ["별표", "별지"]),
]


def select_tool(question: str) -> tuple[str, dict]:
    """사용자 질문을 키워드 스코어링으로 분석하여 최적 MCP 도구를 결정한다.

    각 도구의 키워드 출현 횟수를 세어 최고 점수 도구를 선택.
    동점 시 우선순위(낮은 번호)가 높은 도구를 선택한다.

    Returns:
        (tool_name, arguments) 튜플
    """
    q = question.strip()

    # 특수 패턴: 시행령+시행규칙 동시 언급 → 3단비교
    if re.search(r"시행령.*시행규칙|시행규칙.*시행령", q):
        return "chain_law_system", {"query": q}

    # 키워드 스코어링
    best_tool = "chain_full_research"
    best_score = 0
    best_priority = 999

    for priority, tool_name, keywords in _TOOL_MAP:
        score = sum(1 for kw in keywords if kw in q)
        if score > best_score or (score == best_score and score > 0 and priority < best_priority):
            best_score = score
            best_tool = tool_name
            best_priority = priority

    # get_annexes는 법령명이 필요 — 추출 시도
    if best_tool == "get_annexes":
        law_match = re.search(r"(.+?(?:법|령|규칙))", q)
        if law_match:
            return "get_annexes", {"lawName": law_match.group(1).strip()}

    return best_tool, {"query": q}
