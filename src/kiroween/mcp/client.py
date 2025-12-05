"""MCP Client wrapper for Slack integration using langchain-mcp-adapters."""

import asyncio
from typing import Any

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from kiroween.config import get_settings
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
            logger.info("connecting_to_slack_mcp", transport=settings.slack_mcp_transport)

            config = self._build_config(settings)
            self._client = MultiServerMCPClient(config)
            self._tools = await self._client.get_tools()

            self._connected = True
            logger.info(
                "slack_mcp_connected",
                tools_count=len(self._tools),
                tool_names=[t.name for t in self._tools],
            )

            # Wait for MCP server to finish caching users and channels
            logger.info("waiting_for_mcp_cache", wait_seconds=8)
            await asyncio.sleep(8)
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
        """Disconnect from MCP server."""
        if self._client and self._connected:
            # Cleanup if needed
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
