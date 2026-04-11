import os
import json
import logging
import asyncpg
from datetime import datetime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class AsyncDBManager:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.pool = None

    async def connect(self):
        if not self.pool:
            # 💡 윈도우 환경(한글 경로)에서의 인코딩 에러 방지: DSN 문자열 대신 개별 파라미터 전달
            import re
            pattern = r"postgresql://(?P<user>[^:]+):(?P<password>[^@]+)@(?P<host>[^:/]+):(?P<port>\d+)/(?P<database>.+)"
            match = re.match(pattern, self.db_url)
            
            if match:
                params = match.groupdict()
                self.pool = await asyncpg.create_pool(
                    user=params['user'],
                    password=params['password'],
                    host=params['host'],
                    port=int(params['port']),
                    database=params['database'],
                    min_size=1,
                    max_size=10,
                    ssl=False
                )
            else:
                # 룩업 실패 시 원래 방식 시도 (폴백)
                self.pool = await asyncpg.create_pool(self.db_url, min_size=1, max_size=10, ssl=False)
                
            logger.info("✅ Async DB Pool initialized (Manual Params Mode)")

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def get_or_create_session(self, session_id: str):
        async with self.pool.acquire() as conn:
            # upsert session
            row = await conn.fetchrow("""
                INSERT INTO chat_sessions (session_id)
                VALUES ($1)
                ON CONFLICT (session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                RETURNING id
            """, session_id)
            return row['id']

    async def save_message(self, session_id: str, role: str, content: str, 
                         category: str = None, sources: List[str] = None, latency_ms: int = None):
        session_uuid = await self.get_or_create_session(session_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO chat_messages (session_uuid, role, content, category, sources, latency_ms)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """, session_uuid, role, content, category, json.dumps(sources) if sources else None, latency_ms)
            return row['id']

    async def get_history(self, session_id: str, limit: int = 50):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT m.role, m.content, m.category, m.sources, m.timestamp
                FROM chat_messages m
                JOIN chat_sessions s ON m.session_uuid = s.id
                WHERE s.session_id = $1
                ORDER BY m.timestamp ASC
                LIMIT $2
            """, session_id, limit)
            
            history = []
            for r in rows:
                history.append({
                    "role": r['role'],
                    "content": r['content'],
                    "category": r['category'],
                    "sources": json.loads(r['sources']) if r['sources'] else [],
                    "timestamp": r['timestamp'].isoformat()
                })
            return history

    async def save_feedback(self, session_id: str, message_index: int, rating: int, comment: str = None):
        # Note: This is a simplified logic. In production, we'd use message_id directly
        # For Day 2, we fetch the message_id by offset
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT m.id
                FROM chat_messages m
                JOIN chat_sessions s ON m.session_uuid = s.id
                WHERE s.session_id = $1
                ORDER BY m.timestamp ASC
                OFFSET $2 LIMIT 1
            """, session_id, message_index)
            
            if row:
                await conn.execute("""
                    INSERT INTO chat_feedback (message_id, rating, comment)
                    VALUES ($1, $2, $3)
                """, row['id'], rating, comment)
                return True
            return False

    async def get_all_sessions(self, limit: int = 20):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT session_id, updated_at
                FROM chat_sessions
                ORDER BY updated_at DESC
                LIMIT $1
            """, limit)
            return [{"session_id": r['session_id'], "updated_at": r['updated_at'].isoformat()} for r in rows]

    async def save_audit_log(self, action: str, details: str, ip_address: str = None):
        """보안/감사 로그를 데이터베이스에 안전하게 저장합니다."""
        if not self.pool:
            return False
            
        try:
            async with self.pool.acquire() as conn:
                # audit_logs 테이블이 존재하는지 확인 (Day 3 보안 과제 시 생성됨)
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'audit_logs'
                    );
                """)
                if table_exists:
                    await conn.execute("""
                        INSERT INTO audit_logs (action, details, ip_address, timestamp)
                        VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                    """, action, details, ip_address)
                return True
        except Exception as e:
            logger.warning(f"감사 로그 DB 기록 실패: {e}")
            return False

