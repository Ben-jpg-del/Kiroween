"""Message ingestion service: Analyze Slack messages and create/update agenda items."""

import re
from datetime import datetime, timedelta
from typing import Any

from kiroween.agenda.models import AgendaItem, ItemStatus, ItemType
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class MessageIngestionService:
    """Service for ingesting Slack messages and creating agenda items."""

    def __init__(self):
        self.agenda_service = AgendaService()

    # Task detection patterns
    TASK_PATTERNS = [
        r"can you\s+([^?.!]+)",
        r"please\s+([^?.!]+)",
        r"i need you to\s+([^?.!]+)",
        r"todo:\s*([^\n]+)",
        r"@(\w+)\s+can you\s+([^?.!]+)",
        r"@(\w+)\s+please\s+([^?.!]+)",
        r"i'll\s+([^?.!]+)",
        r"let's\s+([^?.!]+)",
        r"we should\s+([^?.!]+)",
        r"action item:\s*([^\n]+)",
    ]

    # Due date patterns
    DUE_DATE_PATTERNS = [
        (r"by\s+(friday|monday|tuesday|wednesday|thursday|saturday|sunday)", "day_of_week"),
        (r"by\s+(eod|end of day)", "today"),
        (r"by\s+(eow|end of week)", "end_of_week"),
        (r"before\s+(standup|meeting|demo)", "relative"),
        (r"by\s+(\d{1,2}/\d{1,2}(?:/\d{2,4})?)", "date"),
        (r"(\d+)\s+(days?|hours?)\s+from now", "relative_days"),
        (r"tomorrow", "tomorrow"),
        (r"next\s+(week|month)", "relative"),
    ]

    # Completion patterns
    COMPLETION_PATTERNS = [
        r"done",
        r"finished",
        r"completed",
        r"✅",
        r"✓",
        r"resolved",
        r"closed",
    ]

    def detect_item_type(self, message_text: str, thread_context: list[dict] | None = None) -> ItemType:
        """Detect the type of agenda item from message content."""
        text_lower = message_text.lower()

        # Check for explicit markers
        if any(pattern in text_lower for pattern in ["todo:", "action item:", "task:"]):
            return ItemType.TASK

        if any(pattern in text_lower for pattern in ["decision:", "we decided", "agreed to", "consensus:"]):
            return ItemType.DECISION

        if any(pattern in text_lower for pattern in ["question:", "?", "can someone", "does anyone"]):
            return ItemType.QUESTION

        if any(pattern in text_lower for pattern in ["announcement:", "announcing", "update:"]):
            return ItemType.ANNOUNCEMENT

        # Check for task patterns
        for pattern in self.TASK_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return ItemType.TASK

        # Default to note if unclear
        return ItemType.NOTE

    def extract_assignee(self, message_text: str, mentions: list[str] | None = None) -> tuple[str | None, str | None]:
        """Extract assignee from message (user_id, user_name)."""
        if mentions:
            # First mention is likely the assignee
            return mentions[0], None  # user_name would need to be looked up

        # Check for @mentions in text
        mention_pattern = r"@(\w+)"
        matches = re.findall(mention_pattern, message_text)
        if matches:
            return matches[0], None

        return None, None

    def extract_due_date(self, message_text: str, message_ts: str | None = None) -> datetime | None:
        """Extract due date from message text."""
        text_lower = message_text.lower()
        base_time = datetime.utcnow()
        if message_ts:
            try:
                base_time = datetime.fromtimestamp(float(message_ts))
            except (ValueError, TypeError):
                pass

        for pattern, pattern_type in self.DUE_DATE_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                if pattern_type == "today":
                    return base_time.replace(hour=17, minute=0, second=0, microsecond=0)  # EOD
                elif pattern_type == "tomorrow":
                    return (base_time + timedelta(days=1)).replace(hour=17, minute=0, second=0, microsecond=0)
                elif pattern_type == "end_of_week":
                    days_until_friday = (4 - base_time.weekday()) % 7
                    if days_until_friday == 0:
                        days_until_friday = 7
                    return (base_time + timedelta(days=days_until_friday)).replace(hour=17, minute=0, second=0, microsecond=0)
                elif pattern_type == "day_of_week":
                    day_name = match.group(1).lower()
                    day_map = {
                        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                        "friday": 4, "saturday": 5, "sunday": 6
                    }
                    target_day = day_map.get(day_name)
                    if target_day is not None:
                        days_ahead = (target_day - base_time.weekday()) % 7
                        if days_ahead == 0:
                            days_ahead = 7
                        return (base_time + timedelta(days=days_ahead)).replace(hour=17, minute=0, second=0, microsecond=0)
                elif pattern_type == "relative_days":
                    num = int(match.group(1))
                    unit = match.group(2)
                    if "day" in unit:
                        return (base_time + timedelta(days=num)).replace(hour=17, minute=0, second=0, microsecond=0)
                    elif "hour" in unit:
                        return base_time + timedelta(hours=num)

        return None

    def extract_title(self, message_text: str, max_length: int = 100) -> str:
        """Extract a short title from message text."""
        # Remove markdown, mentions, URLs
        text = re.sub(r"<@\w+>", "", message_text)
        text = re.sub(r"<https?://[^>]+>", "", text)
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[*_`]", "", text)

        # Take first sentence or first line
        lines = text.split("\n")
        first_line = lines[0].strip()
        sentences = re.split(r"[.!?]", first_line)
        title = sentences[0].strip() if sentences else first_line

        if len(title) > max_length:
            title = title[:max_length - 3] + "..."

        return title or "Untitled"

    def extract_project_topic(self, message_text: str, channel_name: str | None = None) -> tuple[str | None, str | None]:
        """Extract project and topic from message or channel."""
        project = None
        topic = None

        # Check for explicit project markers
        project_match = re.search(r"project[:\s]+(\w+)", message_text, re.IGNORECASE)
        if project_match:
            project = project_match.group(1)

        # Use channel name as topic if it looks like a project channel
        if channel_name:
            if any(prefix in channel_name.lower() for prefix in ["proj-", "project-", "team-"]):
                project = channel_name

        return project, topic

    async def ingest_message(
        self,
        message: dict[str, Any],
        workspace_id: str | None = None,
        thread_context: list[dict] | None = None,
    ) -> AgendaItem | None:
        """Ingest a Slack message and create/update agenda items.

        Args:
            message: Slack message dict with text, user, ts, channel, etc.
            workspace_id: Workspace ID
            thread_context: List of messages in the thread for context

        Returns:
            Created or updated AgendaItem, or None if not relevant
        """
        message_text = message.get("text", "")
        if not message_text or len(message_text.strip()) < 10:
            return None  # Skip very short messages

        # Detect item type
        item_type = self.detect_item_type(message_text, thread_context)

        # Skip pure chatter (notes without clear purpose)
        if item_type == ItemType.NOTE and not any(
            keyword in message_text.lower()
            for keyword in ["important", "note:", "reminder", "update"]
        ):
            return None

        # Extract information
        title = self.extract_title(message_text)
        assignee_id, assignee_name = self.extract_assignee(
            message_text, message.get("mentions", [])
        )
        due_date = self.extract_due_date(message_text, message.get("ts"))
        project, topic = self.extract_project_topic(
            message_text, message.get("channel_name")
        )

        # Get requestor (message author)
        requestor_id = message.get("user")
        requestor_name = message.get("user_name")

        # Build source URL
        channel_id = message.get("channel")
        thread_ts = message.get("thread_ts") or message.get("ts")
        message_ts = message.get("ts")
        source_url = None
        if channel_id and message_ts:
            if thread_ts and thread_ts != message_ts:
                source_url = f"https://slack.com/archives/{channel_id}/p{message_ts.replace('.', '')}"
            else:
                source_url = f"https://slack.com/archives/{channel_id}/p{message_ts.replace('.', '')}"

        # Create raw snippet (first 200 chars)
        raw_snippet = message_text[:200] + ("..." if len(message_text) > 200 else "")

        # Check if this is a completion message
        status = ItemStatus.OPEN
        if any(re.search(pattern, message_text.lower()) for pattern in self.COMPLETION_PATTERNS):
            status = ItemStatus.COMPLETED

        # Create agenda item
        item = await self.agenda_service.upsert_item(
            item_type=item_type.value,
            title=title,
            description=message_text,
            status=status.value,
            assigned_to_user_id=assignee_id,
            assigned_to_user_name=assignee_name,
            source_channel_id=channel_id,
            source_channel_name=message.get("channel_name"),
            source_thread_ts=thread_ts,
            source_url=source_url,
            priority=0,
        )

        # Update with additional fields via repository
        async with self.agenda_service.get_repository() as repo:
            item.workspace_id = workspace_id
            item.raw_snippet = raw_snippet
            item.source_message_ts = message_ts
            item.requestor_user_id = requestor_id
            item.requestor_user_name = requestor_name
            item.created_by_user_id = requestor_id
            item.project = project
            item.topic = topic
            item.due_date = due_date
            item.due_at = due_date  # Alias
            await repo.session.commit()
            await repo.session.refresh(item)

        logger.info(
            "ingested_message",
            item_id=item.id,
            item_type=item_type.value,
            title=title[:50],
        )

        return item

    async def ingest_thread(
        self,
        thread_messages: list[dict[str, Any]],
        workspace_id: str | None = None,
        channel_id: str | None = None,
        thread_ts: str | None = None,
    ) -> list[AgendaItem]:
        """Ingest all messages in a thread and create agenda items."""
        items = []
        for message in thread_messages:
            item = await self.ingest_message(
                message=message,
                workspace_id=workspace_id,
                thread_context=thread_messages,
            )
            if item:
                items.append(item)
        return items


def get_ingestion_service() -> MessageIngestionService:
    """Get the global ingestion service instance."""
    return MessageIngestionService()

