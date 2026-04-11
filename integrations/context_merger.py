"""
Phase 3: RAG 검색 결과와 MCP 실시간 법령 결과를 병합하는 모듈.
"""

import logging
from typing import List
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

def merge_contexts(rag_docs: List[Document], mcp_text: str, question: str, max_tokens: int = 4000) -> str:
    """
    RAG 문서와 MCP 결과를 하나의 프롬프트 컨텍스트로 병합합니다.
    
    1. MCP 결과를 최우선으로 배치 ([법제처 실시간 법령] 라벨 적용)
    2. RAG 문서 중 MCP 결과와 중복되는 법령 조문은 필터링 (간단한 텍스트 포함 여부 검사)
    3. 나머지 RAG 문서를 [내부 문서] 라벨로 뒤에 배치
    4. 예상 토큰 길이를 고려하여 초과 시 강제 절삭
    """
    merged_text = ""
    
    # 1. MCP 결과 추가 (최우선 순위 - 공신력 확보)
    if mcp_text and not mcp_text.startswith("[MCP 실패]") and mcp_text != "[결과 없음]":
        mcp_section = f"==== [출처: 법제처 실시간 법령] ====\n{mcp_text.strip()}\n\n"
        merged_text += mcp_section
        
    # 2. RAG 문서 필터링 및 추가 (중복 제거)
    rag_section = ""
    added_sources = set()
    
    if rag_docs:
        for doc in rag_docs:
            content = doc.page_content.strip()
            source = doc.metadata.get("source", "알 수 없는 문서")
            
            # 중복 제거 휴리스틱: RAG 문서의 첫 30글자가 이미 MCP 결과 텍스트에 포함되어 있다면 스킵
            # (같은 법령의 동일 조문일 가능성이 매우 높음)
            if mcp_text and content[:30] in mcp_text:
                logger.debug("중복된 RAG 문서 스킵 (MCP에 이미 포함됨): %s", source)
                continue
                
            rag_section += f"==== [출처: 내부 문서({source})] ====\n{content}\n\n"
            added_sources.add(source)
            
        if rag_section:
            merged_text += rag_section

    # 3. 토큰 예산 관리 (단순 글자 수 기반 근사치 계산: 한국어 모델 기준 1토큰 ≈ 2~2.5글자)
    max_chars = int(max_tokens * 2.5)
    if len(merged_text) > max_chars:
        logger.warning("병합된 컨텍스트 길이 초과 (%d자). %d자로 강제 절삭합니다.", len(merged_text), max_chars)
        merged_text = merged_text[:max_chars] + "\n... (텍스트가 너무 길어 일부 생략됨)"
        
    return merged_text.strip()