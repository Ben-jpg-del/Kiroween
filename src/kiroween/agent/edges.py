"""Conditional edge logic for the LangGraph agent."""

from kiroween.agent.state import AgentState
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


def route_by_intent(state: AgentState) -> str:
    """Route to appropriate node based on classified intent.

    Args:
        state: Current agent state with intent field.

    Returns:
        Name of the next node to execute.
    """
    intent = state.get("intent")

    logger.debug("routing_by_intent", intent=intent)

    if intent == "summarize_missed":
        return "summarizer"
    elif intent == "search_previous":
        return "searcher"
    elif intent == "track_obligations":
        return "tracker"
    elif intent == "extract_decisions":
        return "extractor"
    else:
        # For send_message and general_query, go directly to responder
        return "responder"


def should_continue(state: AgentState) -> str:
    """Determine if the agent should continue or finish.

    This edge is used after tool execution to decide if
    more processing is needed.

    Args:
        state: Current agent state.

    Returns:
        "continue" to go back to responder, "end" to finish.
    """
    messages = state.get("messages", [])

    if not messages:
        return "end"

    last_message = messages[-1]

    # Check if last message has tool calls
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"

    return "end"
