"""Agent state definitions for LangGraph."""

from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages


class SlackFile(TypedDict):
    """Slack file attachment data."""

    id: str
    name: str
    mimetype: str
    url_private: str
    size: int


class SlackMessage(TypedDict):
    """Structured Slack message data."""

    channel_id: str
    thread_ts: str | None
    user_id: str
    user_name: str
    text: str
    timestamp: str
    reactions: list[str]
    files: list[SlackFile]


class AgendaItemData(TypedDict):
    """Agenda/task item structure."""

    id: str
    type: Literal["task", "decision", "obligation", "question", "action_item"]
    title: str
    description: str | None
    status: Literal["open", "in_progress", "completed", "deferred"]
    source_channel: str | None
    source_thread_ts: str | None
    assigned_to: str | None
    priority: int


class IntentData(TypedDict):
    """Parsed intent data from router."""

    intent: str
    channel: str | None
    time_range: str | None
    search_query: str | None
    thread_url: str | None
    user_name: str | None


Intent = Literal[
    "summarize_missed",
    "search_previous",
    "track_obligations",
    "extract_decisions",
    "send_message",
    "general_query",
    "vision_catchup",
]


class AgentState(TypedDict):
    """Complete agent state for LangGraph.

    This state is passed through all nodes in the graph and contains
    all data needed for processing user requests.
    """

    # Conversation history (uses add_messages reducer for append)
    messages: Annotated[list[BaseMessage], add_messages]

    # User intent classification
    intent: Intent | None

    # Parsed parameters from user request
    target_channel: str | None
    target_thread_ts: str | None
    time_range: str | None
    search_query: str | None
    target_user: str | None

    # Retrieved Slack data
    slack_messages: list[SlackMessage]
    slack_threads: list[dict]

    # Agenda engine data
    agenda_items: list[AgendaItemData]
    pending_agenda_updates: list[AgendaItemData]

    # Processing output
    response: str | None
    error: str | None

    # Vision processing output
    vision_summary: dict | None


def create_initial_state() -> AgentState:
    """Create an initial empty agent state."""
    return {
        "messages": [],
        "intent": None,
        "target_channel": None,
        "target_thread_ts": None,
        "time_range": None,
        "search_query": None,
        "target_user": None,
        "slack_messages": [],
        "slack_threads": [],
        "agenda_items": [],
        "pending_agenda_updates": [],
        "response": None,
        "error": None,
        "vision_summary": None,
    }
