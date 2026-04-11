"""
기존 인덱싱 데이터에 메타데이터 태그를 소급 적용하는 백필 스크립트

사용법:
    python scripts/backfill_metadata_tags.py                  # 실행
    python scripts/backfill_metadata_tags.py --dry-run        # 미리보기만
    python scripts/backfill_metadata_tags.py --batch-size 20  # 배치 크기 지정
"""
import argparse
import json
import logging
import os
import sys
import time

import psycopg2
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# 프로젝트 루트 추가
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def get_db_url():
    try:
        cipher = Fernet(os.getenv("MASTER_KEY").encode())
        return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
    except Exception:
        return os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/nurinamu_db")


def get_tagger():
    """태거 LLM 초기화"""
    from indexer.metadata_tagger import MetadataTagger

    provider = os.getenv("TAGGING_LLM_PROVIDER", os.getenv("GLOBAL_LLM_PROVIDER", "local")).lower()
    model = os.getenv("TAGGING_LLM_MODEL", "")

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(model=model or "gemini-2.0-flash", temperature=0)
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=model or "gpt-4o-mini", temperature=0)
    else:
        from langchain_ollama import ChatOllama
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        llm = ChatOllama(
            model=model or os.getenv("ROUTER_LLM_MODEL", "exaone3.5:2.4b"),
            temperature=0, base_url=ollama_url
        )

    return MetadataTagger(llm)


def main():
    parser = argparse.ArgumentParser(description="기존 데이터 메타데이터 태깅 백필")
    parser.add_argument("--batch-size", type=int, default=50, help="한 번에 처리할 청크 수")
    parser.add_argument("--dry-run", action="store_true", help="DB 업데이트 없이 미리보기만")
    parser.add_argument("--limit", type=int, default=0, help="처리할 최대 청크 수 (0=전체)")
    args = parser.parse_args()

    db_url = get_db_url()
    tagger = get_tagger()
    logger.info(f"백필 시작 (batch_size={args.batch_size}, dry_run={args.dry_run})")

    conn = psycopg2.connect(db_url)

    # 태깅되지 않은 청크 조회 (law_category 키가 없는 것)
    with conn.cursor() as cur:
        count_sql = """
            SELECT COUNT(*) FROM langchain_pg_embedding
            WHERE cmetadata->>'law_category' IS NULL;
        """
        cur.execute(count_sql)
        total = cur.fetchone()[0]

    logger.info(f"태깅 대상: {total}개 청크")
    if total == 0:
        logger.info("태깅할 청크가 없습니다.")
        conn.close()
        return

    if args.limit > 0:
        total = min(total, args.limit)

    processed, tagged, failed = 0, 0, 0
    t_start = time.time()

    with conn.cursor() as cur:
        select_sql = """
            SELECT uuid, document, cmetadata FROM langchain_pg_embedding
            WHERE cmetadata->>'law_category' IS NULL
            ORDER BY uuid
            LIMIT %s;
        """
        cur.execute(select_sql, (total,))
        rows = cur.fetchall()

    for i in range(0, len(rows), args.batch_size):
        batch = rows[i:i + args.batch_size]

        for row_uuid, document, cmetadata in batch:
            processed += 1
            text = document[:2000] if document else ""
            if not text.strip():
                continue

            try:
                tags = tagger.tag_chunk_sync(text)
            except Exception as e:
                logger.warning(f"태깅 실패 (uuid={row_uuid}): {e}")
                failed += 1
                continue

            if not tags:
                continue

            if args.dry_run:
                logger.info(f"[DRY-RUN] uuid={row_uuid[:8]}... tags={json.dumps(tags, ensure_ascii=False)}")
                tagged += 1
                continue

            # cmetadata에 태그 병합 (기존 키 보존)
            try:
                with conn.cursor() as cur:
                    update_sql = """
                        UPDATE langchain_pg_embedding
                        SET cmetadata = cmetadata || %s::jsonb
                        WHERE uuid = %s;
                    """
                    cur.execute(update_sql, (json.dumps(tags, ensure_ascii=False), row_uuid))
                conn.commit()
                tagged += 1
            except Exception as e:
                conn.rollback()
                logger.warning(f"DB 업데이트 실패 (uuid={row_uuid}): {e}")
                failed += 1

        elapsed = time.time() - t_start
        rate = processed / elapsed if elapsed > 0 else 0
        logger.info(f"진행: {processed}/{total} ({tagged} tagged, {failed} failed, {rate:.1f} chunks/s)")

    conn.close()
    total_time = time.time() - t_start
    logger.info(f"백필 완료: {tagged}/{processed} 태깅 성공, {failed} 실패, {total_time:.1f}초 소요")


if __name__ == "__main__":
    main()
