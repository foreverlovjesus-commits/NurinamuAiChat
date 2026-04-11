import asyncio
import json
import logging
import os
import time
import re
from datetime import datetime
from dotenv import load_dotenv

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import usage_tracker

logger = logging.getLogger(__name__)

def _extract_law_names(text: str) -> list:
    """텍스트에서 법령명(OO법, OO시행령 등)을 정규식으로 유추하여 추출"""
    laws = set()
    matches1 = re.findall(r'([가-힣]+(?:법|법률|시행령|시행규칙|\s*조례))\s*제\s*\d+\s*조', text)
    matches2 = re.findall(r'\[([가-힣\s]+(?:법|법률|시행령|시행규칙|\s*조례))\]', text)
    matches3 = re.findall(r'【([가-힣\s]+(?:법|법률|시행령|시행규칙|\s*조례))】', text)
    
    stop_words = {"방법", "불법", "위법", "적법", "편법", "이분법", "해결법"}
    
    for m in matches1 + matches2 + matches3:
        clean_name = m.strip()
        if len(clean_name) >= 2 and not any(clean_name.endswith(sw) for sw in stop_words):
            laws.add(clean_name)
    return list(laws)

class RAGEngineV3:

    def __init__(self, retriever):
        self.retriever = retriever
        self.db_url = retriever.db_url
        self.max_history_turns = 3

    def _get_llm(self, llm_type: str, is_router: bool = False):
        from dotenv import dotenv_values
        env_dict = dotenv_values(".env")
        
        llm_type = llm_type.lower()
        if llm_type == "openai":
            from langchain_openai import ChatOpenAI
            main_model  = env_dict.get("OPENAI_MAIN_MODEL",   "gpt-4o")
            router_model = env_dict.get("OPENAI_ROUTER_MODEL", "gpt-4o-mini")
            model_name = router_model if is_router else main_model
            return ChatOpenAI(model=model_name, temperature=0, streaming=not is_router)
        elif llm_type == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            main_model = env_dict.get("GEMINI_MODEL", "gemini-2.5-flash")
            router_model = env_dict.get("GEMINI_ROUTER_MODEL", "gemini-3.1-flash-lite-preview")
            model_name = router_model if is_router else main_model
            return ChatGoogleGenerativeAI(model=model_name, temperature=0)
        elif llm_type == "anthropic":
            from langchain_anthropic import ChatAnthropic
            model_name = env_dict.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
            return ChatAnthropic(model=model_name, temperature=0)
        else:
            from langchain_ollama import ChatOllama
            main_model = env_dict.get("MAIN_LLM_MODEL", "qwen2.5:14b")
            router_model = env_dict.get("ROUTER_LLM_MODEL", "exaone3.5:2.4b")
            model_name = router_model if is_router else main_model
            ollama_url = env_dict.get("OLLAMA_BASE_URL", "http://localhost:11434")
            return ChatOllama(model=model_name, temperature=0, base_url=ollama_url)

    async def classify_category(self, question: str, router_llm) -> dict:
        from pydantic import BaseModel, Field
        from langchain_core.output_parsers import JsonOutputParser

        class RouteDecision(BaseModel):
            route_type: str = Field(description="['rag', 'law', 'hybrid'] 중 하나")
            category: str = Field(description="청탁금지법, 이해충돌방지법, 공익신고자보호법, 행정심판법, 공무원행동강령, 공공재정환수법, 법령검색, 일반 Q&A 중 하나")
            reason: str = Field(description="분류 판단 근거")
            summary_5w1h: str = Field(description="육하원칙 요약")
            search_keyword: list[str] = Field(description="검색용 핵심 키워드 3~5개 리스트")
            
        parser = JsonOutputParser(pydantic_object=RouteDecision)

        messages = [
            SystemMessage(content=(
                "당신은 공공기관 민원/질문 분석 전문가입니다. 사용자의 질문을 분석하여 다음 기준에 맞춰 확정적인 JSON 형식으로 분류하세요.\n"
                "절대 마크다운 기호 없이 순수한 JSON만 반환해야 합니다.\n\n"
                f"{parser.get_format_instructions()}\n\n"
                "[세부 카테고리 분류 기준]\n"
                "   - 청탁금지법: 금품수수, 부정청탁, 외부강의·사례금(강의료), 선물·음식물·명절·경조사비 한도, 직무관련자(교사, 학부모 등 포함), 김영란법, 청탁금지법 위반 여부\n"
                "   - 이해충돌방지법: 사적이해관계 신고·회피, 직무관련자 거래 제한, 가족 채용, 퇴직공직자 관련\n"
                "   - 공익신고자보호법: 공익신고, 내부고발, 신고자 보호·면책, 신원 보호, 포상금\n"
                "   - 행정심판법: 행정심판 청구, 재결, 집행정지, 심판위원회, 청구기간(90일 등)\n"
                "   - 공무원행동강령: 향응·금품 수수, 공무원 행동기준, 민원인으로부터 향응\n"
                "   - 공공재정환수법: 보조금·지원금 부정수급, 공공재정환수\n"
                "   - 법령검색: 특정 법률 조항·시행령 원문 질의\n"
                "   - 일반 Q&A: 위 어디에도 속하지 않는 단순 문의\n\n"
                "[특별 주의사항]\n"
                "스승의 날 선물, 학교 담임 교사, 대학교 교수, 재학생 학부모 관련 질의는 모두 명백한 '청탁금지법' 적용 대상입니다."
            )),
            HumanMessage(content=question),
        ]

        try:
            # 🚀 범용 파서(JsonOutputParser) 사용: Langchain 버전이나 로컬/상용 LLM 종류를 타지 않고 가장 완벽하게 JSON을 추출
            timeout_sec = int(os.getenv("LLM_TIMEOUT", "1200"))
            res = await asyncio.wait_for(router_llm.ainvoke(messages), timeout=timeout_sec)
            
            result = parser.invoke(res)
            
            # 검색어가 리스트 형식이므로 조인해둠 (이후 플로우와 호환)
            if isinstance(result.get("search_keyword"), list):
                result["search_keyword"] = " ".join(result["search_keyword"])
            result["_category_source"] = "llm_json_parser"
            
            logger.info(f"[Structured Router] LLM JSON 파싱 완료: {result.get('category')} (근거: {result.get('reason')})")
        except Exception as e:
            logger.warning(f"Structured Routing failed: {e}. Fallback to default.")
            result = {
                "route_type": "rag", 
                "category": "일반 Q&A", 
                "reason": str(e),
                "summary_5w1h": "",
                "search_keyword": question,
                "_category_source": "fallback"
            }

        return result

    async def condense_question(self, question: str, history: list, router_llm) -> str:
        if not history: return question
        history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
        prompt = [
            SystemMessage(content="지시대명사나 생략된 맥락을 포함한 완전한 검색용 문장으로 재구성하세요."),
            HumanMessage(content=f"[이전 대화]\n{history_text}\n\n[최신 질문]\n{question}")
        ]
        try:
            res = await asyncio.wait_for(router_llm.ainvoke(prompt), timeout=15)
            return res.content.strip()
        except: return question

    async def check_eligibility(self, db_query: str, question: str, router_llm) -> tuple[bool, str]:
        def_query = db_query + " 법적용대상 정의 목적 공직자등"
        try:
            def_docs = await self.retriever.retrieve(def_query, final_k=2)
            def_context = "\n".join([doc.page_content[:1000] for doc in def_docs])
            messages = [
                SystemMessage(content="답변은 '적격', '부적격', '판단불가' 중 하나로 시작하고 이유를 작성하세요."),
                HumanMessage(content=f"[정의 문서]\n{def_context}\n\n[질문]\n{question}")
            ]
            res = await asyncio.wait_for(router_llm.ainvoke(messages), timeout=15)
            ans = res.content.strip()
            return (not ans.startswith("부적격"), ans)
        except: return True, "판단불가"

    async def generate_stream(self, question: str, session_id: str = None, db_manager=None, include_sources: list[str] = None):
        t_generate_start = time.time()
        from dotenv import dotenv_values
        import os
        _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        env_dict = dotenv_values(_env_path)
        mode = env_dict.get("GLOBAL_SEARCH_MODE", "auto").strip("'\"")
        llm_type = env_dict.get("GLOBAL_LLM_PROVIDER", "local").strip("'\"")
        hide_judgment = env_dict.get("HIDE_DETAILED_JUDGMENT", "false").strip("'\"").lower() == "true"
        enable_firac = env_dict.get("ENABLE_FIRAC_MODE", "false").strip("'\"").lower() == "true"
        
        # FIRAC 세부 스타일 로드
        f_style = env_dict.get("FIRAC_FORMAT_STYLE", "concise").strip("'\"").lower()
        f_logic = env_dict.get("FIRAC_LOGIC_STRUCTURE", "front").strip("'\"").lower()
        f_type  = env_dict.get("FIRAC_TEMPLATE_TYPE", "basic").strip("'\"").lower()

        if not question or not question.strip():
            yield f"data: {json.dumps({'type': 'error', 'content': '질문을 입력해 주세요.'})}\n\n"; return

        history = []
        if db_manager and session_id:
            # 🚀 In-memory 딕셔너리 누수를 방지하기 위해 DB에서 직접 대화 이력을 로드 (최대 6개)
            history = await db_manager.get_history(session_id, limit=6)
            await db_manager.save_message(session_id, "user", question)

        t_route_start = time.time()
        router_llm = self._get_llm(llm_type, is_router=True)
        search_query = await self.condense_question(question, history, router_llm)
        db_query = search_query
        
        # Route logic
        route_type, category, reason, summary_5w1h = "rag", "일반 Q&A", "", ""
        if mode != "auto":
            route_type = mode
        else:
            route_info = await self.classify_category(search_query, router_llm)
            route_type = route_info.get("route_type", "rag").lower()
            category = route_info.get("category", "일반 Q&A")
            summary_5w1h = route_info.get("summary_5w1h", "")
            reason = route_info.get("reason", "")
            
            t_route_end = time.time()
            if not include_sources:
                yield f"data: {json.dumps({'type': 'chunk', 'content': f'\n💡 [질의 분류 체계 가동 완료: {t_route_end - t_route_start:.1f}초 경과]\n'}, ensure_ascii=False)}\n\n"
            
            # search_keyword가 리스트로 반환되는 경우(예: ["키워드1", "키워드2"]) 문자열로 조인하여 오류 방지
            raw_kwd = route_info.get("search_keyword", search_query)
            if isinstance(raw_kwd, list):
                db_query = " ".join(str(k) for k in raw_kwd)
            else:
                db_query = str(raw_kwd)
                
        # 쿼리 메타데이터 추출 (활성화된 경우, 단 노트북 모드일 때는 최소화)
        query_metadata = {}
        if include_sources:
            query_metadata = {"source": include_sources}
        elif env_dict.get("ENABLE_METADATA_TAGGING", "true").lower() == "true":
            t_tag_start = time.time()
            try:
                from indexer.metadata_tagger import MetadataTagger
                tagger = MetadataTagger(router_llm)
                query_metadata = await tagger.tag_query(search_query)
                if query_metadata:
                    logger.info(f"쿼리 메타데이터 추출: {query_metadata}")
                    # 메타데이터 태거의 강력한 분류 결과를 UI 카테고리에 강제 보정 적용
                    if "law_category" in query_metadata and query_metadata["law_category"] not in ("기타", "해당없음"):
                        if category == "일반 Q&A":
                            category = query_metadata["law_category"]
                            reason = f"메타데이터 분석기(Tagger)에 의해 '{category}' 관련 질의로 명확히 분류됨."
                t_tag_end = time.time()
                yield f"data: {json.dumps({'type': 'chunk', 'content': f'💡 [메타데이터 필터 태깅 완료: {t_tag_end - t_tag_start:.1f}초 경과]\n'}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.warning(f"쿼리 메타데이터 추출 실패 (무시): {e}")

        # 보정된 카테고리를 프론트엔드로 전송
        yield f"data: {json.dumps({'type': 'category', 'content': category, 'reason': reason, 'summary_5w1h': summary_5w1h}, ensure_ascii=False)}\n\n"
        # FIRAC 모드 활성화 시에는 메타데이터 태그를 별도로 전송하지 않음 (FIRAC 구조 내에 포함되거나 불필요하다고 가정)
        if query_metadata and not enable_firac:
            yield f"data: {json.dumps({'type': 'metadata_tags', 'content': query_metadata}, ensure_ascii=False)}\n\n"

        # Eligibility check
        try:
            is_elig_enabled = env_dict.get("ENABLE_ELIGIBILITY_CHECK", "false").lower() == "true" and not include_sources
            if is_elig_enabled:
                t_elig_start = time.time()
                is_eligible, eligibility_reason = await self.check_eligibility(db_query, search_query, router_llm)
                if not is_eligible:
                    yield f"data: {json.dumps({'type': 'chunk', 'content': f'부적격 차단: {eligibility_reason}'}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'response_time_ms': 0})}\n\n"; return
                t_elig_end = time.time()
                yield f"data: {json.dumps({'type': 'chunk', 'content': f'💡 [대상자 적격성 심사 통과: {t_elig_end - t_elig_start:.1f}초 경과]\n'}, ensure_ascii=False)}\n\n"

            context_text, sources = "", []

            # 🚀 Retrieval 단계: MCP 실시간 연동 로직 모두 제거, Vector DB(PGVector)에 100% 의존
            if route_type == "pure_llm":
                rag_docs = []
                yield f"data: {json.dumps({'type': 'chunk', 'content': f'💡 [순수 지식 검색 모드 작동 (RAG 우회)]\n\n'}, ensure_ascii=False)}\n\n"
            else:
                t_ret_start = time.time()
                rag_docs = await self.retriever.retrieve(db_query, final_k=3, metadata_filter=query_metadata)
                context_text = "\n".join([d.page_content for d in rag_docs])
                sources = [d.metadata.get('source', '문서') for d in rag_docs]

                sources = list(set(sources))
                t_ret_end = time.time()
                yield f"data: {json.dumps({'type': 'docs', 'sources': sources}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'chunk', 'content': f'💡 [하이브리드 문서 검색 병합 완료: {t_ret_end - t_ret_start:.1f}초 경과]\n'}, ensure_ascii=False)}\n\n"

                # 사용자에게 가중치 랭킹 결과를 시각적으로 보여주기 위한 요약본 스트리밍
                ranking_text = "💡 [참고 문서 최종 랭킹 순위 (가중치 반영)]\n"
                for idx, d in enumerate(rag_docs):
                    src = d.metadata.get('source', '알 수 없는 문서')
                    dt = d.metadata.get('doc_type', 'general')
                    f_score = d.metadata.get('final_score', 0.0)
                    ranking_text += f"> {idx+1}위: [{dt}] {src} (Score: {f_score})\n"
                
                yield f"data: {json.dumps({'type': 'chunk', 'content': f'{ranking_text}\n━━━━━━━━━━━━━━━━━━━━\n\n'}, ensure_ascii=False)}\n\n"

            # ── 참고 데이터에 출처 헤더를 붙여 LLM이 어느 법 조문인지 알 수 있도록 가공 ──
            def _build_context_with_source(docs) -> str:
                """각 RAG 문서 앞에 출처 법령명을 헤더로 붙여 반환."""
                parts = []
                for i, doc in enumerate(docs, 1):
                    src = doc.metadata.get("source", "")
                    law = doc.metadata.get("law_name",
                           doc.metadata.get("law_category",
                           doc.metadata.get("act_type", src or "출처 미상")))
                    article = doc.metadata.get("article", "")
                    header  = f"[출처 {i}: {law}{' ' + article if article else ''}]"
                    parts.append(f"{header}\n{doc.page_content.strip()}")
                return "\n\n".join(parts)

            # Prompt & Generate
            # 환경변수로 관리자가 시스템 프롬프트를 덮어쓸 수 있도록 지원
            from dotenv import dotenv_values as _dv
            _env_live = _dv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
            _custom_prompt = _env_live.get("SYSTEM_PROMPT_OVERRIDE", "").replace("\\n", "\n").strip()

            if _custom_prompt:
                sys_instructions = _custom_prompt
            else:
                sys_instructions = (
                    "당신은 공공기관 최고의 법률 비서입니다. 답변 시 '~에 따르면', '제공된 문서에 의하면'과 같은 표현은 절대 쓰지 마세요.\n"
                    "법적 판단은 단호하고 명확하게 작성하세요.\n\n"
                    "━━━ 【법령 인용 필수 규칙】 ━━━\n"
                    "법적 근거를 제시할 때는 반드시 다음 3가지를 모두 포함하세요:\n"
                    "  1) 법령 이름  예) 청탁금지법, 이해충돌방지법, 공익신고자보호법, 행정심판법\n"
                    "  2) 조문 번호  예) 제10조 제1항, 시행령 별표1\n"
                    "  3) 해당 조문의 핵심 내용 요약 (1~2문장)\n\n"
                    "인용 형식 예시:\n"
                    "  ▸ [법령명] 제O조 제O항: [조문이 규정하는 객관적 사실 및 요약].\n"
                    "  ▸ [법령명] 시행령 별표O: [구체적 기준이나 상한액 요약].\n\n"
                    "❌ 금지: '제8조에 따르면' 처럼 법령명 없이 조문 번호만 언급하는 방식\n"
                    "✅ 필수: 법령명 + 조문 번호 + 해당 조문이 실제로 규정하는 내용\n"
                    "근거 조문이 [참고 데이터]에 없다면 '관련 조문을 확인할 수 없어 정확한 내용 확인이 필요합니다'라고 명시하세요.\n\n"
                    "━━━ 【직무관련자 판단 필수 주의사항】 ━━━\n"
                    "청탁금지법에서 '직무관련자'를 판단할 때 반드시 아래 기준을 따르세요:\n\n"
                    "✅ 직무관련자 = 공직자등의 직무 수행과 직접 이해관계가 있는 자\n"
                    "   예) 재학생의 학부모 → 교사(교직원)의 직무관련자 ← 청탁금지법 적용\n"
                    "   예) 허가·계약 신청인 → 담당 공무원의 직무관련자 ← 청탁금지법 적용\n\n"
                    "❌ 절대 금지되는 잘못된 추론:\n"
                    "   '학부모는 학생이 아니므로 외부인 → 청탁금지법 적용 대상 아님' ← 틀림\n"
                    "   '일반 시민이므로 외부인 → 적용 대상 아님' ← 틀림\n\n"
                    "올바른 판단 순서:\n"
                    "  1단계: 금품을 받는 사람이 공직자등인가? (교직원, 공무원, 사립학교 교원 등)\n"
                    "  2단계: 금품을 주는 사람이 그 직무와 관련된 이해관계에 있는가?\n"
                    "  → 두 조건 모두 충족 시 청탁금지법 제8조 적용\n\n"
                    "사립유치원·사립학교 교직원은 청탁금지법 제2조 제2호에 따라 공직자등에 해당합니다.\n"
                    "재학생 학부모는 교직원의 직무(교육·평가·생활지도)와 이해관계가 있어 직무관련자입니다.\n\n"
                    "━━━ 【절대 엄수: 직무관련성과 예외조항 배제 원칙 (일반화)】 ━━━\n"
                    "청탁금지법 제8조 제3항의 예외사유(원활한 직무수행 등 목적 하에 3·5·10 가액 한도 내 허용)는 "
                    "**제공자와 공직자 간에 '직접적인 이해관계(인·허가, 인사·지도·평가, 단속·감사, 수사·재판, 계약 등 밀접한 직무관련성)'가 성립하는 경우에는 그 목적(사교·의례 등)이 원천적으로 부정**됩니다.\n"
                    "따라서, 검색된 문서([참고 데이터])나 사실관계를 통해 대상자들이 **'밀접한 직무관련자(직접적 이해관계)'**로 확인되는 경우, "
                    "**가액 한도(5만원 이하 등)와 무관하게 예외 조항 적용을 전면 배제하고 '직무관련성이 밀접하여 원활한 직무수행 목적이 인정되지 않으므로 수수 금지(법 위반)'로 판단**하십시오."
                )
            if enable_firac:
                # ── FIRAC 스타일 조립 엔진 ──
                style_guide = ""
                if f_style == "concise":
                    style_guide = "최대한 짧고 간결한 문장을 사용하며, 불필요한 수식어를 배제하고 핵심 위주로 개조식(Bullet points)을 적극 활용하십시오."
                elif f_style == "narrative":
                    style_guide = "부드럽고 자연스러운 서술형 문장(~습니다)을 사용하여 정황을 친절하게 설명하는 산문식 스타일로 작성하십시오."
                elif f_style == "prolix":
                    style_guide = "논리적 인과관계를 매우 상세히 설명하고, 모든 예외 조건과 변수를 마침표 하나에 길게 담아내는 고전적인 만연체 스타일로 작성하십시오."

                template_guide = ""
                if f_type == "statutory":
                    template_guide = "특히 '규정' 섹션에서는 법률 조문 고유의 계층 구조(제O조 ➔ 제O항 ➔ 제O호 ➔ O목)를 엄격히 준수하여 인용하십시오."
                elif f_type == "judicial":
                    template_guide = "전체 구조를 판결문 형식인 [주문](결론)과 [이유](사실관계 및 법리 분석)로 명확히 분리하여 작성하십시오."
                
                logic_pos = "최상단(1단계 이전)" if f_logic == "front" else "최하단(5단계)"

                sys_instructions += f"\n\n[FIRAC 지능형 문서 설계 지침]\n"
                sys_instructions += f"1. 문체: {style_guide}\n"
                sys_instructions += f"2. 논리 배치: 가장 중요한 '최종 결론'을 반드시 전체 답변의 **{logic_pos}**에 배치하십시오.\n"
                if template_guide:
                    sys_instructions += f"3. 특수 양식: {template_guide}\n"

                sys_instructions += """
반드시 아래의 **FIRAC** 5단계를 거쳐 논리적으로 추론하되, 관리자가 지정한 위의 스타일 가이드를 최우선으로 적용하십시오.
화면에서 논리 전개 과정을 접고 펼칠 수 있도록, 1~4단계(사실-쟁점-규정-포섭)는 반드시 HTML `<details>`와 `<summary>` 태그를 사용하여 작성하십시오.
⚠️ 중요: 절대로 ````html` 이나 ````` 같은 마크다운 코드 블록으로 태그를 감싸지 말고, 일반 텍스트(Raw Text)처럼 바로 HTML 태그를 출력하십시오.
⚠️ 중요: `<summary>` 태그 다음 줄에는 반드시 **빈 줄(Empty Line)**을 넣어야 마크다운 글줄이 깨지지 않고 정상 출력됩니다!

[출력 구조 예시]
"""
                if f_logic == "front":
                    sys_instructions += "### ⚡ [최종 결론 및 요약] (두괄식 배치)\n(여기에 결론을 먼저 작성)\n\n"
                
                sys_instructions += """
<details>
<summary><strong>1. Facts (사실관계)</strong></summary>

질문에 포함된 모든 객관적 사실관계를 체계적으로 정리 (반드시 윗줄 띄움)

</details>

<details>
<summary><strong>2. Issues (법적 쟁점)</strong></summary>

해결해야 할 법적 쟁점을 의문문 형태로 명확히 정의 (반드시 윗줄 띄움)

</details>

<details>
<summary><strong>3. Rules (관련 규정)</strong></summary>

[참고 데이터]의 관련 조문을 정확히 인용 (반드시 윗줄 띄움)

</details>

<details>
<summary><strong>4. Application (사안의 포섭)</strong></summary>

규정을 사실관계에 대입하여 위반 여부를 상세히 분석 (반드시 윗줄 띄움)

</details>
"""
                if f_logic != "front":
                    sys_instructions += "\n### 5. Conclusion (최종 결론 및 면책조항)\n\n위 1~4단계 분석을 종합한 최종 판단 결과를 필수로 제시 (여기에 결론 작성)\n"
                
                if f_type == "judicial":
                    sys_instructions = sys_instructions.replace(" 사실관계", " [이유] 사실관계")
                    sys_instructions = sys_instructions.replace(" 결론", " [주문] 결론")
            elif hide_judgment:
                sys_instructions += (
                    "\n\n[특별 지시사항] 관리자 모드가 활성화되었습니다. 불필요한 서술이나 부연 설명을 일절 생략하고 오직 아래의 형식으로만 답변하세요:\n"
                    f"1. 5W1H 분석 요약: {summary_5w1h}\n"
                    "2. 관련 법규 및 근거 조문 원문"
                )

            if route_type == "pure_llm":
                sys_instructions += "\n\n[순수 지식 엔진 모드 최우선 규칙] 현재 RAG 참고 데이터가 시스템적으로 차단되어 제공되지 않습니다. '참고 데이터가 없다'는 회피성 기재를 절대 하지 말고, 반드시 당신의 거대한 내부 학습 지식을 총동원하여 규정과 조문을 찾아 완벽한 답변을 작성하십시오."

            prompt = [SystemMessage(content=sys_instructions)]
            for msg in history:
                role_msg = HumanMessage(content=msg["content"]) if msg["role"] == "user" else AIMessage(content=msg["content"])
                prompt.append(role_msg)

            # 🚀 출처 헤더 포함 컨텍스트 조립 - 항상 DB(rag_docs) 기반으로 조립
            final_context = _build_context_with_source(rag_docs) if rag_docs else context_text

            final_prompt = f"[참고 데이터 — 각 항목의 [출처 N: 법령명] 을 인용에 반드시 활용하세요]\n{final_context}\n\n질문: {question}"
            prompt.append(HumanMessage(content=final_prompt))

            full_answer, t_llm_start = "", time.time()
            main_llm = self._get_llm(llm_type, is_router=False)
            main_model_name = getattr(main_llm, 'model_name', getattr(main_llm, 'model', 'unknown'))

            async for ch in main_llm.astream(prompt):
                if ch.content:
                    full_answer += ch.content
                    yield f"data: {json.dumps({'type': 'chunk', 'content': ch.content}, ensure_ascii=False)}\n\n"

            latency_ms = int((time.time() - t_llm_start) * 1000)
            usage_tracker.record_usage(
                provider=llm_type, model=main_model_name, call_type="main",
                input_tokens=len(final_prompt), output_tokens=len(full_answer),
                latency_ms=latency_ms, session_id=session_id
            )
        except Exception as e:
            logger.error(f"파이프라인 실행 중 에러 발생: {e}")
            import traceback
            traceback.print_exc()
            yield f"data: {json.dumps({'type': 'error', 'content': f'내부 시스템 에러가 발생했습니다: {str(e)}'}, ensure_ascii=False)}\n\n"
            full_answer = f"에러 발생: {str(e)}"

        total_latency = int((time.time() - t_generate_start) * 1000)
        if db_manager and session_id:
            await db_manager.save_message(session_id, "assistant", full_answer, sources=sources, latency_ms=total_latency)

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'response_time_ms': total_latency}, ensure_ascii=False)}\n\n"
