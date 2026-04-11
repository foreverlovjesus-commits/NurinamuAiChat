"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🥊  임베딩 모델 성능 비교 벤치마크 (compare_models.py)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  사용법:
    python compare_models.py "유치원 선생님 화분 청탁금지법"

  사전 조건:
    - 비교하려는 각 임베딩 모델이 이미 색인(Indexing)되어 있어야 합니다.
    - 색인은 관리자 화면(admin_dashboard.py)에서 모델 선택 후 "전체 문서 재색인" 버튼으로 수행합니다.

  .env 파일의 COMPARE_MODELS 변수로 비교 대상 모델 목록을 지정합니다.
  예: COMPARE_MODELS=jhgan/ko-sroberta-multitask,BAAI/bge-m3
  미설정 시 현재 GLOBAL_EMBEDDING_MODEL 하나만 테스트합니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import sys
import os
import asyncio
import textwrap

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from cryptography.fernet import Fernet
from dotenv import load_dotenv, dotenv_values
from langchain_community.vectorstores.pgvector import PGVector
from langchain_huggingface import HuggingFaceEmbeddings

load_dotenv(os.path.join(BASE_DIR, ".env"))

# ─────────────────────────────────────────────
# 설정 로드
# ─────────────────────────────────────────────
def get_db_url():
    try:
        cipher = Fernet(os.getenv("MASTER_KEY").encode())
        return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
    except Exception as e:
        print(f"❌ DB URL 복호화 실패: {e}")
        sys.exit(1)

def get_embeddings(model_name: str):
    """모델명 패턴으로 임베딩 엔진을 자동 선택합니다."""
    embed_lower = model_name.lower()
    if "google" in embed_lower or "models/" in embed_lower or "embedding-0" in embed_lower:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        return GoogleGenerativeAIEmbeddings(model=model_name, task_type="RETRIEVAL_QUERY")
    elif "openai" in embed_lower or "text-embedding-3" in embed_lower or "text-embedding-ada" in embed_lower:
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model_name)
    else:
        return HuggingFaceEmbeddings(model_name=model_name)

def search_with_model(db_url: str, model_name: str, query: str, top_k: int = 3):
    """특정 임베딩 모델의 DB 테이블에서 검색하여 상위 문서를 반환합니다."""
    safe_model_name = model_name.replace("/", "_").replace("-", "_")
    base_collection = os.getenv("VECTOR_DB_COLLECTION", "enterprise_knowledge_v3")
    collection_name = f"{base_collection}_{safe_model_name}"

    try:
        embeddings = get_embeddings(model_name)
        vectorstore = PGVector(
            collection_name=collection_name,
            connection_string=db_url,
            embedding_function=embeddings
        )
        docs = vectorstore.similarity_search_with_score(query, k=top_k)
        return docs, None
    except Exception as e:
        return [], str(e)

# ─────────────────────────────────────────────
# 출력 포맷
# ─────────────────────────────────────────────
COLORS = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "cyan":   "\033[96m",
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "red":    "\033[91m",
    "gray":   "\033[90m",
    "white":  "\033[97m",
}

def c(color, text):
    return f"{COLORS.get(color, '')}{text}{COLORS['reset']}"

def print_header(query, models):
    print()
    print(c("cyan", "━" * 70))
    print(c("bold", f"  🥊 임베딩 모델 성능 비교 벤치마크"))
    print(c("cyan", "━" * 70))
    print(f"  {c('white', '질문:')} {query}")
    print(f"  {c('white', '비교 모델:')} {', '.join(models)}")
    print(c("cyan", "━" * 70))

def print_model_results(model_name: str, docs_with_scores, error: str, rank: int):
    medal = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "🔵"
    print()
    print(c("bold", f"  {medal}  [{model_name}]"))
    print(c("gray", "  " + "─" * 66))

    if error:
        print(c("red", f"  ❌ 오류: {error}"))
        print(c("yellow", f"  ⚠️  이 모델의 색인(Indexing)이 완료되었는지 확인하세요."))
        return

    if not docs_with_scores:
        print(c("yellow", "  ⚠️  검색 결과 없음. 이 모델로 색인된 문서가 없을 수 있습니다."))
        return

    for i, (doc, score) in enumerate(docs_with_scores, 1):
        source = doc.metadata.get("source", "알 수 없는 출처")
        content_preview = doc.page_content.replace("\n", " ").strip()
        content_preview = textwrap.shorten(content_preview, width=200, placeholder="...")

        # 점수가 낮을수록 유사도 높음 (L2 거리) / 점수가 높을수록 유사도 높음 (코사인 유사도)
        score_color = "green" if i == 1 else "yellow" if i == 2 else "gray"
        print(f"\n  {c('bold', f'Top {i}')}  {c(score_color, f'[유사도 점수: {score:.4f}]')}  📄 {c('white', source)}")
        print(f"  {c('gray', content_preview)}")

def print_comparison_verdict(models_results: list):
    """검색 결과에서 1위 출처 파일을 모델별로 비교합니다."""
    print()
    print(c("cyan", "━" * 70))
    print(c("bold", "  📊 모델별 TOP 1 결과 요약 비교"))
    print(c("cyan", "━" * 70))
    for model_name, docs_with_scores, error in models_results:
        if error or not docs_with_scores:
            top_source = c("red", "(검색 실패)")
            top_score = "-"
        else:
            top_doc, top_score = docs_with_scores[0]
            top_source = top_doc.metadata.get("source", "?")
            top_score = f"{top_score:.4f}"
        short_name = model_name.split("/")[-1]
        print(f"  {c('white', short_name):40s} → {c('green', top_source)}  (점수: {top_score})")
    print(c("cyan", "━" * 70))
    print()


# ─────────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print(c("yellow", "\n사용법: python compare_models.py \"질문 내용\""))
        print(c("gray",   "예시:   python compare_models.py \"유치원 선생 화분 청탁금지법\""))
        sys.exit(0)

    query = " ".join(sys.argv[1:])
    db_url = get_db_url()

    env_dict = dotenv_values(os.path.join(BASE_DIR, ".env"))
    compare_str = env_dict.get("COMPARE_MODELS", "")
    if compare_str:
        models = [m.strip() for m in compare_str.split(",") if m.strip()]
    else:
        current_model = env_dict.get("GLOBAL_EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
        print(c("yellow", f"\n⚠️  .env 에 COMPARE_MODELS 가 없어 현재 모델 [{current_model}]만 테스트합니다."))
        print(c("gray",   "   비교 테스트를 원하면 .env 에 다음을 추가하세요:"))
        print(c("gray",   "   COMPARE_MODELS=jhgan/ko-sroberta-multitask,BAAI/bge-m3"))
        models = [current_model]

    top_k = 3
    print_header(query, models)

    models_results = []
    for i, model_name in enumerate(models):
        print(f"\n  ⏳ [{model_name}] 모델로 검색 중...", end="", flush=True)
        docs, error = search_with_model(db_url, model_name, query, top_k)
        print(f" 완료!")
        models_results.append((model_name, docs, error))

    # 개별 상세 결과 출력
    for rank, (model_name, docs, error) in enumerate(models_results):
        print_model_results(model_name, docs, error, rank)

    # 최종 요약 비교 테이블
    print_comparison_verdict(models_results)


if __name__ == "__main__":
    main()
