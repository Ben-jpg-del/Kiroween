"""Responder node for generating final responses."""

from langchain_core.messages import AIMessage, SystemMessage

from kiroween.agent.state import AgentState
from kiroween.config import get_settings
from kiroween.llm.prompts import SYSTEM_PROMPT
from kiroween.llm.provider import get_llm_with_tools
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


async def responder_node(state: AgentState, tools: list) -> dict:
    """Generate response using LLM with tools.

    This node is the main reasoning engine that:
    - Uses the system prompt for context
    - Can call Slack MCP tools and agenda tools
    - Generates the final response to the user

    Args:
        state: Current agent state
        tools: List of available tools (Slack MCP + Agenda)

    Returns:
        Dict with updated messages.
    """
    intent = state.get("intent", "general_query")
    messages = state.get("messages", [])

    logger.info(
        "responder_generating",
        intent=intent,
        message_count=len(messages),
    )

    # Build context based on intent
    settings = get_settings()
    context_parts = [SYSTEM_PROMPT]

    # Add user context if available
    if settings.slack_user_id:
        context_parts.append(
            f"\nCurrent user ID: {settings.slack_user_id}"
            f"\nWhen the user says 'me' or 'my tasks', use this user ID: {settings.slack_user_id}"
        )

    if intent == "summarize_missed":
        channel = state.get("target_channel", "the channel")
        time_range = state.get("time_range", "recent")
        context_parts.append(
            f"\nUser wants to summarize messages from {channel} ({time_range}). "
            "Use conversations_history to fetch messages, then provide a clear summary."
        )
    elif intent == "search_previous":
        query = state.get("search_query", "")
        context_parts.append(
            f"\nUser is searching for: '{query}'. "
            "Use conversations_search_messages to find relevant discussions."
        )
    elif intent == "track_obligations":
        user = state.get("target_user")
        if user:
            context_parts.append(
                f"\nUser wants to track obligations with {user}. "
                "Use agenda_db_search to find existing items."
            )
        else:
            context_parts.append(
                "\nUser wants to see their tasks and obligations. "
                "Use agenda_db_search to find open items."
            )
    elif intent == "extract_decisions":
        context_parts.append(
            "\nUser wants to extract decisions and tasks from a thread. "
            "Use conversations_replies to get thread content, then extract and save items."
        )

    system_message = SystemMessage(content="\n".join(context_parts))

    # Prepare messages for LLM
    llm_messages = [system_message] + list(messages)

    try:
        llm = get_llm_with_tools(tools)
        response = await llm.ainvoke(llm_messages)

        logger.info(
            "responder_generated",
            has_tool_calls=bool(response.tool_calls) if hasattr(response, "tool_calls") else False,
        )

        return {"messages": [response]}

    except Exception as e:
        logger.error("responder_error", error=str(e))
        error_message = AIMessage(
            content=f"I encountered an error while processing your request: {e}"
        )
        return {"messages": [error_message], "error": str(e)}


def create_responder_node(tools: list):
    """Create a responder node with tools bound.

    Args:
        tools: List of available tools.

    Returns:
        Async function that can be used as a LangGraph node.
    """

    async def _responder(state: AgentState) -> dict:
        return await responder_node(state, tools)

    return _responder
