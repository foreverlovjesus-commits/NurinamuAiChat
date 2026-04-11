import os, asyncio
from dotenv import load_dotenv
from cryptography.fernet import Fernet
from retriever.factory import get_retriever

load_dotenv()

async def check_similarity(query, target_source):
    # DB URL 복호화
    cipher = Fernet(os.getenv('MASTER_KEY').encode())
    db_url = cipher.decrypt(os.getenv('ENCRYPTED_DATABASE_URL').encode()).decode()
    
    # 리트리버 로드
    from retriever.factory import get_retriever
    retriever = get_retriever(db_url)
    
    print(f"\n[질문]: {query}")
    print(f"[대상 문서]: {target_source}")
    print("-" * 50)
    
    # 1. 벡터 검색 (Similarity Search with Score)
    # 특정 문서로 필터링하여 검색
    filter_dict = {"source": target_source}
    
    # vectorstore.similarity_search_with_score 사용
    docs_with_score = await asyncio.to_thread(
        retriever.vectorstore.similarity_search_with_score, 
        query, 
        k=5, 
        filter=filter_dict
    )
    
    if not docs_with_score:
        print("유사한 내용을 찾을 수 없습니다. (문서명이 정확한지 확인해 주세요)")
        return

    for i, (doc, score) in enumerate(docs_with_score, 1):
        # PGVector의 score는 거리(Distance)일 수 있으므로 낮을수록 유사함 (L2 distance 기준)
        # 유사도 점수로 변환 (예: 1 - dist)
        print(f"순위 {i} | 거리 점수: {score:.4f} (낮을수록 유사)")
        print(f"내용 요약: {doc.page_content[:100]}...")
        print()

if __name__ == "__main__":
    query = input("유사도를 측정할 질문을 입력하세요: ")
    # 앞에서 확인한 정확한 소스 명칭 사용
    target_source = "청탁금지법 유권해석 자료집.md" 
    asyncio.run(check_similarity(query, target_source))
