"""Redis cache utilities for caching MCP tool results and Slack data."""

import asyncio
import json
from typing import Any

import redis.asyncio as redis
from redis.asyncio import Redis

from kiroween.config import get_settings
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class RedisCache:
    """Async Redis cache manager for Slack MCP data."""

    def __init__(self):
        self._client: Redis | None = None
        self._connected = False

    async def connect(self) -> None:
        """Connect to Redis server."""
        if self._connected:
            return

        settings = get_settings()

        try:
            logger.info(
                "connecting_to_redis",
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
            )

            self._client = await redis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                db=settings.redis_db,
                password=settings.redis_password,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )

            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info("redis_connected")

        except Exception as e:
            logger.warning("redis_connection_failed", error=str(e))
            # Don't fail the app if Redis is unavailable
            self._connected = False
            self._client = None

    async def disconnect(self) -> None:
        """Disconnect from Redis server."""
        if self._client and self._connected:
            await self._client.aclose()
            self._connected = False
            self._client = None
            logger.info("redis_disconnected")

    async def get(self, key: str) -> Any | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if not self._connected or not self._client:
            return None

        try:
            value = await self._client.get(key)
            if value:
                logger.debug("cache_hit", key=key)
                return json.loads(value)
            logger.debug("cache_miss", key=key)
            return None
        except Exception as e:
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    async def set(
        self, key: str, value: Any, ttl: int | None = None, nx: bool = False
    ) -> bool:
        """Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (uses default from settings if not provided)
            nx: Only set if key doesn't exist

        Returns:
            True if set successfully, False otherwise
        """
        if not self._connected or not self._client:
            return False

        settings = get_settings()
        ttl = ttl or settings.redis_ttl

        try:
            serialized = json.dumps(value)
            result = await self._client.set(key, serialized, ex=ttl, nx=nx)
            logger.debug("cache_set", key=key, ttl=ttl, nx=nx, success=bool(result))
            return bool(result)
        except Exception as e:
            logger.warning("cache_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if deleted, False otherwise
        """
        if not self._connected or not self._client:
            return False

        try:
            result = await self._client.delete(key)
            logger.debug("cache_delete", key=key, deleted=bool(result))
            return bool(result)
        except Exception as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        if not self._connected or not self._client:
            return False

        try:
            result = await self._client.exists(key)
            return bool(result)
        except Exception as e:
            logger.warning("cache_exists_failed", key=key, error=str(e))
            return False

    async def get_many(self, keys: list[str]) -> dict[str, Any]:
        """Get multiple values from cache.

        Args:
            keys: List of cache keys

        Returns:
            Dictionary of key -> value for keys that exist
        """
        if not self._connected or not self._client or not keys:
            return {}

        try:
            values = await self._client.mget(keys)
            result = {}
            for key, value in zip(keys, values):
                if value:
                    result[key] = json.loads(value)
            logger.debug("cache_get_many", requested=len(keys), found=len(result))
            return result
        except Exception as e:
            logger.warning("cache_get_many_failed", error=str(e))
            return {}

    async def set_many(self, items: dict[str, Any], ttl: int | None = None) -> bool:
        """Set multiple values in cache.

        Args:
            items: Dictionary of key -> value to cache
            ttl: Time to live in seconds (uses default from settings if not provided)

        Returns:
            True if all set successfully, False otherwise
        """
        if not self._connected or not self._client or not items:
            return False

        settings = get_settings()
        ttl = ttl or settings.redis_ttl

        try:
            # Use pipeline for efficiency
            async with self._client.pipeline() as pipe:
                for key, value in items.items():
                    serialized = json.dumps(value)
                    pipe.set(key, serialized, ex=ttl)
                await pipe.execute()

            logger.debug("cache_set_many", count=len(items), ttl=ttl)
            return True
        except Exception as e:
            logger.warning("cache_set_many_failed", error=str(e))
            return False

    @property
    def is_connected(self) -> bool:
        """Check if connected to Redis."""
        return self._connected


# Global cache instance
_cache: RedisCache | None = None


def get_cache() -> RedisCache:
    """Get the global cache instance."""
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache
