"""Router node for intent classification."""

import json

from langchain_core.messages import HumanMessage

from kiroween.agent.state import AgentState
from kiroween.llm.prompts import ROUTER_PROMPT
from kiroween.llm.provider import get_llm
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


async def router_node(state: AgentState) -> dict:
    """Classify user intent and extract parameters.

    This node analyzes the user's message to determine:
    - What type of action they want (summarize, search, track, etc.)
    - Relevant parameters (channel, time range, search query, etc.)

    Returns:
        Dict with intent and extracted parameters.
    """
    # Get the last user message
    messages = state.get("messages", [])
    if not messages:
        logger.warning("router_no_messages")
        return {"intent": "general_query"}

    last_message = messages[-1]
    if not isinstance(last_message, HumanMessage):
        # If last message is not from user, treat as general query
        return {"intent": "general_query"}

    user_input = last_message.content

    logger.info("router_classifying", input_preview=user_input[:100])

    try:
        llm = get_llm()

        response = await llm.ainvoke([
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": user_input},
        ])

        # Parse the response
        content = response.content
        if isinstance(content, str):
            # Try to extract JSON from the response
            try:
                # Handle case where model wraps JSON in markdown code block
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]

                parsed = json.loads(content.strip())
            except json.JSONDecodeError:
                # If parsing fails, default to general_query
                logger.warning("router_parse_failed", content=content[:200])
                parsed = {"intent": "general_query"}
        else:
            parsed = {"intent": "general_query"}

        intent = parsed.get("intent", "general_query")
        logger.info(
            "router_classified",
            intent=intent,
            channel=parsed.get("channel"),
            time_range=parsed.get("time_range"),
        )

        return {
            "intent": intent,
            "target_channel": parsed.get("channel"),
            "time_range": parsed.get("time_range"),
            "search_query": parsed.get("search_query"),
            "target_thread_ts": parsed.get("thread_url"),  # Will need parsing
            "target_user": parsed.get("user_name"),
        }

    except Exception as e:
        logger.error("router_error", error=str(e))
        return {"intent": "general_query", "error": str(e)}
