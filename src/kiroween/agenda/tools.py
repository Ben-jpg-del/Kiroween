"""LangChain tools for agenda operations."""

from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from kiroween.agenda.notifications import get_digest_service
from kiroween.agenda.ingestion import get_ingestion_service
from kiroween.agenda.search import get_knowledge_service, get_search_service
from kiroween.agenda.service import get_agenda_service
from kiroween.agenda.task_management import get_task_management_service
from kiroween.agenda.thread_management import get_thread_management_service
from kiroween.agenda.views import get_views_service
from kiroween.agenda.workflows import get_personal_workflows_service
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


@tool
async def ingest_slack_message(
    message_text: str,
    user_id: str,
    channel_id: str,
    message_ts: str,
    workspace_id: str | None = None,
    thread_ts: str | None = None,
) -> str:
    """Ingest a Slack message and automatically create agenda items.

    Analyzes the message to detect tasks, decisions, questions, etc.
    and creates appropriate agenda items with extracted metadata.
    """
    ingestion = get_ingestion_service()
    try:
        message = {
            "text": message_text,
            "user": user_id,
            "channel": channel_id,
            "ts": message_ts,
            "thread_ts": thread_ts,
        }
        item = await ingestion.ingest_message(message, workspace_id)
        if item:
            return f"Ingested message as {item.type.value}: '{item.title}' (ID: {item.id})"
        return "Message ingested but no agenda item created (likely not relevant)."
    except Exception as e:
        logger.error("ingest_message_error", error=str(e))
        return f"Error ingesting message: {e}"


@tool
async def get_my_tasks(
    user_id: str,
    workspace_id: str | None = None,
    include_completed: bool = False,
) -> str:
    """Get all tasks assigned to me, grouped by due date."""
    views = get_views_service()
    try:
        tasks = await views.get_my_tasks(user_id, workspace_id, include_completed)
        if not tasks:
            return "No tasks found."

        results = []
        for task in tasks:
            due_str = f" (Due: {task.due_date.strftime('%Y-%m-%d')})" if task.due_date else ""
            priority_str = " 🔴" if task.priority == 2 else " 🟡" if task.priority == 1 else ""
            results.append(f"• {task.title}{priority_str}{due_str}")

        return f"Your tasks ({len(tasks)}):\n\n" + "\n".join(results)
    except Exception as e:
        logger.error("get_my_tasks_error", error=str(e))
        return f"Error getting tasks: {e}"


@tool
async def update_task_status(
    task_id: str,
    status: str,
    changed_by: str | None = None,
) -> str:
    """Update task status (open, in_progress, completed, deferred, stale)."""
    task_mgmt = get_task_management_service()
    try:
        item = await task_mgmt.update_task_status(task_id, status, changed_by)
        if item:
            return f"Updated task '{item.title}' to status: {status}"
        return f"Task {task_id} not found."
    except Exception as e:
        logger.error("update_task_status_error", error=str(e))
        return f"Error updating task status: {e}"


@tool
async def get_overdue_tasks(
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    """Get all overdue tasks."""
    task_mgmt = get_task_management_service()
    try:
        tasks = await task_mgmt.get_overdue_tasks(user_id, workspace_id)
        if not tasks:
            return "No overdue tasks."

        results = []
        for task in tasks:
            days_overdue = (datetime.utcnow() - task.due_date).days if task.due_date else 0
            results.append(f"• {task.title} ({days_overdue} days overdue)")

        return f"Overdue tasks ({len(tasks)}):\n\n" + "\n".join(results)
    except Exception as e:
        logger.error("get_overdue_tasks_error", error=str(e))
        return f"Error getting overdue tasks: {e}"


@tool
async def generate_morning_digest(
    user_id: str,
    workspace_id: str | None = None,
) -> str:
    """Generate morning digest: tasks due today, new tasks, important decisions."""
    digest = get_digest_service()
    try:
        digest_data = await digest.generate_morning_digest(user_id, workspace_id)
        return await digest.format_digest_for_slack(digest_data, "morning_digest")
    except Exception as e:
        logger.error("generate_morning_digest_error", error=str(e))
        return f"Error generating morning digest: {e}"


@tool
async def extract_decisions_from_thread(
    thread_messages: list[dict[str, Any]],
    workspace_id: str,
    channel_id: str | None = None,
    thread_ts: str | None = None,
) -> str:
    """Extract decisions from a Slack thread."""
    thread_mgmt = get_thread_management_service()
    try:
        decisions = await thread_mgmt.extract_decisions_from_thread(
            thread_messages, workspace_id, channel_id, thread_ts
        )
        if not decisions:
            return "No decisions found in thread."

        results = []
        for decision in decisions:
            results.append(f"• {decision.decision_text}")

        return f"Extracted {len(decisions)} decision(s):\n\n" + "\n".join(results)
    except Exception as e:
        logger.error("extract_decisions_error", error=str(e))
        return f"Error extracting decisions: {e}"


@tool
async def search_decisions_about(
    topic: str,
    workspace_id: str | None = None,
    limit: int = 20,
) -> str:
    """Search for decisions about a specific topic."""
    search = get_search_service()
    try:
        decisions = await search.search_decisions_about(topic, workspace_id, limit)
        if not decisions:
            return f"No decisions found about '{topic}'."

        results = []
        for decision in decisions:
            results.append(f"• {decision.title} ({decision.created_at.strftime('%Y-%m-%d')})")

        return f"Decisions about '{topic}' ({len(decisions)}):\n\n" + "\n".join(results)
    except Exception as e:
        logger.error("search_decisions_error", error=str(e))
        return f"Error searching decisions: {e}"


@tool
async def find_similar_question(
    question: str,
    workspace_id: str | None = None,
) -> str:
    """Find if a similar question has been answered before (FAQ lookup)."""
    knowledge = get_knowledge_service()
    try:
        faq = await knowledge.find_similar_question(question, workspace_id)
        if faq:
            return f"Similar question found:\n\nQ: {faq.question}\nA: {faq.answer}"
        return "No similar questions found in FAQ."
    except Exception as e:
        logger.error("find_similar_question_error", error=str(e))
        return f"Error finding similar question: {e}"


@tool
async def snooze_task(
    task_id: str,
    hours: int,
    changed_by: str | None = None,
) -> str:
    """Snooze a task for N hours (updates due date)."""
    workflows = get_personal_workflows_service()
    try:
        item = await workflows.snooze_task(task_id, hours, changed_by)
        if item:
            return f"Snoozed task '{item.title}' for {hours} hours. New due date: {item.due_date}"
        return f"Task {task_id} not found."
    except Exception as e:
        logger.error("snooze_task_error", error=str(e))
        return f"Error snoozing task: {e}"


@tool
async def reassign_task(
    task_id: str,
    new_assignee_user_id: str,
    new_assignee_user_name: str | None = None,
    changed_by: str | None = None,
) -> str:
    """Reassign a task to a different user."""
    workflows = get_personal_workflows_service()
    try:
        item = await workflows.reassign_task(
            task_id, new_assignee_user_id, new_assignee_user_name, changed_by
        )
        if item:
            return f"Reassigned task '{item.title}' to {new_assignee_user_name or new_assignee_user_id}"
        return f"Task {task_id} not found."
    except Exception as e:
        logger.error("reassign_task_error", error=str(e))
        return f"Error reassigning task: {e}"


def get_agenda_tools() -> list:
    """Get all agenda-related tools."""
    return [
        agenda_db_upsert_item,
        agenda_db_search,
        ingest_slack_message,
        get_my_tasks,
        update_task_status,
        get_overdue_tasks,
        generate_morning_digest,
        extract_decisions_from_thread,
        search_decisions_about,
        find_similar_question,
        snooze_task,
        reassign_task,
    ]
