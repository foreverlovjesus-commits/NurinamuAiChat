"""
법령 데이터 인덱싱 백그라운드 스케줄러.
일정 주기마다 law_indexer.py를 실행하여 벡터 DB의 법령을 최신화합니다.
"""
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

# 프로젝트 루트 경로 추가
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

from indexer.law_indexer import main as run_indexer

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 실행 주기 (초) - 기본값: 7일 (7 * 24 * 60 * 60)
INTERVAL_SECONDS = 7 * 24 * 60 * 60

async def schedule_loop():
    logger.info(f"🚀 법령 인덱서 백그라운드 스케줄러 가동 (주기: {INTERVAL_SECONDS / 86400}일)")
    
    while True:
        start_time = datetime.now()
        logger.info("배치 실행: 법령 데이터 동기화 시작")
        
        try:
            await run_indexer()
            logger.info("배치 완료: 법령 데이터 동기화 성공")
        except Exception as e:
            logger.error(f"배치 실패: {e}", exc_info=True)
            
        next_run = start_time + timedelta(seconds=INTERVAL_SECONDS)
        logger.info(f"다음 실행 예정 시간: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 다음 실행 시간까지 대기
        await asyncio.sleep(INTERVAL_SECONDS)

if __name__ == "__main__":
    try:
        asyncio.run(schedule_loop())
    except KeyboardInterrupt:
        logger.info("🛑 스케줄러가 종료되었습니다.")