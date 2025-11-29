"""Searcher node for message search and retrieval."""

from kiroween.agent.state import AgentState
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


async def searcher_node(state: AgentState) -> dict:
    """Prepare for message search.

    This node sets up the context for searching previous discussions
    and answers in Slack.

    Returns:
        Dict with search parameters.
    """
    search_query = state.get("search_query")
    channel = state.get("target_channel")

    logger.info(
        "searcher_preparing",
        query=search_query,
        channel=channel,
    )

    # The responder will use conversations_search_messages tool
    return {
        "slack_messages": [],
    }
