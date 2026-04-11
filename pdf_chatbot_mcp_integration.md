# [V2 PRO] NuriNamuAiChat ↔ Korean-Law MCP 엔터프라이즈 연동 가이드

기존에 구축해두신 **FastAPI + LangChain + Qwen/ExaOne** 환경에 `korean-law-mcp`를 부착하기 위한 **고도화된 프로덕션용(Enterprise) 아키텍처 가이드**입니다.
이 가이드는 로컬 14B 모델의 컨텍스트 한계(환각 현상)를 극복하고, 다중 사용자 환경에서 발생할 수 있는 스케일링 병목을 방어하기 위해 설계되었습니다.

---

## 🌟 1. 시스템 아키텍처 (마이크로서비스 & 의도 기반 라우팅)

비효율적인 '자식 프로세스(stdio)' 및 '단일 Agent 무한 루핑' 구조를 버리고, 빠르고 안전한 **마이크로서비스 통신(SSE)** 과 **라우팅 구조**를 채택합니다.

```mermaid
graph TD
    User([사용자 질의]) --> FastAPI
    
    subgraph FastAPI_Backend[FastAPI 백엔드 (Python)]
        Router[의도 분류 라우터 (Semantic Router)]
        
        Router --> |내부 문서 질의 판단| RAG_Chain[독립 RAG Chain (Tool X)]
        Router --> |공공 법령 질의 판단| Law_Agent[법제처 Tool Calling Agent]
        Router --> |복합 질의 판단| Hybrid_Chain[병렬 검색 종합 (RAG + Tool)]
    end
    
    subgraph Node_MCP[korean-law-mcp 단독 서비스]
        Law_Agent <==> |HTTP/SSE 네트워크 통신| Node_Server[Node.js 데몬/컨테이너]
    end
    
    Node_Server -.-> |API 호출| OpenLaw[국가법령정보센터]
    RAG_Chain -.-> |Vector 매칭| PGVector[(PGVector)]
```

### 아키텍처 핵심 변경점:
1. **Decoupled MCP**: Node.js 서버는 Python이 띄우지 않습니다. 독립된 컨테이너나 PM2 데몬으로 실행되며, FastAPI와는 `SSE(Server-Sent Events)` 또는 HTTP 기반으로 통신합니다. (FastAPI 워커가 10개로 늘어나도 Node는 스케일 아웃 불이익을 받지 않음)
2. **Intent Routing**: 질문이 들어올 때마다 한 모델 안에서 "RAG 할까? Tool 쓸까?" 헤매지 않습니다. 가벼운 속도의 라우터 모델이 질문 의도를 먼저 `INTERNAL`, `EXTERNAL`, `BOTH`로 분류하여 가벼운 체인으로 분기합니다.

---

## 🛡️ 2. Python - 방어형 MCP 클라이언트 (에러 셧다운 방지)

기존 파이프 연동 대신 **SSE 클라이언트**를 사용하거나, 불가피하게 stdio를 유지하더라도 **타임아웃(Timeout)과 토큰 자르기(Truncation)** 안전망을 반드시 추가해야 합니다.

### `utils/law_mcp_client.py` 방어적 구현본 (stdio 유지 시 예제)

```python
import asyncio
from typing import List
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.tools import StructuredTool, ToolException

# 보안: 환경변수 사용 필수 (하드코딩 금지)
import os
LAW_API_KEY = os.getenv("LAW_OC_API_KEY", "your_fallback_key")

class LawMCPManager:
    def __init__(self, node_script_path: str):
        self.server_params = StdioServerParameters(
            command="node",
            args=[node_script_path],
            env={"LAW_OC": LAW_API_KEY}
        )
        self._session = None
        self._exit_stack = None

    async def connect(self):
        self._exit_stack = AsyncExitStack()
        read, write = await self._exit_stack.enter_async_context(stdio_client(self.server_params))
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()

    async def disconnect(self):
        if self._exit_stack:
            await self._exit_stack.aclose()

    async def get_langchain_tools(self) -> List[StructuredTool]:
        mcp_tools = await self._session.list_tools()
        lc_tools = []
        
        for tool in mcp_tools.tools:
            async def run_mcp_tool(tool_name=tool.name, **kwargs) -> str:
                try:
                    # [핵심 방어 1] 타임아웃 서킷 브레이커 (10초 이상 API 지연시 블로킹 방지)
                    result = await asyncio.wait_for(
                        self._session.call_tool(tool_name, arguments=kwargs),
                        timeout=12.0
                    )
                    
                    if result.isError:
                        return "법제처 API 내부 오류가 발생했습니다. (LLM: 다른 방법으로 안내할 것)"
                        
                    raw_text = "\n".join(c.text for c in result.content if c.type == "text")
                    
                    # [핵심 방어 2] 14B 모델 컨텍스트 오버플로우 / 환각 방어 (Token Truncation)
                    # 법령 원문 전체를 넣으면 모델이 망가집니다. 강제 커팅 후 재검색 유도.
                    MAX_CHARS = 2500
                    if len(raw_text) > MAX_CHARS:
                        return raw_text[:MAX_CHARS] + "\n\n... (텍스트가 너무 길어 일부 생략됨. 구체적인 조항[예: 제3조]을 명시하여 다시 도구를 호출하세요.)"
                        
                    return raw_text

                except asyncio.TimeoutError:
                    return "법제처 API 응답 지연 (Timeout). 사용량 폭주 또는 공공데이터 포털 점검 중일 수 있습니다."
                except Exception as e:
                    return f"도구 실행 일시 오류. (원인: {str(e)[:50]})"

            lc_tools.append(StructuredTool.from_function(
                coroutine=run_mcp_tool,
                name=tool.name,
                description=tool.description,
            ))
        return lc_tools

mcp_manager = LawMCPManager(node_script_path="C:/korean-law-mcp-main/build/index.js")
```

---

## 🚀 3. FastAPI 의도 기반 분기 라우터 (LangChain Router)

가장 빈번하게 환각(Hallucination)이 발생하는 "RAG 검색"과 "법령 검색"을 완벽하게 분리하는 LCEL 기반 라우팅 아키텍처입니다.

```python
from fastapi import FastAPI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableBranch, RunnablePassthrough
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_openai import ChatOpenAI

# 1. 모델 설정 (라우터용 가벼운 모델 / 본 작업용 14B 모델)
router_llm = ChatOpenAI(model="qwen2.5:7b-instruct", base_url="http://localhost:11434/v1", api_key="ollama")
main_llm = ChatOpenAI(model="qwen2.5:14b", base_url="http://localhost:11434/v1", api_key="ollama")

# 2. 의도 분류 라우터 체인 (매우 빠르고 토큰 소모가 적음)
router_template = """
사용자 질문을 분석하여 다음 세 가지 중 하나의 범주만 단어로 반환하세요:
1. INTERNAL: 사내 지침, 회사 규정, 연차, 사내 시스템 관련
2. EXTERNAL: 도로교통법, 민법, 정부 공공 법령 정보 관련
3. BOTH: 사내 규정과 법령 정보의 비교 또는 둘 다 포함된 경우

질문: {question}
범주 (INTERNAL/EXTERNAL/BOTH):"""

router_prompt = ChatPromptTemplate.from_template(router_template)
intent_router = router_prompt | router_llm | StrOutputParser()

# ==========================================================
# 분기 1: 내부 규정 전용 RAG 체인 (Tool 안 씀. 빠르고 할루시네이션 없음)
def create_internal_chain():
    prompt = ChatPromptTemplate.from_template("""사내 규정을 기반으로 답변하세요.\n규정: {context}\n지시: {question}""")
    return prompt | main_llm | StrOutputParser()

# 분기 2: 외부 법령 전용 에이전트 (RAG Context 오염 없음)
async def external_law_agent(inputs: dict):
    tools = await mcp_manager.get_langchain_tools()
    prompt = ChatPromptTemplate.from_messages([
        ("system", "당신은 법률 검색기능을 가진 도구 사용 에이전트입니다. 반드시 도구를 사용해야 합니다."),
        ("human", "{question}"),
        ("placeholder", "{agent_scratchpad}")
    ])
    agent = create_tool_calling_agent(main_llm, tools, prompt)
    # [핵심 방어 3] max_iterations으로 무한 루핑(에이전트 폭주) 마비 방지
    executor = AgentExecutor(agent=agent, tools=tools, max_iterations=3, verbose=True) 
    result = await executor.ainvoke({"question": inputs["question"]})
    return result["output"]
# ==========================================================

# 4. 종합 라우팅 체인 결합
def route_to_chain(inputs: dict):
    intent = inputs["intent"].strip().upper()
    if "INTERNAL" in intent:
        return create_internal_chain()
    elif "EXTERNAL" in intent:
        return external_law_agent
    else:  # BOTH (가장 복잡한 하이브리드)
        return external_law_agent # BOTH일 경우 일단 Agent에게 넘겨 통합 판단

master_chain = (
    {"question": RunnablePassthrough()}
    | RunnablePassthrough.assign(intent=intent_router)  # 1차 판단
    | RunnableBranch(
        (lambda x: "INTERNAL" in x["intent"].upper(), route_to_chain),
        (lambda x: "EXTERNAL" in x["intent"].upper(), route_to_chain),
        route_to_chain # Default fallback
    )
)

app = FastAPI()

@app.post("/api/v1/chat")
async def chat_endpoint(user_query: str):
    # Context 구성 (RAG 검색 로직은 생략/기존 코드 활용)
    # RAG 검색은 intent가 INTERNAL/BOTH 일때만 효율적으로 수행하는 로직 추가 권장
    response = await master_chain.ainvoke(user_query)
    return {"response": response}
```

## 🎯 도입 시 가장 크게 달라지는 점
1. **서버다운 방지**: 법제처 API가 마비되거나 트래픽이 몰려도 `asyncio.wait_for`로 12초 내 강제 커팅 -> 정상 에러 안내
2. **환각 최소화**: 2500자 이상 법령이 내려와도 강제로 잘라 Qwen 컨텍스트 초과 막음("중간 정보 유실" 방지) 
3. **비용/속도 최적화**: 단순히 사내 식권 규정을 묻는데 무거운 Agent 체인이 법제처 도구를 뒤적거리는 사고 완벽 차단.
