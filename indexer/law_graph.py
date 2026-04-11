"""
법률 관계 그래프 모듈 — 법률 간 참조·준용 관계를 자동 추출하여 JSON 그래프로 저장

기능:
  1. PDF 법령 문서에서 「타법명」 참조, 준용 조항을 정규식으로 추출
  2. 법률 간 관계(참조/준용/위임)를 그래프 구조로 저장
  3. 검색 시 관련 법률 청크를 추가 검색하는 데 활용
"""
import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRAPH_PATH = os.path.join(_PROJECT_ROOT, "logs", "law_graph.json")


def extract_references_from_text(text: str, source_law: str) -> list[dict]:
    """법률 텍스트에서 다른 법률 참조·준용 관계를 추출한다.

    Returns:
        list of {source, target, relation, article, detail}
    """
    relations = []
    lines = text.split("\n")

    # 「법률명」 패턴으로 참조 대상 추출
    ref_pattern = re.compile(r'「([^」]{2,50})」')
    # 준용 패턴
    junyong_pattern = re.compile(r'(제\d+조(?:의\d+)?(?:부터)?\s*(?:제\d+조(?:의\d+)?까지)?[^.]*준용)')
    # 조문 번호 (현재 위치 추적용)
    article_pattern = re.compile(r'^(?:##\s*)?(제\s*\d+\s*조(?:의\d+)?(?:\s*\([^)]*\))?)')

    current_article = ""

    for line in lines:
        # 현재 조문 추적
        art_match = article_pattern.match(line.strip())
        if art_match:
            current_article = art_match.group(1).strip()

        # 1) 「법률명」 참조 추출
        for match in ref_pattern.finditer(line):
            target_law = match.group(1).strip()
            # 자기 참조 제외
            if target_law == source_law:
                continue
            # 노이즈 필터: 너무 짧거나 법률명이 아닌 것
            if len(target_law) < 3:
                continue

            relation_type = "reference"
            # 준용 여부 판별
            if "준용" in line:
                relation_type = "준용"
            elif "위임" in line or "대통령령" in line:
                relation_type = "위임"

            relations.append({
                "source": source_law,
                "target": target_law,
                "relation": relation_type,
                "article": current_article,
                "detail": line.strip()[:200],
            })

        # 2) 내부 조문 간 준용 (같은 법 안에서)
        if "준용" in line and "「" not in line:
            junyong_match = junyong_pattern.search(line)
            if junyong_match:
                relations.append({
                    "source": source_law,
                    "target": source_law,
                    "relation": "내부준용",
                    "article": current_article,
                    "detail": junyong_match.group(0)[:200],
                })

    return relations


def build_graph_from_directory(doc_dir: str) -> dict:
    """doc_archive/법령/ 폴더의 PDF에서 법률 관계 그래프를 구축한다.

    Returns:
        {
            "nodes": [{"id": "청탁금지법", "full_name": "부정청탁 및 ...", "file": "...pdf"}],
            "edges": [{"source": ..., "target": ..., "relation": ..., ...}],
        }
    """
    law_dir = os.path.join(doc_dir, "법령")
    if not os.path.isdir(law_dir):
        logger.warning(f"법령 폴더 없음: {law_dir}")
        return {"nodes": [], "edges": []}

    nodes = []
    all_edges = []

    for fname in sorted(os.listdir(law_dir)):
        if not (fname.endswith(".pdf") or fname.endswith(".md")):
            continue
        fpath = os.path.join(law_dir, fname)
        # 법률 약칭 추출
        short_name = fname.replace("_전문.md", "").split("(")[0].strip()
        full_name = short_name

        # 약칭 매핑 (표시용)
        abbreviations = {
            "부정청탁 및 금품등 수수의 금지에 관한 법률": "청탁금지법",
            "공직자의 이해충돌 방지법": "이해충돌방지법",
            "공익신고자 보호법": "공익신고자보호법",
            "공공재정 부정청구 금지 및 부정이익 환수 등에 관한 법률": "공공재정환수법",
            "부패방지 및 국민권익위원회의 설치와 운영에 관한 법률": "부패방지법",
            "행정심판법": "행정심판법",
            "공무원 행동강령": "공무원행동강령",
        }
        display_name = short_name
        for full, abbr in abbreviations.items():
            if full in short_name:
                display_name = abbr
                break

        nodes.append({
            "id": display_name,
            "full_name": full_name,
            "file": fname,
        })

        text = ""
        if fname.endswith(".md"):
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
        elif fname.endswith(".pdf"):
            # PDF 텍스트 추출
            try:
                import pdfplumber
                with pdfplumber.open(fpath) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            text += t + "\n"
            except ImportError:
                logger.warning("pdfplumber 미설치, 법률 그래프 구축 건너뜀")
                continue
            except Exception as e:
                logger.warning(f"PDF 읽기 실패 ({fname}): {e}")
                continue

        edges = extract_references_from_text(text, display_name)
        all_edges.extend(edges)

    # 엣지 중복 제거 (source+target+relation+article 기준)
    seen = set()
    unique_edges = []
    for edge in all_edges:
        key = (edge["source"], edge["target"], edge["relation"], edge["article"])
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)

    graph = {"nodes": nodes, "edges": unique_edges}
    logger.info(f"법률 그래프 구축 완료: {len(nodes)}개 법률, {len(unique_edges)}개 관계")
    return graph


def save_graph(graph: dict, path: str = GRAPH_PATH):
    """그래프를 JSON 파일로 저장"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(graph, f, ensure_ascii=False, indent=2)
    logger.info(f"법률 그래프 저장: {path}")


def load_graph(path: str = GRAPH_PATH) -> dict:
    """저장된 그래프 로드. 없으면 빈 그래프 반환."""
    if not os.path.exists(path):
        return {"nodes": [], "edges": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_related_laws(graph: dict, law_name: str) -> list[str]:
    """특정 법률과 참조·준용 관계가 있는 법률 목록을 반환한다.

    양방향 탐색: source→target, target→source 모두 포함.
    """
    related = set()
    for edge in graph.get("edges", []):
        if edge["source"] == law_name and edge["target"] != law_name:
            related.add(edge["target"])
        if edge["target"] == law_name and edge["source"] != law_name:
            related.add(edge["source"])
    return list(related)


def find_junyong_articles(graph: dict, law_name: str) -> list[dict]:
    """특정 법률의 준용 조항들을 반환한다."""
    results = []
    for edge in graph.get("edges", []):
        if edge["source"] == law_name and edge["relation"] in ("준용", "내부준용"):
            results.append(edge)
    return results


if __name__ == "__main__":
    """단독 실행: 법률 관계 그래프 구축 및 출력"""
    logging.basicConfig(level=logging.INFO)
    doc_dir = os.path.join(_PROJECT_ROOT, os.getenv("DOC_ARCHIVE_DIR", "doc_archive"))
    graph = build_graph_from_directory(doc_dir)
    save_graph(graph)

    print(f"\n=== 법률 관계 그래프 요약 ===")
    print(f"법률 수: {len(graph['nodes'])}")
    print(f"관계 수: {len(graph['edges'])}")

    for node in graph["nodes"]:
        related = find_related_laws(graph, node["id"])
        junyong = find_junyong_articles(graph, node["id"])
        print(f"\n📜 {node['id']}")
        print(f"   관련 법률: {', '.join(related) if related else '없음'}")
        print(f"   준용 조항: {len(junyong)}건")
