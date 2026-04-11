import psycopg2
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores.pgvector import PGVector
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever

def build_hybrid_retriever(db_url: str, collection_name: str = "std_ops_guidelines"):
    print("🔍 하이브리드 검색 엔진(BM25 + Vector) 초기화 중...")

    # 1. Vector Retriever
    embeddings = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")
    vectorstore = PGVector(collection_name=collection_name, connection_string=db_url, embedding_function=embeddings)
    vector_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

    # 2. BM25 Retriever
    conn = psycopg2.connect(db_url)
    cursor = conn.cursor()
    cursor.execute("SELECT document, cmetadata FROM langchain_pg_embedding")
    rows = cursor.fetchall()
    conn.close()

    docs = [Document(page_content=row[0], metadata=row[1]) for row in rows]
    bm25_retriever = BM25Retriever.from_documents(docs)
    bm25_retriever.k = 5

    # 3. 앙상블 결합
    ensemble_retriever = EnsembleRetriever(
        retrievers=[bm25_retriever, vector_retriever],
        weights=[0.3, 0.7] # 키워드 30%, 벡터 70%
    )
    print("✅ 검색 엔진 초기화 완료")
    return ensemble_retriever
