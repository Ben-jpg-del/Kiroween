"""Extractor node for decision and task extraction from threads."""

from kiroween.agent.state import AgentState
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


async def extractor_node(state: AgentState) -> dict:
    """Prepare for decision/task extraction from a thread.

    This node sets up the context for extracting tasks and decisions
    from a Slack thread.

    Returns:
        Dict with extraction parameters.
    """
    thread_ts = state.get("target_thread_ts")
    channel = state.get("target_channel")

    logger.info(
        "extractor_preparing",
        thread_ts=thread_ts,
        channel=channel,
    )

    # The responder will:
    # 1. Use conversations_replies to get thread content
    # 2. Extract decisions and tasks using LLM
    # 3. Save them using agenda_db_upsert_item
    return {
        "slack_threads": [],
        "pending_agenda_updates": [],
    }
