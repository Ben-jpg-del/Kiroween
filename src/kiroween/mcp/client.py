"""MCP Client wrapper for Slack integration using langchain-mcp-adapters."""

import asyncio
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from kiroween.config import get_settings
from kiroween.utils.cache import get_cache
from kiroween.utils.errors import MCPConnectionError
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class SlackMCPManager:
    """Manages Slack MCP server connection and tools."""

    def __init__(self):
        self._client: MultiServerMCPClient | None = None
        self._tools: list[BaseTool] = []
        self._connected = False

    async def __aenter__(self) -> "SlackMCPManager":
        await self.connect()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Connect to Slack MCP server and load tools."""
        if self._connected:
            return

        settings = get_settings()

        try:
            # Connect to Redis cache first
            cache = get_cache()
            await cache.connect()

            logger.info("connecting_to_slack_mcp", transport=settings.slack_mcp_transport)

            config = self._build_config(settings)
            self._client = MultiServerMCPClient(config)
            raw_tools = await self._client.get_tools()

            # Wrap tools with caching if Redis is available
            if cache.is_connected:
                from kiroween.mcp.cached_tools import wrap_tools_with_cache

                self._tools = wrap_tools_with_cache(raw_tools)
                logger.info("tools_wrapped_with_cache", count=len(self._tools))
            else:
                self._tools = raw_tools
                logger.warning("redis_unavailable_using_uncached_tools")

            self._connected = True
            logger.info(
                "slack_mcp_connected",
                tools_count=len(self._tools),
                tool_names=[t.name for t in self._tools],
            )

            # Check if users/channels are already cached
            if cache.is_connected:
                from kiroween.mcp.cached_tools import _get_cache_key

                users_key = _get_cache_key("search_users", {"query": ""})
                channels_key = _get_cache_key("channels_list", {})

                users_cached = await cache.exists(users_key)
                channels_cached = await cache.exists(channels_key)

                if users_cached and channels_cached:
                    logger.info("using_cached_users_channels_skipping_wait")
                else:
                    # Wait for MCP server to finish caching, then prime our cache
                    logger.info("waiting_for_mcp_cache", wait_seconds=20)
                    await asyncio.sleep(20)

                    # Prime the Redis cache with users and channels
                    from kiroween.mcp.cached_tools import prime_user_channel_cache

                    await prime_user_channel_cache()
            else:
                # Fallback to original behavior if Redis unavailable
                logger.info("waiting_for_mcp_cache", wait_seconds=20)
                await asyncio.sleep(20)
                logger.info("mcp_cache_ready")

        except Exception as e:
            logger.error("slack_mcp_connection_failed", error=str(e))
            raise MCPConnectionError(f"Failed to connect to Slack MCP server: {e}") from e

    def _build_config(self, settings: Any) -> dict:
        """Build MCP client configuration based on settings."""
        if settings.slack_mcp_transport == "stdio":
            return {
                "slack": {
                    "command": "npx",
                    "args": ["-y", "slack-mcp-server"],
                    "transport": "stdio",
                    "env": {
                        "SLACK_MCP_XOXP_TOKEN": settings.slack_mcp_xoxp_token,
                        "SLACK_MCP_ADD_MESSAGE_TOOL": str(
                            settings.slack_mcp_add_message_tool
                        ).lower(),
                    },
                }
            }
        else:
            # For SSE or streamable_http transport
            return {
                "slack": {
                    "url": f"http://127.0.0.1:13080/mcp",
                    "transport": settings.slack_mcp_transport,
                }
            }

    async def disconnect(self) -> None:
        """Disconnect from MCP server and Redis cache."""
        if self._client and self._connected:
            # Disconnect from Redis
            cache = get_cache()
            await cache.disconnect()

            # Cleanup MCP connection
            self._connected = False
            self._tools = []
            logger.info("slack_mcp_disconnected")

    @property
    def tools(self) -> list[BaseTool]:
        """Get all available Slack MCP tools."""
        return self._tools

    @property
    def is_connected(self) -> bool:
        """Check if connected to MCP server."""
        return self._connected

    def get_tool_by_name(self, name: str) -> BaseTool | None:
        """Get a specific tool by name.

        Args:
            name: Tool name (e.g., 'conversations_history')

        Returns:
            The tool if found, None otherwise.
        """
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None

    def get_slack_tools(self) -> list[BaseTool]:
        """Get all Slack MCP tools.

        These typically include:
        - conversations_history: Fetch channel messages
        - conversations_replies: Fetch thread replies
        - conversations_search_messages: Search messages
        - channels_list: List/search channels
        - search_users: Search users
        - conversations_add_message: Send messages
        """
        return self._tools


# Global manager instance
_mcp_manager: SlackMCPManager | None = None


def get_mcp_manager() -> SlackMCPManager:
    """Get the global MCP manager instance."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = SlackMCPManager()
    return _mcp_manager
