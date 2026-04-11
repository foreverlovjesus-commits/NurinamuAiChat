import json
import os
import logging

logger = logging.getLogger(__name__)

class OntologyManager:
    """경량화된 사전(Dictionary) 기반 온톨로지 관리자.
    사용자 쿼리의 일상 용어를 법률 개념어로 자동 확장합니다.
    """
    def __init__(self, json_path="data/ontology_dict.json"):
        self.json_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), json_path))
        self.ontology = {}
        self.load()

    def load(self):
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, 'r', encoding='utf-8') as f:
                    self.ontology = json.load(f)
            except Exception as e:
                logger.error(f"온톨로지 파일 로드 실패: {e}")
                self.ontology = {}
        else:
            # 초기 기본 데이터
            self.ontology = {
                "학부모": ["직무관련자"],
                "학생": ["직무관련자"],
                "유치원 교사": ["공직자등", "교직원"],
                "선생님": ["공직자등", "교직원"],
                "스승의날": ["선물", "금품수수"]
            }
            self.save()

    def save(self):
        os.makedirs(os.path.dirname(self.json_path), exist_ok=True)
        with open(self.json_path, 'w', encoding='utf-8') as f:
            json.dump(self.ontology, f, ensure_ascii=False, indent=4)

    def add_entity(self, entity: str, concepts: list[str]):
        """엔티티와 매핑되는 개념 리스트 추가"""
        if not entity or not concepts:
            return
        
        # 중복 제거
        if entity in self.ontology:
            existing = set(self.ontology[entity])
            existing.update(concepts)
            self.ontology[entity] = list(existing)
        else:
            self.ontology[entity] = concepts
        self.save()

    def update_entity(self, old_entity: str, new_entity: str, concepts: list[str]):
        """엔티티 수정 (키 변경 및 밸류 변경)"""
        if old_entity in self.ontology and old_entity != new_entity:
            del self.ontology[old_entity]
        self.ontology[new_entity] = concepts
        self.save()

    def remove_entity(self, entity: str):
        """엔티티 삭제"""
        if entity in self.ontology:
            del self.ontology[entity]
            self.save()

    def expand_query(self, query: str) -> str:
        """
        주어진 원본 문자열에서 온톨로지 키워드를 찾아,
        매칭되는 법률 개념어들을 중복 없이 추출한 후 뒷부분에 추가합니다.
        
        예: "유치원 선생님께 학부모가" -> "유치원 선생님께 학부모가 공직자등 교직원 직무관련자"
        """
        if not query:
            return query
            
        expanded_concepts = set()
        for entity, concepts in self.ontology.items():
            if entity in query:
                for concept in concepts:
                    expanded_concepts.add(concept)
        
        if expanded_concepts:
            expansion_str = " ".join(expanded_concepts)
            return f"{query} {expansion_str}"
        return query
