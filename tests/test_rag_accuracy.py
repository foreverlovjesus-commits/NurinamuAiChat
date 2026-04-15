"""
tests/test_rag_accuracy.py
==========================
NuriNamu AI — RAG 응답 정확도 자동 평가 스크립트

측정 지표:
  1. 카테고리 분류 정확도 (Category Classification Accuracy)
     - LLM Router 가 golden_dataset의 expected_category를 올바르게 분류하는 비율
  2. 검색 히트율 (Retrieval Hit Rate @K)
     - 검색된 상위 K개 문서에 expected_keywords 중 1개 이상이 포함되는 비율
  3. 키워드 커버리지 (Keyword Coverage)
     - 검색 결과에서 expected_keywords 전체가 포함되는 비율

실행 방법:
  python -m tests.test_rag_accuracy               # 전체 실행
  python -m tests.test_rag_accuracy --ids CK-001  # 특정 케이스만
  python -m tests.test_rag_accuracy --top-k 5 --report json
"""

import os
import sys
import json
import asyncio
import argparse
import time
from datetime import datetime
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

DATASET_PATH = Path(__file__).parent / "golden_dataset.json"
REPORT_DIR   = _ROOT / "logs" / "accuracy_reports"


# ── 결과 저장 ─────────────────────────────────────────────────────────────────
def save_report(results: list, summary: dict, report_format: str = "json"):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = {"timestamp": ts, "summary": summary, "details": results}

    json_path = REPORT_DIR / f"accuracy_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 최신 결과를 latest.json 으로도 저장 (Admin Dashboard가 읽음)
    latest_path = REPORT_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n📄 리포트 저장: {json_path}")
    return json_path


# ── 리트리버 초기화 ───────────────────────────────────────────────────────────
def init_retriever():
    from retriever.factory import get_retriever
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        from cryptography.fernet import Fernet
        try:
            cipher  = Fernet(os.getenv("MASTER_KEY").encode())
            db_url  = cipher.decrypt(os.getenv("ENCRYPTED_DATABASE_URL").encode()).decode()
        except Exception as e:
            print(f"❌ DB URL 복호화 실패: {e}")
            sys.exit(1)
    return get_retriever(db_url), db_url


# ── LLM 라우터 초기화 ─────────────────────────────────────────────────────────
def init_router_llm():
    llm_type = os.getenv("GLOBAL_LLM_PROVIDER", "local").lower()
    if llm_type == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        return ChatGoogleGenerativeAI(model=model, temperature=0)
    elif llm_type == "openai":
        from langchain_openai import ChatOpenAI
        model = os.getenv("OPENAI_ROUTER_MODEL", "gpt-4o-mini")
        return ChatOpenAI(model=model, temperature=0)
    elif llm_type in ("anthropic",):
        from langchain_anthropic import ChatAnthropic
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        return ChatAnthropic(model=model, temperature=0)
    else:
        from langchain_ollama import ChatOllama
        model = os.getenv("ROUTER_LLM_MODEL", "exaone3.5:2.4b")
        ollama_url = os.getenv("OLLAMA_BASE_URL")
        return ChatOllama(model=model, temperature=0, base_url=ollama_url)


# ── 단일 케이스 평가 ──────────────────────────────────────────────────────────
async def evaluate_case(case: dict, retriever, router_llm, top_k: int = 3) -> dict:
    from rag.rag_engine import RAGEngineV3
    engine = RAGEngineV3(retriever)

    q = case["question"]
    expected_cat  = case["expected_category"]
    expected_kws  = [kw.lower() for kw in case["expected_keywords"]]
    case_id = case["id"]

    result = {
        "id": case_id,
        "question": q,
        "expected_category": expected_cat,
        "expected_keywords": case["expected_keywords"],
        # 측정값 (초기화)
        "predicted_category": None,
        "category_correct": False,
        "retrieved_docs_count": 0,
        "hit_at_k": False,           # expected_keywords 중 1개 이상 포함
        "keyword_coverage": 0.0,     # 포함된 키워드 비율
        "matched_keywords": [],
        "latency_ms": 0,
        "error": None,
    }

    t0 = time.time()

    # ── 1. 카테고리 분류 평가 ──────────────────────────────────────────────
    try:
        route_info = await engine.classify_category(q, router_llm)
        predicted_cat = route_info.get("category", "일반 Q&A")
        result["predicted_category"] = predicted_cat
        result["category_correct"] = (predicted_cat == expected_cat)
    except Exception as e:
        result["error"] = f"카테고리 분류 오류: {e}"
        result["predicted_category"] = "분류 실패"

    # ── 2. 검색 히트율 평가 ───────────────────────────────────────────────
    try:
        docs = await retriever.retrieve(q, final_k=top_k)
        result["retrieved_docs_count"] = len(docs)

        combined_text = " ".join(d.page_content for d in docs).lower()
        matched = [kw for kw in expected_kws if kw in combined_text]
        result["matched_keywords"] = matched
        result["hit_at_k"] = len(matched) > 0
        result["keyword_coverage"] = round(len(matched) / len(expected_kws), 3) if expected_kws else 0.0

    except Exception as e:
        if result["error"]:
            result["error"] += f" / 검색 오류: {e}"
        else:
            result["error"] = f"검색 오류: {e}"

    result["latency_ms"] = int((time.time() - t0) * 1000)
    return result


# ── 전체 평가 실행 ────────────────────────────────────────────────────────────
async def run_evaluation(dataset: list, top_k: int = 3, verbose: bool = True) -> tuple[list, dict]:
    retriever, _ = init_retriever()
    router_llm   = init_router_llm()

    total = len(dataset)
    results = []

    print(f"\n🔍 NuriNamu RAG 정확도 평가 시작 (총 {total}개 케이스, Top-{top_k})")
    print("=" * 60)

    for i, case in enumerate(dataset, 1):
        if verbose:
            print(f"\n[{i:2d}/{total}] {case['id']} — {case['question'][:40]}...")

        res = await evaluate_case(case, retriever, router_llm, top_k)
        results.append(res)

        if verbose:
            cat_icon = "✅" if res["category_correct"] else "❌"
            hit_icon = "✅" if res["hit_at_k"]         else "❌"
            print(f"  {cat_icon} 분류: {res['predicted_category']!r:15s} (정답: {res['expected_category']!r})")
            print(f"  {hit_icon} 검색 히트율: 키워드 {len(res['matched_keywords'])}/{len(case['expected_keywords'])}개 "
                  f"({res['keyword_coverage']*100:.0f}%)  |  {res['latency_ms']}ms")
            if res["error"]:
                print(f"  ⚠️  {res['error']}")

    # ── 요약 통계 ──────────────────────────────────────────────────────────
    cat_correct   = sum(1 for r in results if r["category_correct"])
    hit_count     = sum(1 for r in results if r["hit_at_k"])
    avg_coverage  = sum(r["keyword_coverage"] for r in results) / total if total else 0
    avg_latency   = sum(r["latency_ms"] for r in results) / total if total else 0

    summary = {
        "total_cases": total,
        "top_k": top_k,
        "category_accuracy": round(cat_correct / total, 4) if total else 0,
        "category_accuracy_pct": f"{cat_correct / total * 100:.1f}%" if total else "0%",
        "retrieval_hit_rate": round(hit_count / total, 4) if total else 0,
        "retrieval_hit_rate_pct": f"{hit_count / total * 100:.1f}%" if total else "0%",
        "avg_keyword_coverage": round(avg_coverage, 4),
        "avg_keyword_coverage_pct": f"{avg_coverage * 100:.1f}%",
        "avg_latency_ms": round(avg_latency),
        "pass": cat_correct,
        "fail_category": total - cat_correct,
        "fail_retrieval": total - hit_count,
        "evaluated_at": datetime.now().isoformat(),
    }

    # ── 카테고리별 분류 오류 분석 ─────────────────────────────────────────
    wrong = [r for r in results if not r["category_correct"]]
    if wrong:
        summary["misclassified"] = [
            {"id": r["id"], "expected": r["expected_category"], "predicted": r["predicted_category"]}
            for r in wrong
        ]

    print("\n" + "=" * 60)
    print("📊 평가 결과 요약")
    print("=" * 60)
    print(f"  카테고리 분류 정확도   : {summary['category_accuracy_pct']} ({cat_correct}/{total})")
    print(f"  검색 히트율 @{top_k}        : {summary['retrieval_hit_rate_pct']} ({hit_count}/{total})")
    print(f"  평균 키워드 커버리지   : {summary['avg_keyword_coverage_pct']}")
    print(f"  평균 응답 지연         : {summary['avg_latency_ms']}ms")

    if wrong:
        print(f"\n  ❌ 카테고리 오분류 ({len(wrong)}건):")
        for m in summary.get("misclassified", []):
            print(f"     {m['id']}: '{m['expected']}' → '{m['predicted']}'")

    return results, summary


# ── CLI 진입점 ────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="NuriNamu RAG 정확도 평가")
    parser.add_argument("--ids", nargs="*", help="평가할 케이스 ID (미지정 시 전체)")
    parser.add_argument("--top-k", type=int, default=3, help="검색 상위 K개 (기본값: 3)")
    parser.add_argument("--report", choices=["json", "none"], default="json", help="리포트 출력 형식")
    parser.add_argument("--quiet", action="store_true", help="케이스별 상세 출력 숨김")
    args = parser.parse_args()

    with open(DATASET_PATH, encoding="utf-8") as f:
        dataset = json.load(f)

    if args.ids:
        dataset = [c for c in dataset if c["id"] in args.ids]
        if not dataset:
            print(f"❌ 지정한 ID를 찾을 수 없습니다: {args.ids}")
            sys.exit(1)

    results, summary = asyncio.run(run_evaluation(dataset, top_k=args.top_k, verbose=not args.quiet))

    if args.report == "json":
        save_report(results, summary)


if __name__ == "__main__":
    main()
