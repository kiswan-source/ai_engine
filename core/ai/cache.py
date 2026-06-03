"""Redis-backed cache for AI responses."""
import json
from typing import Optional

import redis.asyncio as aioredis

from api.config import settings
from core.utils.logger import get_logger

logger = get_logger(__name__)

_pool: Optional[aioredis.ConnectionPool] = None


def get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        _pool = aioredis.ConnectionPool.from_url(
            settings.REDIS_URL, decode_responses=True
        )
    return _pool


class AICache:
    PREFIX = "ai_cache:"

    def _client(self) -> aioredis.Redis:
        return aioredis.Redis(connection_pool=get_pool())

    async def get(self, key: str) -> Optional[str]:
        try:
            async with self._client() as r:
                value = await r.get(f"{self.PREFIX}{key}")
                return value
        except Exception as e:
            logger.warning("Cache get failed", error=str(e))
            return None

    async def set(self, key: str, value: str, ttl: int = 3600) -> bool:
        try:
            async with self._client() as r:
                await r.setex(f"{self.PREFIX}{key}", ttl, value)
                return True
        except Exception as e:
            logger.warning("Cache set failed", error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        try:
            async with self._client() as r:
                await r.delete(f"{self.PREFIX}{key}")
                return True
        except Exception as e:
            logger.warning("Cache delete failed", error=str(e))
            return False

    async def flush_pattern(self, pattern: str) -> int:
        try:
            async with self._client() as r:
                keys = await r.keys(f"{self.PREFIX}{pattern}*")
                if keys:
                    return await r.delete(*keys)
                return 0
        except Exception as e:
            logger.warning("Cache flush failed", error=str(e))
            return 0
