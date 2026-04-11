import os
import sys
import json

# 💡 현재 파일의 부모의 부모 디렉토리(프로젝트 루트)를 파이썬 경로에 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# 클라우드 특화 엔진 (Gemini/Claude 대응)
from langchain_google_genai import ChatGoogleGenerativeAI
from retriever.factory import get_retriever

# 설정 로드
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

try:
    cipher = Fernet(os.getenv("MASTER_KEY").encode())
    DB_URL = cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
except Exception as e:
    print(f"❌ 보안 복호화 에러: {e}")
    raise SystemExit(1)

# 🌟 클라우드 전용 엔진 클래스
class CloudRAGEngine:
    def __init__(self, retriever):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0.1,
            google_api_key=os.getenv("GOOGLE_API_KEY")
        )
        self.retriever = retriever

    async def generate_stream(self, question: str):
        # 1. 문서 검색 (로컬 Vector DB 사용)
        docs = await self.retriever.retrieve(question, final_k=5)
        context = "\n\n".join([f"[{d.metadata.get('source')}]\n{d.page_content}" for d in docs])

        # UI에 출처 먼저 전송
        sources = list(set([d.metadata.get('source', '문서') for d in docs]))
        yield f"data: {json.dumps({'type': 'docs', 'sources': sources}, ensure_ascii=False)}\n\n"

        # 2. 답변 생성 (Gemini API 호출)
        prompt = f"당신은 전문 가이드입니다. 다음 문서를 바탕으로 답하세요.\n\n[문서]\n{context}\n\n질문: {question}\n답변:"

        async for chunk in self.llm.astream(prompt):
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk.content}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

global_retriever = None
cloud_engine = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global global_retriever, cloud_engine
    global_retriever = get_retriever(DB_URL)
    cloud_engine = CloudRAGEngine(global_retriever)
    yield

app = FastAPI(title="Gemini Cloud RAG API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class UserRequest(BaseModel):
    question: str

@app.post("/ask")
async def ask_cloud(request: UserRequest):
    return StreamingResponse(cloud_engine.generate_stream(request.question), media_type="text-event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001) # 포트 8001번 사용
