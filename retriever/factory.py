import logging
import os
from .advanced_retriever import AdvancedHybridRetrieverV2

logger = logging.getLogger(__name__)

def get_retriever(db_url: str):
    """
    환경 설정(RETRIEVER_TYPE)에 따라 적절한 리트리버 객체를 반환합니다.
    """
    # 기본값은 항상 현재 검증된 pgvector 시스템입니다.
    retriever_type = os.getenv("RETRIEVER_TYPE", "pgvector").lower()

    # [미래 확장용 주석] 🚀 OpenSearch + Qdrant 도입 시 아래 주석을 해제하고 로직을 구현합니다.
    """
    if retriever_type == "ensemble":
        # from .ensemble_retriever import AdvancedEnsembleRetriever
        # return AdvancedEnsembleRetriever(db_url)
        pass
    """

    # 현재 활성화된 고성능 PGVector 하이브리드 검색기 반환
    logger.info("[Architecture] 현재 검색 엔진 모드: %s", retriever_type.upper())
    return AdvancedHybridRetrieverV2(db_url)
