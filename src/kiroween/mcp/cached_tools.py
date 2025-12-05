"""Cached MCP tool wrappers for reducing Slack API calls."""

import hashlib
import json
from typing import Any

from langchain_core.tools import BaseTool

from kiroween.utils.cache import get_cache
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


# Tools that should be cached
CACHEABLE_TOOLS = {
    "search_users",  # User lookups rarely change
    "channels_list",  # Channel lists rarely change
    "conversations_info",  # Channel info rarely changes
}

# Tools that should have shorter TTL
SHORT_TTL_TOOLS = {
    "conversations_history": 300,  # 5 minutes
    "conversations_replies": 300,  # 5 minutes
}


def _get_cache_key(tool_name: str, input_data: dict) -> str:
    """Generate cache key from tool name and input.

    Args:
        tool_name: Name of the tool
        input_data: Tool input parameters

    Returns:
        Cache key string
    """
    # Sort dict keys for consistent hashing
    sorted_input = json.dumps(input_data, sort_keys=True)
    input_hash = hashlib.sha256(sorted_input.encode()).hexdigest()[:16]
    return f"mcp:tool:{tool_name}:{input_hash}"


class CachedTool:
    """Wrapper for MCP tools with Redis caching."""

    def __init__(self, tool: BaseTool, cache_ttl: int | None = None):
        """Initialize cached tool wrapper.

        Args:
            tool: The original tool to wrap
            cache_ttl: Custom TTL for this tool (None = use default from settings)
        """
        self.tool = tool
        self.cache_ttl = cache_ttl
        self.cache = get_cache()

    @property
    def name(self) -> str:
        """Get tool name."""
        return self.tool.name

    @property
    def description(self) -> str:
        """Get tool description."""
        return self.tool.description

    async def ainvoke(self, input_data: dict) -> Any:
        """Invoke tool with caching.

        Args:
            input_data: Tool input parameters

        Returns:
            Tool result (from cache or fresh call)
        """
        # Check if this tool should be cached
        if not self._should_cache():
            logger.debug("tool_not_cacheable", tool=self.name)
            return await self.tool.ainvoke(input_data)

        # Try to get from cache
        cache_key = _get_cache_key(self.name, input_data)
        cached_result = await self.cache.get(cache_key)

        if cached_result is not None:
            logger.info("tool_cache_hit", tool=self.name, cache_key=cache_key)
            return cached_result

        # Cache miss - call the actual tool
        logger.info("tool_cache_miss", tool=self.name, cache_key=cache_key)
        result = await self.tool.ainvoke(input_data)

        # Cache the result
        ttl = self._get_ttl()
        await self.cache.set(cache_key, result, ttl=ttl)
        logger.debug("tool_result_cached", tool=self.name, ttl=ttl)

        return result

    def invoke(self, input_data: dict) -> Any:
        """Synchronous invoke (delegates to async)."""
        import asyncio

        return asyncio.run(self.ainvoke(input_data))

    def _should_cache(self) -> bool:
        """Check if this tool should be cached."""
        return self.name in CACHEABLE_TOOLS or self.name in SHORT_TTL_TOOLS

    def _get_ttl(self) -> int | None:
        """Get TTL for this tool."""
        if self.cache_ttl is not None:
            return self.cache_ttl
        if self.name in SHORT_TTL_TOOLS:
            return SHORT_TTL_TOOLS[self.name]
        return None  # Use default from settings


def wrap_tools_with_cache(tools: list[BaseTool]) -> list[CachedTool]:
    """Wrap all tools with caching.

    Args:
        tools: List of original tools

    Returns:
        List of cached tool wrappers
    """
    logger.info("wrapping_tools_with_cache", count=len(tools))
    return [CachedTool(tool) for tool in tools]


async def prime_user_channel_cache() -> None:
    """Prime the cache with users and channels on startup.

    This reduces the need for the 20-second MCP cache wait.
    """
    from kiroween.mcp.client import get_mcp_manager

    cache = get_cache()
    if not cache.is_connected:
        logger.warning("cache_not_connected_skipping_prime")
        return

    manager = get_mcp_manager()
    if not manager.is_connected:
        logger.warning("mcp_not_connected_skipping_prime")
        return

    logger.info("priming_user_channel_cache")

    try:
        # Get users list tool
        users_tool = manager.get_tool_by_name("search_users")
        if users_tool:
            # Fetch all users (empty query typically returns all)
            users_result = await users_tool.ainvoke({"query": ""})
            cache_key = _get_cache_key("search_users", {"query": ""})
            await cache.set(cache_key, users_result, ttl=86400)  # Cache for 24h
            logger.info("users_cached", cache_key=cache_key)

        # Get channels list tool
        channels_tool = manager.get_tool_by_name("channels_list")
        if channels_tool:
            # Fetch all channels
            channels_result = await channels_tool.ainvoke({})
            cache_key = _get_cache_key("channels_list", {})
            await cache.set(cache_key, channels_result, ttl=86400)  # Cache for 24h
            logger.info("channels_cached", cache_key=cache_key)

        logger.info("user_channel_cache_primed")

    except Exception as e:
        logger.warning("cache_priming_failed", error=str(e))
