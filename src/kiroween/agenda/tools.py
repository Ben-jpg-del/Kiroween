"""LangChain tools for agenda operations."""

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from kiroween.agenda.service import get_agenda_service
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class AgendaUpsertInput(BaseModel):
    """Input schema for upserting an agenda item."""

    item_type: str = Field(
        ...,
        description="Type of item: task, decision, obligation, question, or action_item",
    )
    title: str = Field(..., description="Brief title of the item (max 500 chars)")
    description: str | None = Field(None, description="Detailed description")
    status: str = Field(
        default="open",
        description="Status: open, in_progress, completed, or deferred",
    )
    item_id: str | None = Field(
        None, description="Item ID for updates. Leave empty for new items."
    )
    assigned_to_user_id: str | None = Field(
        None, description="Slack user ID of the assignee"
    )
    assigned_to_user_name: str | None = Field(
        None, description="Display name of the assignee"
    )
    source_channel_id: str | None = Field(
        None, description="Source Slack channel ID"
    )
    source_thread_ts: str | None = Field(
        None, description="Source thread timestamp"
    )
    priority: int = Field(
        default=0, description="Priority: 0=normal, 1=high, 2=urgent"
    )


class AgendaSearchInput(BaseModel):
    """Input schema for searching agenda items."""

    query: str | None = Field(None, description="Text search in title/description")
    item_type: str | None = Field(
        None,
        description="Filter by type: task, decision, obligation, question, action_item",
    )
    status: str | None = Field(
        None,
        description="Filter by status: open, in_progress, completed, deferred",
    )
    assigned_to: str | None = Field(None, description="Filter by assignee's Slack user ID")
    channel_id: str | None = Field(None, description="Filter by source Slack channel ID")
    limit: int = Field(default=20, description="Maximum number of results (1-50)")


@tool(args_schema=AgendaUpsertInput)
async def agenda_db_upsert_item(
    item_type: str,
    title: str,
    description: str | None = None,
    status: str = "open",
    item_id: str | None = None,
    assigned_to_user_id: str | None = None,
    assigned_to_user_name: str | None = None,
    source_channel_id: str | None = None,
    source_thread_ts: str | None = None,
    priority: int = 0,
) -> str:
    """Create or update an agenda item (task, decision, obligation, etc.).

    Use this tool to:
    - Track action items extracted from Slack conversations
    - Record decisions made in threads
    - Create obligations and tasks assigned to users
    - Update existing items with new status or details

    Returns a confirmation message with the item ID.
    """
    service = get_agenda_service()

    try:
        item = await service.upsert_item(
            item_type=item_type,
            title=title,
            description=description,
            status=status,
            item_id=item_id,
            assigned_to_user_id=assigned_to_user_id,
            assigned_to_user_name=assigned_to_user_name,
            source_channel_id=source_channel_id,
            source_thread_ts=source_thread_ts,
            priority=priority,
        )

        action = "Updated" if item_id else "Created"
        logger.info(
            "agenda_tool_upsert",
            action=action.lower(),
            item_id=item.id,
            item_type=item_type,
        )

        return (
            f"{action} {item_type}: '{item.title}'\n"
            f"ID: {item.id}\n"
            f"Status: {item.status.value}\n"
            f"Priority: {'urgent' if priority == 2 else 'high' if priority == 1 else 'normal'}"
        )

    except Exception as e:
        logger.error("agenda_tool_upsert_error", error=str(e))
        return f"Error creating/updating agenda item: {e}"


@tool(args_schema=AgendaSearchInput)
async def agenda_db_search(
    query: str | None = None,
    item_type: str | None = None,
    status: str | None = None,
    assigned_to: str | None = None,
    channel_id: str | None = None,
    limit: int = 20,
) -> str:
    """Search agenda items by various criteria.

    Use this tool to:
    - Find existing tasks, decisions, and obligations
    - Look up items assigned to a specific user
    - Filter items by status or type
    - Search for items from a specific Slack channel

    Returns a formatted list of matching items.
    """
    service = get_agenda_service()

    try:
        items = await service.search_items(
            query=query,
            item_type=item_type,
            status=status,
            assigned_to=assigned_to,
            channel_id=channel_id,
            limit=min(limit, 50),
        )

        logger.info(
            "agenda_tool_search",
            query=query,
            item_type=item_type,
            status=status,
            results_count=len(items),
        )

        if not items:
            return "No agenda items found matching the criteria."

        results = []
        for item in items:
            status_emoji = {
                "open": "📋",
                "in_progress": "🔄",
                "completed": "✅",
                "deferred": "⏸️",
                "cancelled": "❌",
            }.get(item.status.value, "📋")

            priority_str = ""
            if item.priority == 2:
                priority_str = " 🔴 URGENT"
            elif item.priority == 1:
                priority_str = " 🟡 HIGH"

            assignee = f" → {item.assigned_to_user_name}" if item.assigned_to_user_name else ""

            results.append(
                f"{status_emoji} [{item.type.value.upper()}] {item.title}{priority_str}{assignee}\n"
                f"   ID: {item.id} | Status: {item.status.value}"
            )

        return f"Found {len(items)} item(s):\n\n" + "\n\n".join(results)

    except Exception as e:
        logger.error("agenda_tool_search_error", error=str(e))
        return f"Error searching agenda items: {e}"


def get_agenda_tools() -> list:
    """Get all agenda-related tools."""
    return [agenda_db_upsert_item, agenda_db_search]
