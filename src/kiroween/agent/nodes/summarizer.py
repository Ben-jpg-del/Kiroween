"""Summarizer node for message summarization."""

from kiroween.agent.state import AgentState
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


async def summarizer_node(state: AgentState) -> dict:
    """Prepare for message summarization.

    This node sets up the context for the responder to fetch
    and summarize messages from a channel.

    The actual Slack API calls are made by the responder node
    using the MCP tools, allowing for proper tool calling flow.

    Returns:
        Dict with any additional context needed.
    """
    channel = state.get("target_channel")
    time_range = state.get("time_range", "1d")

    logger.info(
        "summarizer_preparing",
        channel=channel,
        time_range=time_range,
    )

    # The responder will use this context to make appropriate tool calls
    # We could add preprocessing here if needed (e.g., resolve channel name to ID)

    return {
        "slack_messages": [],  # Will be populated by tool calls
        "slack_threads": [],
    }
