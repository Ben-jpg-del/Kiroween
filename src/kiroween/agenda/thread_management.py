"""Thread and decision management service."""

import re
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select

from kiroween.agenda.models import AgendaItem, Decision, ItemStatus, ItemType, ThreadTitle
from kiroween.agenda.repository import AgendaRepository
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class ThreadManagementService:
    """Service for managing threads, titles, and decision extraction."""

    def __init__(self):
        self.agenda_service = AgendaService()

    # Decision extraction patterns
    DECISION_PATTERNS = [
        r"we'll go with\s+([^.!?]+)",
        r"final decision:\s*([^.!?]+)",
        r"consensus:\s*([^.!?]+)",
        r"we decided\s+([^.!?]+)",
        r"agreed to\s+([^.!?]+)",
        r"decision:\s*([^.!?]+)",
        r"decided:\s*([^.!?]+)",
    ]

    async def infer_thread_title(
        self,
        thread_messages: list[dict[str, Any]],
        channel_id: str,
        thread_ts: str,
        workspace_id: str,
        use_llm: bool = False,
    ) -> ThreadTitle:
        """Infer a title for a thread."""
        if not thread_messages:
            title = "Untitled Thread"
        else:
            first_message = thread_messages[0]
            first_text = first_message.get("text", "")

            if use_llm:
                # TODO: Use LLM to generate title
                title = self._extract_title_from_text(first_text)
            else:
                title = self._extract_title_from_text(first_text)

        async with self.agenda_service.get_repository() as repo:
            # Check if title already exists
            result = await repo.session.execute(
                select(ThreadTitle).where(ThreadTitle.thread_ts == thread_ts)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.title = title
                existing.updated_at = datetime.utcnow()
                existing.last_activity_at = datetime.utcnow()
                existing.message_count = len(thread_messages)
                await repo.session.commit()
                await repo.session.refresh(existing)
                return existing

            thread_title = ThreadTitle(
                workspace_id=workspace_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                title=title,
                inferred_by="first_message" if not use_llm else "llm",
                last_activity_at=datetime.utcnow(),
                message_count=len(thread_messages),
            )
            repo.session.add(thread_title)
            await repo.session.commit()
            await repo.session.refresh(thread_title)

            logger.info("inferred_thread_title", thread_ts=thread_ts, title=title)
            return thread_title

    def _extract_title_from_text(self, text: str, max_length: int = 100) -> str:
        """Extract a title from message text."""
        # Remove markdown, mentions, URLs
        text = re.sub(r"<@\w+>", "", text)
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

        return title or "Untitled Thread"

    async def extract_decisions_from_thread(
        self,
        thread_messages: list[dict[str, Any]],
        workspace_id: str,
        channel_id: str | None = None,
        thread_ts: str | None = None,
    ) -> list[Decision]:
        """Extract decisions from a thread."""
        decisions = []

        for message in thread_messages:
            text = message.get("text", "").lower()
            message_ts = message.get("ts")

            for pattern in self.DECISION_PATTERNS:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    decision_text = match.group(1).strip()

                    # Create decision record
                    async with self.agenda_service.get_repository() as repo:
                        decision = Decision(
                            workspace_id=workspace_id,
                            thread_ts=thread_ts,
                            channel_id=channel_id,
                            decision_message_ts=message_ts,
                            decision_text=decision_text,
                        )
                        repo.session.add(decision)

                        # Also create agenda item
                        agenda_item = await self.agenda_service.upsert_item(
                            item_type=ItemType.DECISION.value,
                            title=f"Decision: {decision_text[:100]}",
                            description=message.get("text", ""),
                            status=ItemStatus.OPEN.value,
                            source_channel_id=channel_id,
                            source_thread_ts=thread_ts,
                        )

                        decision.agenda_item_id = agenda_item.id

                        # Extract project if mentioned
                        project_match = re.search(
                            r"project[:\s]+(\w+)", message.get("text", ""), re.IGNORECASE
                        )
                        if project_match:
                            agenda_item.project = project_match.group(1)
                            decision.project = project_match.group(1)

                        # Extract involved users
                        mentions = re.findall(r"<@(\w+)>", message.get("text", ""))
                        if mentions:
                            decision.involved_user_ids = ",".join(mentions)

                        await repo.session.commit()
                        await repo.session.refresh(decision)

                        decisions.append(decision)
                        logger.info(
                            "extracted_decision",
                            decision_id=decision.id,
                            thread_ts=thread_ts,
                        )

        return decisions

    async def get_thread_dashboard(
        self,
        workspace_id: str,
        channel_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Get thread dashboard with titles, activity, task/decision counts."""
        async with self.agenda_service.get_repository() as repo:
            # Get thread titles
            stmt = select(ThreadTitle).where(ThreadTitle.workspace_id == workspace_id)
            if channel_id:
                stmt = stmt.where(ThreadTitle.channel_id == channel_id)

            stmt = stmt.order_by(ThreadTitle.last_activity_at.desc()).limit(limit)
            result = await repo.session.execute(stmt)
            thread_titles = list(result.scalars().all())

            # For each thread, get task/decision counts
            dashboard = []
            for thread_title in thread_titles:
                # Count tasks in thread
                tasks_stmt = select(func.count(AgendaItem.id)).where(
                    and_(
                        AgendaItem.source_thread_ts == thread_title.thread_ts,
                        AgendaItem.type == ItemType.TASK,
                        AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                    )
                )
                tasks_result = await repo.session.execute(tasks_stmt)
                task_count = tasks_result.scalar_one()

                # Count decisions in thread
                decisions_stmt = select(func.count(Decision.id)).where(
                    Decision.thread_ts == thread_title.thread_ts
                )
                decisions_result = await repo.session.execute(decisions_stmt)
                decision_count = decisions_result.scalar_one()

                dashboard.append({
                    "thread_ts": thread_title.thread_ts,
                    "title": thread_title.title,
                    "channel_id": thread_title.channel_id,
                    "last_activity_at": thread_title.last_activity_at.isoformat() if thread_title.last_activity_at else None,
                    "message_count": thread_title.message_count,
                    "task_count": task_count,
                    "decision_count": decision_count,
                    "is_resolved": thread_title.is_resolved,
                })

            return dashboard

    async def mark_thread_resolved(
        self,
        thread_ts: str,
        workspace_id: str | None = None,
    ) -> bool:
        """Mark a thread as resolved."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(ThreadTitle).where(ThreadTitle.thread_ts == thread_ts)
            if workspace_id:
                stmt = stmt.where(ThreadTitle.workspace_id == workspace_id)

            result = await repo.session.execute(stmt)
            thread_title = result.scalar_one_or_none()

            if not thread_title:
                return False

            thread_title.is_resolved = True
            thread_title.updated_at = datetime.utcnow()
            await repo.session.commit()

            logger.info("marked_thread_resolved", thread_ts=thread_ts)
            return True

    async def get_thread_title(
        self,
        thread_ts: str,
    ) -> ThreadTitle | None:
        """Get thread title by thread_ts."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(ThreadTitle).where(ThreadTitle.thread_ts == thread_ts)
            )
            return result.scalar_one_or_none()


def get_thread_management_service() -> ThreadManagementService:
    """Get the global thread management service instance."""
    return ThreadManagementService()

