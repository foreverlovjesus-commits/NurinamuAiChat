import os
import re
import sys
import glob
import logging
import hashlib
import asyncio
import psycopg2
from datetime import datetime
import json
import time

import pandas as pd
from dotenv import load_dotenv
from cryptography.fernet import Fernet

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores.pgvector import PGVector
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

load_dotenv()

# 프로젝트 루트 경로 추가 (usage_tracker 모듈 참조용)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
import usage_tracker

# 한국어 문장 경계 인식 separators
_KO_SEPARATORS = ["\n\n", "\n", "다. ", "요. ", "음. ", "함. ", "임. ", "됩니다. ", ". ", " ", ""]

# --- 1. 로깅 및 보안 ---
LOG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "indexer.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# Configure logging to write to both File and Console
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8', mode='a'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def get_db_url():
    try:
        cipher = Fernet(os.getenv("MASTER_KEY").encode())
        return cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
    except Exception:
        sys.exit(1)


DB_URL = get_db_url()
DOC_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.getenv("DOC_ARCHIVE_DIR", "doc_archive"))
PROGRESS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "progress.json")

_progress_state = {
    "file_index": 0,
    "total_files": 0,
    "current_file": "",
    "current_stage": "대기",
    "stage_progress_current": 0,
    "stage_progress_total": 0,
    "overall_percent": 0,
    "status": "running",
    "message": ""
}

def update_progress(**kwargs):
    _progress_state.update(kwargs)
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    try:
        with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_progress_state, f, ensure_ascii=False)
    except Exception:
        pass

# --- 2. 유틸리티 함수 (증분 업데이트) ---
def calculate_file_hash(file_path):
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()


def check_if_already_indexed(collection_name, file_name, file_hash):
    try:
        conn = psycopg2.connect(DB_URL)
        with conn.cursor() as cur:
            sql = """
                SELECT COUNT(e.uuid)
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON e.collection_id = c.uuid
                WHERE c.name = %s AND e.cmetadata->>'source' = %s AND e.cmetadata->>'file_hash' = %s;
            """
            cur.execute(sql, (collection_name, file_name, file_hash))
            count = cur.fetchone()[0]
        conn.close()
        return count > 0
    except Exception as e:
        logger.warning(f"⚠️ 중복 체크 중 경고: {e}")
        return False


def delete_existing_docs(collection_name, file_name):
    try:
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            sql = """
                DELETE FROM langchain_pg_embedding
                WHERE cmetadata->>'source' = %s
                AND collection_id = (SELECT uuid FROM langchain_pg_collection WHERE name = %s LIMIT 1);
            """
            cur.execute(sql, (file_name, collection_name))
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ 기존 데이터 삭제 중 경고: {e}")


# --- 3. 문서 유형 자동 감지 ---
def detect_doc_type(file_path: str, text_sample: str = "") -> str:
    """
    우선순위:
    1. 폴더명 (법령/, 판례/, FAQ/) → 확실한 분류
    2. 파일 확장자 (.xlsx/.csv → faq)
    3. 텍스트 패턴 매칭
    4. 기본값: general
    """
    path_norm = file_path.replace("\\", "/").lower()

    # 1. 폴더명 기반 (최우선) — 단, .md 파일은 general로 처리 (FAQ 폴더의 md 변환본)
    is_md = file_path.lower().endswith('.md')
    if "/법령/" in path_norm:
        return "legal"
    if "/판례/" in path_norm:
        return "case"
    if "/faq/" in path_norm and not is_md:
        return "faq"
    if "/faq/" in path_norm and is_md:
        return "general"

    # 2. 확장자 기반
    if file_path.lower().endswith(('.xlsx', '.xls', '.csv')):
        return "faq"

    # 3. 텍스트 패턴 기반
    if re.search(r'제\s*\d+\s*조', text_sample):
        return "legal"
    if re.search(r'사건\s*번호|재결\s*번호|청\s*구\s*인|피청구인|주\s*문|판\s*결', text_sample):
        return "case"

    return "general"


# --- 4. 파서 ---
_easyocr_reader = None

def get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is None:
        import easyocr
        import warnings
        warnings.filterwarnings("ignore", category=UserWarning)
        logger.info("⏳ EasyOCR 파이썬 로컬 모델을 메모리에 로딩 중입니다... (최초 1회 한정)")
        _easyocr_reader = easyocr.Reader(['ko', 'en'])
    return _easyocr_reader

def get_hwp_text(file_path):
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        if file_path.lower().endswith('.hwpx'):
            text_content = []
            with zipfile.ZipFile(file_path, 'r') as z:
                content_files = [f for f in z.namelist() if 'Contents/section' in f]
                for cf in content_files:
                    with z.open(cf) as f:
                        tree = ET.parse(f)
                        for elem in tree.iter():
                            if elem.text:
                                text_content.append(elem.text.strip())
            return "\n".join(text_content)
        return ""
    except Exception as e:
        logger.warning(f"⚠️ 한글 파싱 폴백 실패: {e}")
        return ""


def get_llama_parse_docs(file_path):
    from llama_parse import LlamaParse
    parser = LlamaParse(
        api_key=os.getenv("LLAMA_CLOUD_API_KEY"),
        result_type="markdown",
        num_workers=4,
        language="ko"
    )
    llama_docs = parser.load_data(file_path)
    return [Document(page_content=doc.text, metadata=doc.metadata) for doc in llama_docs]


def get_unstructured_docs(file_path):
    from unstructured.partition.auto import partition
    elements = partition(filename=file_path, strategy="hi_res", infer_table_structure=True)
    return [Document(page_content=str(el), metadata={"source": os.path.basename(file_path)}) for el in elements]


def get_pdfplumber_docs(file_path):
    """새롭게 만든 pdf_parser 모듈을 사용하여 문서를 추출합니다."""
    from indexer.pdf_parser import extract_text_from_pdf
    text = extract_text_from_pdf(file_path)
    if text.strip():
        return [Document(page_content=text, metadata={"source": os.path.basename(file_path)})]
    return []


def parse_raw_docs(file_path):
    """파일 형식에 맞게 원문 파싱 (공통)"""
    file_name = os.path.basename(file_path)
    ext = file_path.lower()
    PARSER_TYPE = os.getenv("PDF_PARSER_TYPE", "llamaparse").lower()

    try:
        if ext.endswith('.pdf'):
            if PARSER_TYPE == "llamaparse":
                return get_llama_parse_docs(file_path)
            # LlamaParse를 사용하지 않는 경우, 안전한 pdfplumber 기반 커스텀 파서를 사용
            return get_pdfplumber_docs(file_path)
        elif ext.endswith('.hwpx'):
            logger.info(f"📝 {file_name}: HWPX 전용 파서 가동")
            hwp_text = get_hwp_text(file_path)
            if hwp_text:
                return [Document(page_content=hwp_text, metadata={"source": file_name})]
            return get_unstructured_docs(file_path)
        elif ext.endswith('.md'):
            with open(file_path, 'r', encoding='utf-8') as f:
                text = f.read()
            return [Document(page_content=text, metadata={"source": file_name})]
        elif ext.endswith(('.xlsx', '.xls', '.csv')):
            return []  # FAQ는 chunk_faq()에서 직접 처리
        elif ext.endswith(('.jpg', '.jpeg', '.png')):
            logger.info(f"🖼️ {file_name}: 100% 로컬 파이썬 OCR 텍스트 추출 가동")
            reader = get_easyocr_reader()
            result = reader.readtext(file_path, detail=0)
            image_text = "\n".join(result).strip()
            if image_text:
                return [Document(page_content=image_text, metadata={"source": file_name})]
            else:
                logger.warning(f"⚠️ {file_name}에서 추출된 텍스트가 없습니다.")
                return []
        else:
            return get_unstructured_docs(file_path)
    except Exception as e:
        logger.error(f"❌ {file_name} 파싱 실패: {e}")
        return []


# --- 5. 유형별 청킹 전략 ---

def _base_meta(file_name, file_hash, doc_type, extra=None):
    meta = {
        "source": file_name,
        "file_hash": file_hash,
        "doc_type": doc_type,
        "processed_at": datetime.now().isoformat(),
    }
    if extra:
        meta.update(extra)
    return meta


def chunk_legal(docs, file_name, file_hash):
    """
    법령: 조(條) 단위 청킹
    "제1조(목적)" 등의 패턴으로 분할 → 각 조가 1청크
    """
    chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=80, separators=_KO_SEPARATORS)

    for doc in docs:
        full_text = doc.page_content
        # 제X조 패턴으로 분할 (조 번호와 제목 포함)
        parts = re.split(r'(제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]*\))?)', full_text)

        if len(parts) <= 1:
            # 조 패턴 없으면 일반 청킹으로 대체
            for sub in splitter.split_text(full_text):
                chunks.append(Document(
                    page_content=sub,
                    metadata=_base_meta(file_name, file_hash, "legal")
                ))
            continue

        # parts = [앞부분, "제1조", 내용, "제2조", 내용, ...]
        i = 1
        while i < len(parts):
            article_title = parts[i].strip()
            article_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if article_body:
                # [마크다운 자동 위계화 로직 추가]
                # 1. 항(①, ② 등) 치환
                clean_body = re.sub(r'([①-⑳])', r'\n- \1', article_body)
                # 2. 호(1., 2. 등) 치환 (들여쓰기)
                clean_body = re.sub(r'\n\s*(\d+)\.', r'\n  - \1.', clean_body)
                # 3. 목(가., 나. 등) 치환 (추가 들여쓰기)
                clean_body = re.sub(r'\n\s*([가-하])\.', r'\n    - \1.', clean_body)
                # 다중 공백 제거
                clean_body = re.sub(r'\n{3,}', r'\n\n', clean_body)
                
                # 조문 제목을 Heading2(##)로 합치기
                chunk_text = f"## {article_title}\n{clean_body.strip()}"
                
                # 조 내용이 너무 길면 추가 분할
                if len(chunk_text) > 1200:
                    for sub in splitter.split_text(chunk_text):
                        chunks.append(Document(
                            page_content=sub,
                            metadata=_base_meta(file_name, file_hash, "legal",
                                                {"article": article_title})
                        ))
                else:
                    chunks.append(Document(
                        page_content=chunk_text,
                        metadata=_base_meta(file_name, file_hash, "legal",
                                            {"article": article_title})
                    ))
            i += 2

    logger.info(f"  └─ [법령] {len(chunks)}개 조항 청크 생성")
    return chunks


def chunk_case(docs, file_name, file_hash):
    """
    판례/결정례: 사건 단위 청킹
    사건번호/재결번호 기준으로 분할 → 사건 1건 = 1~N청크
    """
    chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=100, separators=_KO_SEPARATORS)

    for doc in docs:
        full_text = doc.page_content

        # 사건번호 또는 재결번호로 사건 단위 분리
        cases = re.split(r'(?=(?:사건|재결)\s*번호\s*[:：])', full_text)

        for case_text in cases:
            case_text = case_text.strip()
            if len(case_text) < 50:
                continue

            # 사건번호/재결번호 추출 (메타데이터용)
            num_match = re.search(r'(?:사건|재결)\s*번호\s*[:：]\s*([^\n]+)', case_text)
            case_num = num_match.group(1).strip() if num_match else ""

            if len(case_text) <= 1500:
                chunks.append(Document(
                    page_content=case_text,
                    metadata=_base_meta(file_name, file_hash, "case",
                                        {"case_number": case_num})
                ))
            else:
                # 긴 사건은 주문/이유 기준으로 섹션 분할
                sections = re.split(r'(【주\s*문】|【이\s*유】|【판시사항】|【판결요지】)', case_text)
                if len(sections) > 1:
                    i = 0
                    while i < len(sections):
                        section_title = sections[i].strip() if re.match(r'【', sections[i]) else ""
                        section_body = sections[i + 1].strip() if i + 1 < len(sections) else sections[i].strip()
                        if section_title:
                            md_title = section_title.replace("【", "").replace("】", "").strip()
                            content = f"### {md_title}\n{section_body}"
                        else:
                            content = section_body
                        if content and len(content) > 50:
                            for sub in splitter.split_text(content):
                                chunks.append(Document(
                                    page_content=sub,
                                    metadata=_base_meta(file_name, file_hash, "case",
                                                        {"case_number": case_num,
                                                         "section": section_title})
                                ))
                        i += 2
                else:
                    for sub in splitter.split_text(case_text):
                        chunks.append(Document(
                            page_content=sub,
                            metadata=_base_meta(file_name, file_hash, "case",
                                                {"case_number": case_num})
                        ))

    logger.info(f"  └─ [판례] {len(chunks)}개 사건 청크 생성")
    return chunks


def chunk_faq(file_path, file_name, file_hash):
    """
    FAQ (xlsx/csv): 행(Row) 단위 청킹
    Q+A 쌍이 분리되지 않도록 한 행 = 한 청크
    """
    chunks = []
    try:
        if file_path.lower().endswith('.csv'):
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        else:
            df = pd.read_excel(file_path)

        for _, row in df.iterrows():
            # 컬럼명: 값 형태로 자연어 변환
            parts = []
            for col, val in row.items():
                if pd.notna(val) and str(val).strip():
                    parts.append(f"{col}: {str(val).strip()}")
            row_text = " | ".join(parts)
            if len(row_text) < 10:
                continue
            chunks.append(Document(
                page_content=row_text,
                metadata=_base_meta(file_name, file_hash, "faq")
            ))

    except Exception as e:
        logger.warning(f"⚠️ FAQ 행 단위 파싱 실패, general로 대체: {e}")
        return []

    logger.info(f"  └─ [FAQ] {len(chunks)}개 행 청크 생성")
    return chunks


def chunk_general(docs, file_name, file_hash):
    """
    일반 문서 (지침, 매뉴얼, 공문): 마크다운 헤더 단위 청킹 (기존 방식)
    """
    headers_to_split_on = [("#", "H1"), ("##", "H2"), ("###", "H3")]
    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    chunks = []
    for doc in docs:
        for chunk in markdown_splitter.split_text(doc.page_content):
            chunk.metadata.update(_base_meta(file_name, file_hash, "general"))
            chunks.append(chunk)
    logger.info(f"  └─ [일반] {len(chunks)}개 섹션 청크 생성")
    return chunks


# --- 6. 통합 문서 처리 ---
def process_document_v4(file_path, file_hash, tagger=None):
    file_name = os.path.basename(file_path)
    update_progress(current_stage="문서 파싱 및 청킹", stage_progress_current=0, stage_progress_total=1, message="문서 구조 분석 중")

    # 파일 유형 판별을 위한 텍스트 샘플 추출 (최초 1000자)
    text_sample = ""
    raw_docs = parse_raw_docs(file_path)
    if raw_docs:
        text_sample = raw_docs[0].page_content[:1000]

    doc_type = detect_doc_type(file_path, text_sample)
    logger.info(f"📂 {file_name} → 유형 감지: [{doc_type.upper()}]")

    if doc_type == "legal":
        chunks = chunk_legal(raw_docs, file_name, file_hash)

    elif doc_type == "case":
        chunks = chunk_case(raw_docs, file_name, file_hash)

    elif doc_type == "faq":
        # xlsx/csv는 parse_raw_docs에서 빈 리스트 반환 → 직접 처리
        chunks = chunk_faq(file_path, file_name, file_hash)
        if not chunks and raw_docs:
            chunks = chunk_general(raw_docs, file_name, file_hash)

    else:
        chunks = chunk_general(raw_docs, file_name, file_hash)

    # 메타데이터 자동 태깅
    if tagger and chunks:
        tag_provider = os.getenv("TAGGING_LLM_PROVIDER", "local").lower()
        use_async = tag_provider in ("gemini", "openai")

        if use_async:
            # API 모델: 비동기 병렬 처리
            try:
                chunk_texts = [c.page_content for c in chunks]
                concurrency = int(os.getenv("TAGGING_CONCURRENCY", "3"))
                delay = float(os.getenv("TAGGING_DELAY", "0.5"))
                logger.info(f"  └─ 🏷️ {len(chunks)}개 청크 병렬 태깅 시작 (동시 {concurrency}건, 딜레이 {delay}초)")

                update_progress(current_stage="메타데이터 태깅", stage_progress_current=0, stage_progress_total=len(chunks), message="병렬 태깅 중")
                loop = asyncio.new_event_loop()
                tag_results = loop.run_until_complete(
                    tagger.tag_chunks_batch_async(chunk_texts, max_concurrency=concurrency, delay=delay)
                )
                loop.close()
                update_progress(stage_progress_current=len(chunks), message="태깅 완료")

                tagged_count = 0
                for chunk, tags in zip(chunks, tag_results):
                    if tags:
                        chunk.metadata.update(tags)
                        tagged_count += 1
                logger.info(f"  └─ 🏷️ {tagged_count}/{len(chunks)}개 청크 태깅 완료")
            except Exception as e:
                logger.warning(f"병렬 태깅 실패 (태깅 없이 계속): {e}")
        else:
            # 로컬 LLM: 동기 순차 처리 (Ollama asyncio 불안정 방지)
            logger.info(f"  └─ 🏷️ {len(chunks)}개 청크 순차 태깅 시작 (로컬 LLM)")
            update_progress(current_stage="메타데이터 태깅", stage_progress_current=0, stage_progress_total=len(chunks), message="순차 태깅 중")
            tagged_count = 0
            for i, chunk in enumerate(chunks):
                try:
                    tags = tagger.tag_chunk_sync(chunk.page_content)
                    if tags:
                        chunk.metadata.update(tags)
                        tagged_count += 1
                except Exception as e:
                    logger.warning(f"태깅 실패 (건너뜀): {e}")
                if (i + 1) % 20 == 0:
                    logger.info(f"  └─ 🏷️ 태깅 진행: {i+1}/{len(chunks)}")
                update_progress(stage_progress_current=i+1)
            logger.info(f"  └─ 🏷️ {tagged_count}/{len(chunks)}개 청크 태깅 완료")
    return chunks


# --- 7. DB 최적화 ---
def optimize_database():
    try:
        conn = psycopg2.connect(DB_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_hnsw_v4
                ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """)
            cur.execute("ALTER TABLE langchain_pg_embedding ADD COLUMN IF NOT EXISTS fts tsvector;")
            cur.execute("UPDATE langchain_pg_embedding SET fts = to_tsvector('simple', document) WHERE fts IS NULL;")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_fts_v4 ON langchain_pg_embedding USING GIN(fts);")
            # 메타데이터 필터 검색용 GIN 인덱스
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_cmetadata_gin
                ON langchain_pg_embedding USING GIN(cmetadata jsonb_path_ops);
            """)
        conn.close()
        logger.info("✅ DB 최적화 완료 (GIN 메타데이터 인덱스 포함)")
    except Exception as e:
        logger.warning(f"⚠️ 최적화 중 경고: {e}")


# --- 8. 메인 실행 ---
def run_indexer_v4():
    logger.info("=== 🛠️ 지능형 범용 인덱서 V4 가동 ===")
    logger.info(f"문서 폴더: {DOC_FOLDER}")
    logger.info("유형별 청킹: 법령(조항) | 판례(사건) | FAQ(행) | 일반(섹션)")

    embedding_model = os.getenv("GLOBAL_EMBEDDING_MODEL", "jhgan/ko-sroberta-multitask")
    logger.info(f"사용 임베딩 모델: {embedding_model}")
    
    embed_lower = embedding_model.lower()
    emb_provider = os.getenv("GLOBAL_EMBEDDING_PROVIDER", "").lower()
    if emb_provider == "vertex":
        from langchain_google_vertexai import VertexAIEmbeddings
        embeddings = VertexAIEmbeddings(model_name=embedding_model)
    elif "google" in embed_lower or "models/" in embed_lower or "embedding-0" in embed_lower:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model, task_type="RETRIEVAL_DOCUMENT")
    elif "openai" in embed_lower or "text-embedding-3" in embed_lower or "text-embedding-ada" in embed_lower:
        from langchain_openai import OpenAIEmbeddings
        embeddings = OpenAIEmbeddings(model=embedding_model)
    else:
        embeddings = HuggingFaceEmbeddings(model_name=embedding_model)

    safe_model_name = embedding_model.replace("/", "_").replace("-", "_")
    base_collection = os.getenv("VECTOR_DB_COLLECTION", "enterprise_knowledge_v3")
    collection_name = f"{base_collection}_{safe_model_name}"

    extensions = ['*.pdf', '*.txt', '*.md', '*.xlsx', '*.xls', '*.docx', '*.doc', '*.hwp', '*.hwpx', '*.csv', '*.jpg', '*.jpeg', '*.png']
    files = []
    for ext in extensions:
        files.extend(glob.glob(os.path.join(DOC_FOLDER, f"**/{ext}"), recursive=True))

    target_json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "target_files.json")
    
    if os.path.exists(target_json_path):
        logger.info("🎯 부분 색인 모드 가동: target_files.json 에 명시된 파일만 우선순위 순으로 처리합니다.")
        try:
            with open(target_json_path, "r", encoding="utf-8") as f:
                target_list = json.load(f)
            # 파일명 → 실제경로 매핑
            basename_to_path = {os.path.basename(f): f for f in files}
            # target_list 순서(=우선순위)를 유지하며 매칭
            ordered_files = []
            for t in target_list:
                t_base = os.path.basename(t)
                if t_base in basename_to_path:
                    ordered_files.append(basename_to_path[t_base])
            files = ordered_files
            logger.info(f"  대상 파일 {len(files)}건 매칭됨 (우선순위 순)")
            os.remove(target_json_path)
        except Exception as e:
            logger.error(f"target_files.json 파싱 실패: {e}")

    if not files:
        logger.warning(f"처리할 파일이 없습니다. 경로: {DOC_FOLDER}")
        update_progress(status="completed", message="처리할 파일 없음", overall_percent=100)
        return

    total_files = len(files)
    logger.info(f"총 {total_files}개 파일 발견")
    update_progress(total_files=total_files)

    # 메타데이터 태거 초기화 (환경변수로 on/off)
    tagger = None
    if os.getenv("ENABLE_METADATA_TAGGING", "true").lower() == "true":
        try:
            from indexer.metadata_tagger import MetadataTagger
            tag_provider = os.getenv("TAGGING_LLM_PROVIDER", os.getenv("GLOBAL_LLM_PROVIDER", "local")).lower()
            tag_model = os.getenv("TAGGING_LLM_MODEL", "")

            if tag_provider == "gemini":
                from langchain_google_genai import ChatGoogleGenerativeAI
                tag_model = os.getenv("GEMINI_ROUTER_MODEL", "gemini-2.5-flash")
                tag_llm = ChatGoogleGenerativeAI(model=tag_model, temperature=0)
            elif tag_provider == "vertex":
                from langchain_google_vertexai import ChatVertexAI
                tag_model = os.getenv("GEMINI_ROUTER_MODEL", "gemini-1.5-flash")
                tag_llm = ChatVertexAI(
                    project=os.getenv("GCP_PROJECT_ID"),
                    location=os.getenv("GCP_LOCATION", "asia-northeast3"),
                    model=tag_model, temperature=0
                )
            elif tag_provider == "openai":
                from langchain_openai import ChatOpenAI
                tag_llm = ChatOpenAI(model=tag_model or "gpt-4o-mini", temperature=0)
            else:
                from langchain_ollama import ChatOllama
                tag_llm = ChatOllama(
                    model=tag_model or os.getenv("ROUTER_LLM_MODEL", "exaone3.5:2.4b"),
                    temperature=0, base_url=os.getenv("OLLAMA_BASE_URL")
                )
            tagger = MetadataTagger(tag_llm)
            logger.info(f"🏷️ 메타데이터 태깅 활성화 (provider={tag_provider}, model={tag_llm.model})")
        except Exception as e:
            logger.warning(f"⚠️ 태거 초기화 실패 (태깅 없이 진행): {e}")

    force_reindex = os.getenv("FORCE_REINDEX", "false").lower() == "true"
    _content_hashes = set()  # 크로스파일 콘텐츠 중복 제거용
    for i, f in enumerate(files):
        file_name = os.path.basename(f)
        percent = int((i / total_files) * 100)
        update_progress(file_index=i, current_file=file_name, overall_percent=percent, status="running")

        current_hash = calculate_file_hash(f)

        if not force_reindex and check_if_already_indexed(collection_name, file_name, current_hash):
            logger.info(f"⏭️  Skip (변경 없음): {file_name}")
            continue

        delete_existing_docs(collection_name, file_name)
        docs = process_document_v4(f, current_hash, tagger=tagger)

        # 크로스파일 콘텐츠 중복 제거
        if docs:
            unique_docs = []
            for doc in docs:
                content_hash = hashlib.md5(doc.page_content.encode('utf-8')).hexdigest()
                if content_hash not in _content_hashes:
                    unique_docs.append(doc)
                    _content_hashes.add(content_hash)
            dedup_count = len(docs) - len(unique_docs)
            if dedup_count:
                logger.info(f"  └─ 🔄 중복 제거: {dedup_count}개 청크 스킵")
            docs = unique_docs

        if docs:
            update_progress(current_stage="임베딩 및 DB 저장", stage_progress_current=0, stage_progress_total=len(docs), message="벡터 DB 저장 중")
            t_embed_start = time.time()
            try:
                PGVector.from_documents(
                    documents=docs,
                    embedding=embeddings,
                    collection_name=collection_name,
                    connection_string=DB_URL,
                    pre_delete_collection=False
                )
                update_progress(stage_progress_current=len(docs))
                logger.info(f"✅ 완료: {file_name} ({len(docs)}청크)")
                
                # 임베딩 API 사용량 기록 (상용 모델인 경우만 비용 발생)
                t_embed_end = time.time()
                latency_ms = int((t_embed_end - t_embed_start) * 1000)
                total_chars = sum(len(d.page_content) for d in docs)
                # 임베딩 모델의 토큰 추정: Google/OpenAI 임베딩은 입력만 과금
                provider = "embedding"
                if "google" in embed_lower or "models/" in embed_lower:
                    provider = "google_embedding"
                elif "openai" in embed_lower or "text-embedding" in embed_lower:
                    provider = "openai_embedding"
                else:
                    provider = "local_embedding"  # 무료
                usage_tracker.record_usage(
                    provider=provider,
                    model=embedding_model,
                    call_type="embedding",
                    input_tokens=total_chars,
                    output_tokens=0,
                    latency_ms=latency_ms,
                    status="success",
                    question_preview=f"indexing:{file_name}({len(docs)}청크)"
                )
            except Exception as e:
                t_embed_end = time.time()
                latency_ms = int((t_embed_end - t_embed_start) * 1000)
                logger.error(f"❌ 임베딩 실패: {file_name} - {e}")
                usage_tracker.record_error(
                    provider="embedding",
                    model=embedding_model,
                    call_type="embedding",
                    error_msg=str(e),
                    latency_ms=latency_ms,
                    question_preview=f"indexing:{file_name}"
                )
        else:
            logger.warning(f"⚠️ 청크 없음: {file_name}")

    optimize_database()
    update_progress(file_index=total_files, current_file="완료", current_stage="작업 완료", stage_progress_current=100, stage_progress_total=100, overall_percent=100, status="completed", message="인덱싱 종료")

if __name__ == "__main__":
    run_indexer_v4()
