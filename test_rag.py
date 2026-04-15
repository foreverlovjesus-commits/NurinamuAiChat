import asyncio
from rag.rag_engine import RAGEngineV3
from retriever.factory import get_retriever
from dotenv import load_dotenv
import os

load_dotenv(".env")
DB_URL = os.getenv("DATABASE_URL")

async def test():
    retriever = get_retriever(DB_URL)
    engine = RAGEngineV3(retriever)
    async for chunk in engine.generate_stream("안녕하세요"):
        print(chunk)

if __name__ == "__main__":
    asyncio.run(test())
