import logging
import os
import sys
import json
import time
import uuid
# 💡 윈도우 한글 경로 인코딩 에러(asyncpg) 방지를 위한 전역 설정
os.environ["PYTHONUTF8"] = "1"
os.environ["PGPASSFILE"] = "NUL"
from fastapi import FastAPI, Depends, HTTPException, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# 💡 프로젝트 루트를 sys.path에 추가 (python server/api_server.py 직접 실행 시에도 모듈 탐색 가능)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# 💡 엔터프라이즈 추상화: Factory 패턴을 통해 리트리버를 동적으로 로드
from retriever.factory import get_retriever
from rag.rag_engine import RAGEngineV3
from integrations.mcp_law_client import McpLawClient
from server.db_manager import AsyncDBManager
from server.audit_logger import log_audit_event
from server.input_guard import check_and_sanitize, GuardAction, get_block_message

# 경로 설정 및 환경 변수 로드
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

# DB URL 복구 및 우선순위 결정 (Docker 환경 지원)
DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    try:
        master_key = os.getenv("MASTER_KEY")
        encrypted_url = os.getenv("ENCRYPTED_DATABASE_URL")
        if master_key and encrypted_url:
            cipher = Fernet(master_key.encode())
            DB_URL = cipher.decrypt(encrypted_url.encode()).decode()
            logger.info("🔑 보안 DB 연결 URL 복호화 완료")
        else:
            logger.warning("⚠️ DATABASE_URL 및 보안 환경 변수가 없습니다. 기본 로컬 DB를 시도합니다.")
            DB_URL = "postgresql://postgres:postgres@localhost:5432/nurinamu_db"
    except Exception as e:
        logger.critical("보안 복호화 에러: %s", e)
        # 운영 환경에서 DB 없이는 구동 불가
        if os.getenv("NODE_ENV") == "production":
            raise SystemExit(1)
        DB_URL = "postgresql://postgres:postgres@localhost:5432/nurinamu_db"

# --- 🚀 보안 및 속도 제한 설정 (조달청 납품 보안 강화) ---
RATE_LIMIT = os.getenv("RATE_LIMIT_PER_MINUTE", "30/minute")  # 기관별 조정 가능
limiter = Limiter(key_func=get_remote_address)

# ⚠️ API_KEY 환경변수가 반드시 설정되어야 합니다. 기본값 없음.
API_KEY_EXPECTED = os.getenv("API_KEY")
if not API_KEY_EXPECTED:
    logger.critical("❌ [보안] API_KEY 환경변수가 설정되지 않았습니다. 서비스를 시작할 수 없습니다.")
    if os.getenv("NODE_ENV") == "production":
        raise SystemExit(1)
    else:
        logger.warning("⚠️ 개발 환경에서만 임시 API Key를 허용합니다. 운영 배포 전 반드시 설정하세요.")
        API_KEY_EXPECTED = "dev-only-unsafe-key"

async def verify_api_key(x_api_key: str = Header(None)):
    """API Key 인증 미들웨어 대용 (Dependency Injection)"""
    if not x_api_key or x_api_key != API_KEY_EXPECTED:
        # 보안: 제공된 키 값은 로그에 남기지 않음 (유출 방지)
        logger.warning("🚫 [Auth] API Key 인증 실패 (IP 추적은 감사 로그 참조)")
        raise HTTPException(status_code=403, detail="인증에 실패하였습니다. 올바른 API Key를 제공해주세요.")
    return x_api_key

# 전역 객체 선언
global_retriever = None
rag_engine = None
mcp_client = None
db_manager = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global global_retriever, rag_engine, mcp_client, db_manager
    logger.info("서버 리소스 초기화 중...")

    db_manager = AsyncDBManager(DB_URL)
    await db_manager.connect()

    # 💡 팩토리 패턴 적용: 설정에 따라 PGVector 또는 Ensemble(OpenSearch)을 자동으로 선택
    global_retriever = get_retriever(DB_URL)

    # 🚀 성능 최적화: 유저 API 요청 단계에서는 실시간 MCP 법령 검색을 제거하고 Vector DB만 사용
    # MCP를 통한 법령 적재는 indexer/law_scheduler.py(배치 모듈)가 전담합니다.
    mcp_client = None

    rag_engine = RAGEngineV3(global_retriever)

    logger.info("서버 기반 엔진 초기화 완료")

    logger.info("서버 준비 완료")
    yield
    # 종료 시 리소스 정리
    if mcp_client:
        await mcp_client.close()
    if global_retriever:
        del global_retriever
    if db_manager:
        await db_manager.close()

app = FastAPI(title="GovOps Enterprise Hybrid RAG API (V3)", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS 설정 — 조달청 보안 요건: 화이트리스트 필수, 와일드카드 금지
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "")
if not allowed_origins_raw or allowed_origins_raw.strip() == "*":
    if os.getenv("NODE_ENV") == "production":
        logger.critical("❌ [보안] ALLOWED_ORIGINS 환경변수를 반드시 지정해야 합니다. 와일드카드(*) 사용 불가.")
        raise SystemExit(1)
    else:
        # 개발환경에서만 허용
        allowed_origins = ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000"]
        logger.warning("⚠️ 개발 환경 CORS: localhost만 허용합니다. 운영 시 ALLOWED_ORIGINS를 설정하세요.")
else:
    allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]
    logger.info("✅ [보안] CORS 허용 도메인: %s", allowed_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

@app.get("/health")
async def health_check():
    """L4 로드밸런서 및 CI/CD 헬스체크 엔드포인트"""
    return {
        "status": "ok",
        "llm": os.getenv("MAIN_LLM_MODEL", "unknown"),
        "retriever": os.getenv("RETRIEVER_TYPE", "unknown"),
        "mcp_law": "batch_only_mode",
        "mcp_tools_count": 0,
    }

@app.get("/sessions/{session_id}/history")
async def get_session_history(session_id: str, api_key: str = Depends(verify_api_key)):
    """특정 세션의 대화 이력을 조회합니다."""
    global db_manager
    history = await db_manager.get_history(session_id)
    return {"session_id": session_id, "messages": history}

class FeedbackRequest(BaseModel):
    session_id: str
    message_index: int
    rating: int  # 1~5
    comment: Optional[str] = None

@app.post("/feedback")
async def post_feedback(fb: FeedbackRequest, api_key: str = Depends(verify_api_key)):
    """특정 메시지에 대한 피드백을 기록합니다."""
    global db_manager
    success = await db_manager.save_feedback(fb.session_id, fb.message_index, fb.rating, fb.comment)
    if not success:
        raise HTTPException(status_code=404, detail="Message not found in session")
    return {"status": "ok"}

@app.get("/sessions")
async def get_all_sessions(limit: int = 20, api_key: str = Depends(verify_api_key)):
    """최근 세션 목록을 조회합니다."""
    global db_manager
    sessions = await db_manager.get_all_sessions(limit)
    return {"sessions": sessions}

@app.get("/usage/session/{session_id}")
async def get_session_usage(session_id: str, api_key: str = Depends(verify_api_key)):
    """특정 세션의 누적 사용량 및 비용을 조회합니다."""
    import usage_tracker
    stats = usage_tracker.get_session_stats(session_id)
    return stats

class UserRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

@app.post("/ask")
@limiter.limit(RATE_LIMIT)
async def ask_endpoint(request: Request, user_req: UserRequest, api_key: str = Depends(verify_api_key)):
    """
    사용자의 질문을 받아 V3 엔진을 통해 스트리밍 답변을 반환합니다.
    (API Key 인증, RATE_LIMIT_PER_MINUTE 환경변수 기반 Rate Limit, 감사 로그 기록)
    """
    global global_retriever, rag_engine, db_manager
    question = user_req.question
    session_id = user_req.session_id or str(uuid.uuid4())
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    user_ip = request.client.host if request.client else "unknown"
    start_time = time.time()

    # 💡 핫 리로드(Hot-Reload): 임베딩 모델 변경 감지 시 백그라운드 무중단 교체
    from dotenv import dotenv_values
    env_dict = dotenv_values(ENV_PATH)
    env_embed = env_dict.get("GLOBAL_EMBEDDING_MODEL", "BAAI/bge-m3")

    if hasattr(global_retriever, 'active_embedding_model_name'):
        if global_retriever.active_embedding_model_name != env_embed:
            logger.warning("🔄 [핫 리로드] 임베딩 모델 변경 감지 (%s -> %s). 검색 엔진을 동적 교체합니다...", global_retriever.active_embedding_model_name, env_embed)
            try:
                new_retriever = get_retriever(DB_URL)
                global_retriever = new_retriever
                rag_engine.retriever = new_retriever
                logger.info("✅ 챗봇 검색 엔진 핫 리로드 완료!")
            except Exception as e:
                logger.error("❌ 핫 리로드 실패: %s", e)

    async def event_generator():
        success = False
        error_code = None
        try:
            # ── 입력 보안 검사 (프롬프트 인젝션 / PII) ──────────────────────
            guard = check_and_sanitize(question)

            if guard.action == GuardAction.BLOCKED:
                block_msg = get_block_message(guard)
                yield f"data: {json.dumps({'type': 'error', 'content': block_msg}, ensure_ascii=False)}\n\n"
                logger.warning(
                    "[InputGuard] 요청 차단 | request_id=%s reasons=%s",
                    request_id, guard.reasons
                )
                error_code = "INPUT_BLOCKED"
                return

            # 마스킹 적용 시 정화된 텍스트로 RAG 진행
            safe_question = guard.sanitized
            if guard.action == GuardAction.MASKED:
                logger.info(
                    "[InputGuard] PII 마스킹 후 진행 | pii=%s request_id=%s",
                    guard.pii_detected, request_id
                )

            async for chunk in rag_engine.generate_stream(safe_question, session_id, db_manager=db_manager):
                yield chunk
            success = True
        except Exception:
            logger.exception("스트리밍 응답 생성 중 오류")
            error_code = "STREAM_ERROR"
            yield f"data: {json.dumps({'type': 'error', 'content': '요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.'}, ensure_ascii=False)}\n\n"
        finally:
            # 감사 로그 기록 (조달청 납품 요건)
            elapsed_ms = int((time.time() - start_time) * 1000)
            import asyncio
            asyncio.ensure_future(
                log_audit_event(
                    db_manager=db_manager,
                    session_id=session_id,
                    user_ip=user_ip,
                    question=question,
                    request_id=request_id,
                    response_time_ms=elapsed_ms,
                    success=success,
                    error_code=error_code,
                )
            )

    response = StreamingResponse(event_generator(), media_type="text-event-stream")
    response.headers["X-Request-ID"] = request_id
    return response

# 정적 파일 서빙 (HTML+JS UI) — API 라우트 등록 후 마지막에 마운트
STATIC_DIR = os.path.join(BASE_DIR, "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # 💡 다른 스크립트 및 문서와 포트 번호를 8000으로 통일합니다.
    uvicorn.run(app, host="0.0.0.0", port=8000)
