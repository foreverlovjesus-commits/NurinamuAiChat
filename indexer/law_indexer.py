"""
Phase 2: MCP 법령 데이터를 RAG 지식 베이스에 인덱싱하는 배치 스크립트.

MCP 서버의 get_law_markdown 도구를 사용하여 법령 전문을 마크다운으로 가져와
PGVector에 저장합니다. 법령 검색 시 시행령·시행규칙의 MST도 함께 추출하여 인덱싱합니다.
"""

import os
import sys
import asyncio
import time
import re
import psycopg2
from dotenv import load_dotenv
from cryptography.fernet import Fernet

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from integrations.mcp_law_client import McpLawClient
from retriever.factory import get_retriever
from langchain_core.documents import Document

# 핵심 법령 목록 — JSON 파일에서 로드 (대시보드에서 관리)
TARGET_LAWS_PATH = os.path.join(BASE_DIR, "logs", "target_laws.json")

_DEFAULT_LAWS = [
    "부정청탁 및 금품등 수수의 금지에 관한 법률",
    "행정심판법",
    "국민권익위원회의 설치와 운영에 관한 법률",
    "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률",
    "공직자의 이해충돌 방지법",
    "민원 처리에 관한 법률",
    "행정절차법",
]

import json as _json

def load_target_laws() -> list[str]:
    """target_laws.json에서 법령 목록을 읽어온다. 파일이 없으면 기본 목록 반환."""
    if os.path.exists(TARGET_LAWS_PATH):
        try:
            with open(TARGET_LAWS_PATH, "r", encoding="utf-8") as f:
                laws = _json.load(f)
            if isinstance(laws, list) and laws:
                return laws
        except Exception:
            pass
    return _DEFAULT_LAWS

ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)


def get_db_url():
    try:
        cipher = Fernet(os.getenv("MASTER_KEY").encode())
        return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
    except Exception as e:
        print(f"❌ DB URL 복호화 실패: {e}")
        return None


def delete_existing_law(db_url: str, law_name: str) -> int:
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'law_name' = %s AND cmetadata->>'doc_type' = 'legal_api';",
                (law_name,),
            )
            return cur.rowcount
    except Exception as e:
        print(f"⚠️ 기존 '{law_name}' 데이터 삭제 실패: {e}")
        return 0


def _extract_msts(text: str) -> list[str]:
    """MCP 응답에서 MST(법령일련번호)를 모두 추출한다."""
    patterns = [
        r'[Mm][Ss][Tt][\s"\':=]+(\d{4,8})',
        r'lawId[\s"\':=]+(\d{4,8})',
        r'(?:법령)?일련번호[\s"\':=]+(\d{4,8})',
    ]
    found = []
    for pat in patterns:
        found.extend(re.findall(pat, text, re.IGNORECASE))
    return list(dict.fromkeys(found))


async def _search_main_mst(mcp_client: McpLawClient, law_name: str) -> str | None:
    """법령명으로 검색하여 본법의 MST를 반환한다."""
    for tool in ["search_law", "search_laws", "chain_full_research"]:
        res = await mcp_client.call_tool(tool, {"query": law_name})
        if not res or "[MCP" in res or "[결과 없음]" in res:
            continue
        msts = _extract_msts(res)
        if msts:
            print(f"  ✅ MST 발견: {msts[0]} (도구: {tool})")
            return msts[0]
        await asyncio.sleep(0.3)
    return None


async def _fetch_markdown(mcp_client: McpLawClient, mst: str) -> tuple[str, list[str]]:
    """get_law_markdown 도구로 법령 전문 마크다운을 가져온다.

    Returns:
        (마크다운 텍스트, 응답에서 발견된 관련 MST 목록)
    """
    res = await mcp_client.call_tool("get_law_markdown", {"mst": mst})
    if not res or "[MCP" in res or "[결과 없음]" in res or len(res.strip()) <= 50:
        return "", []

    # 응답에서 관련 MST 추출 (시행령·시행규칙 등)
    related = _extract_msts(res)
    # 자기 자신 제거
    related = [m for m in related if m != mst]
    return res, related


def _chunk_markdown(markdown_text: str) -> list[str]:
    """마크다운 법령 텍스트를 조(條) 단위로 분할한다."""
    # ## 제N조 또는 제N조의N 패턴으로 분할
    chunks = re.split(r'\n(?=##?\s*제\d+조)', markdown_text)
    if len(chunks) <= 1:
        # 마크다운 헤더 없는 경우 일반 조문 패턴으로 분할
        chunks = re.split(r'\n(?=제\d+조(?:의\d+)?\()', markdown_text)
    return [c.strip() for c in chunks if c.strip() and len(c.strip()) > 20]


async def _index_single_law(
    mcp_client: McpLawClient, mst: str, law_name: str
) -> tuple[list[Document], list[str]]:
    """하나의 MST에 대해 마크다운 → 청킹 → (Document 목록, 관련 MST 목록) 반환."""
    markdown, related_msts = await _fetch_markdown(mcp_client, mst)
    if not markdown:
        print(f"  ❌ {law_name}: 마크다운 전문을 가져오지 못했습니다.")
        return [], []

    print(f"  📚 마크다운 수집 완료 (길이: {len(markdown):,}자)")

    chunks = _chunk_markdown(markdown)
    print(f"  ✂️ {len(chunks)}개 청크 생성")

    docs = []
    for i, chunk in enumerate(chunks):
        docs.append(Document(
            page_content=chunk,
            metadata={
                "source": f"법제처({law_name})",
                "source_type": "법제처API",
                "doc_type": "legal_api",
                "law_name": law_name,
                "mst": mst,
                "chunk_index": i,
                "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            },
        ))
    return docs, related_msts


async def main():
    print("🚀 MCP 법령 마크다운 인덱서 가동")

    db_url = get_db_url()
    if not db_url:
        return

    mcp_url = os.getenv("MCP_SERVER_URL", "http://localhost:3000")
    mcp_client = McpLawClient(base_url=mcp_url)

    if not await mcp_client.is_healthy():
        print(f"⚠️ MCP 서버({mcp_url})에 연결할 수 없습니다.")
        return

    if not await mcp_client.initialize():
        print("⚠️ MCP 세션 초기화 실패")
        return

    retriever = get_retriever(db_url)
    vector_store = retriever.vectorstore

    all_docs = []
    successful_laws = []
    processed_msts = set()  # 중복 인덱싱 방지

    target_laws = load_target_laws()
    print(f"📋 대상 법령: {len(target_laws)}건")

    for law_name in target_laws:
        print(f"\n{'='*60}")
        print(f"📜 {law_name}")
        print(f"{'='*60}")

        # 1단계: 본법 MST 검색
        main_mst = await _search_main_mst(mcp_client, law_name)
        if not main_mst:
            print(f"  ❌ MST를 찾을 수 없습니다. 건너뜁니다.")
            continue

        if main_mst in processed_msts:
            print(f"  ⏭️ 이미 처리된 MST({main_mst}). 건너뜁니다.")
            continue

        # 2단계: 본법 마크다운 가져오기 + 관련 MST 추출
        print(f"\n  [본법] 🔎 {law_name} (MST: {main_mst})")
        docs, related_msts = await _index_single_law(mcp_client, main_mst, law_name)
        if docs:
            all_docs.extend(docs)
            successful_laws.append(law_name)
            processed_msts.add(main_mst)

        if related_msts:
            print(f"  📎 관련 법령 MST {len(related_msts)}건 발견: {related_msts}")

        # 3단계: 관련 MST(시행령·시행규칙 등) 순회 인덱싱
        for rel_mst in related_msts:
            if rel_mst in processed_msts:
                print(f"  ⏭️ 관련 MST {rel_mst} 이미 처리됨. 건너뜁니다.")
                continue

            rel_name = f"{law_name} 관련법령(MST:{rel_mst})"
            print(f"\n  [관련] 🔎 {rel_name}")
            rel_docs, _ = await _index_single_law(mcp_client, rel_mst, rel_name)
            if rel_docs:
                all_docs.extend(rel_docs)
                successful_laws.append(rel_name)
                processed_msts.add(rel_mst)
            await asyncio.sleep(0.5)

        await asyncio.sleep(1)

    # 4단계: Vector DB 저장
    if all_docs:
        print(f"\n💾 총 {len(all_docs)}개 문서를 DB에 저장합니다...")
        for law in successful_laws:
            deleted = delete_existing_law(db_url, law)
            if deleted > 0:
                print(f"  └─ 🗑️ 기존 '{law}' {deleted}개 삭제")

        await vector_store.aadd_documents(all_docs)
        print(f"\n✅ 완료! {len(successful_laws)}개 법령, {len(all_docs)}개 청크 적재")
        print(f"  📊 처리된 MST: {len(processed_msts)}건")
    else:
        print("🤷 추가할 법령 데이터가 없습니다.")

    await mcp_client.close()


if __name__ == "__main__":
    asyncio.run(main())
