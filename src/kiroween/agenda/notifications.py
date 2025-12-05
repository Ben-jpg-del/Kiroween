"""Notifications and digest generation service."""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, select

from kiroween.agenda.models import AgendaItem, ItemStatus, ItemType, UserProfile
from kiroween.agenda.repository import AgendaRepository
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class NotificationPolicyEngine:
    """Engine for deciding notification delivery based on user preferences."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def get_user_preferences(self, user_id: str) -> dict[str, Any]:
        """Get user notification preferences."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if not profile or not profile.notification_preferences:
                return self._default_preferences()

            return json.loads(profile.notification_preferences)

    def _default_preferences(self) -> dict[str, Any]:
        """Default notification preferences."""
        return {
            "instant_for": ["direct_tasks", "urgent_customer_issues"],
            "batch_everything_else": True,
            "quiet_hours": {"start": "22:00", "end": "08:00"},
            "focus_mode": False,
        }

    def should_notify_instantly(
        self,
        item: AgendaItem,
        preferences: dict[str, Any],
    ) -> bool:
        """Decide if an item should trigger instant notification."""
        instant_for = preferences.get("instant_for", [])

        # Direct tasks assigned to user
        if "direct_tasks" in instant_for:
            if item.type == ItemType.TASK and item.assigned_to_user_id:
                if item.priority >= 1:  # High or urgent
                    return True

        # Urgent customer issues
        if "urgent_customer_issues" in instant_for:
            if item.priority == 2:  # Urgent
                if "customer" in (item.project or "").lower() or "support" in (item.source_channel_name or "").lower():
                    return True

        # High priority items
        if "high_priority" in instant_for:
            if item.priority >= 1:
                return True

        return False

    def is_quiet_hours(self, preferences: dict[str, Any]) -> bool:
        """Check if current time is within quiet hours."""
        quiet_hours = preferences.get("quiet_hours")
        if not quiet_hours:
            return False

        now = datetime.utcnow()
        start_str = quiet_hours.get("start", "22:00")
        end_str = quiet_hours.get("end", "08:00")

        try:
            start_hour, start_min = map(int, start_str.split(":"))
            end_hour, end_min = map(int, end_str.split(":"))

            current_time = now.hour * 60 + now.minute
            start_time = start_hour * 60 + start_min
            end_time = end_hour * 60 + end_min

            if start_time > end_time:  # Overnight quiet hours
                return current_time >= start_time or current_time < end_time
            else:
                return start_time <= current_time < end_time
        except (ValueError, AttributeError):
            return False

    async def decide_notification_action(
        self,
        item: AgendaItem,
        user_id: str,
    ) -> str:
        """Decide notification action: 'instant', 'batch', or 'silent'."""
        preferences = await self.get_user_preferences(user_id)

        # Check quiet hours
        if self.is_quiet_hours(preferences):
            return "batch"

        # Check if should notify instantly
        if self.should_notify_instantly(item, preferences):
            return "instant"

        # Check if batching is enabled
        if preferences.get("batch_everything_else", True):
            return "batch"

        return "silent"


class DigestService:
    """Service for generating digests and summaries."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def generate_morning_digest(
        self,
        user_id: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate morning digest: tasks due today, new tasks, important decisions."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        async with self.agenda_service.get_repository() as repo:
            # Tasks due today
            tasks_due_today = await self._get_tasks_due_on_date(
                repo, user_id, today_start, workspace_id
            )

            # New tasks created in last 24h
            new_tasks = await self._get_new_items_since(
                repo, user_id, yesterday_start, ItemType.TASK, workspace_id
            )

            # Important decisions since yesterday
            decisions = await self._get_new_items_since(
                repo, user_id, yesterday_start, ItemType.DECISION, workspace_id
            )
            important_decisions = [d for d in decisions if d.priority >= 1]

        return {
            "tasks_due_today": tasks_due_today,
            "new_tasks_24h": new_tasks,
            "important_decisions_24h": important_decisions,
            "generated_at": now.isoformat(),
        }

    async def generate_end_of_day_recap(
        self,
        user_id: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate end-of-day recap: completed tasks, still open, overdue."""
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        async with self.agenda_service.get_repository() as repo:
            # Tasks completed today
            completed_today = await self._get_completed_today(
                repo, user_id, today_start, workspace_id
            )

            # Still open tasks
            open_tasks = await self._get_open_tasks(repo, user_id, workspace_id)

            # Overdue tasks
            overdue_tasks = await self._get_overdue_tasks(repo, user_id, workspace_id)

        return {
            "completed_today": completed_today,
            "still_open": open_tasks,
            "overdue": overdue_tasks,
            "generated_at": now.isoformat(),
        }

    async def generate_while_you_were_away(
        self,
        user_id: str,
        start_time: datetime,
        end_time: datetime,
        workspace_id: str | None = None,
        channel_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate summary of changes in watched channels during time window."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.created_at >= start_time,
                    AgendaItem.created_at <= end_time,
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            if channel_ids:
                stmt = stmt.where(AgendaItem.source_channel_id.in_(channel_ids))

            # Filter for items relevant to user
            stmt = stmt.where(
                or_(
                    AgendaItem.assigned_to_user_id == user_id,
                    AgendaItem.requestor_user_id == user_id,
                    AgendaItem.created_by_user_id == user_id,
                )
            )

            stmt = stmt.order_by(AgendaItem.created_at.desc())
            result = await repo.session.execute(stmt)
            items = list(result.scalars().all())

            # Group by type
            by_type = {}
            for item in items:
                item_type = item.type.value
                if item_type not in by_type:
                    by_type[item_type] = []
                by_type[item_type].append(item)

        return {
            "items": by_type,
            "total_count": len(items),
            "time_window": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
            },
        }

    async def format_digest_for_slack(
        self,
        digest: dict[str, Any],
        digest_type: str,
    ) -> str:
        """Format a digest as a Slack message."""
        lines = [f"*{digest_type.replace('_', ' ').title()}*\n"]

        if digest_type == "morning_digest":
            if tasks_due := digest.get("tasks_due_today"):
                lines.append(f"\n*Tasks Due Today ({len(tasks_due)}):*")
                for task in tasks_due[:10]:
                    priority = " 🔴" if task.priority == 2 else " 🟡" if task.priority == 1 else ""
                    lines.append(f"• {task.title}{priority}")

            if new_tasks := digest.get("new_tasks_24h"):
                lines.append(f"\n*New Tasks (24h) ({len(new_tasks)}):*")
                for task in new_tasks[:10]:
                    lines.append(f"• {task.title}")

            if decisions := digest.get("important_decisions_24h"):
                lines.append(f"\n*Important Decisions (24h) ({len(decisions)}):*")
                for decision in decisions[:5]:
                    lines.append(f"• {decision.title}")

        elif digest_type == "end_of_day":
            if completed := digest.get("completed_today"):
                lines.append(f"\n*Completed Today ({len(completed)}):*")
                for task in completed[:10]:
                    lines.append(f"✅ {task.title}")

            if open_tasks := digest.get("still_open"):
                lines.append(f"\n*Still Open ({len(open_tasks)}):*")
                for task in open_tasks[:10]:
                    lines.append(f"📋 {task.title}")

            if overdue := digest.get("overdue"):
                lines.append(f"\n*⚠️ Overdue ({len(overdue)}):*")
                for task in overdue[:10]:
                    lines.append(f"🔴 {task.title}")

        return "\n".join(lines)

    async def _get_tasks_due_on_date(
        self,
        repo: AgendaRepository,
        user_id: str,
        date: datetime,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get tasks due on a specific date."""
        date_end = date + timedelta(days=1)
        stmt = select(AgendaItem).where(
            and_(
                AgendaItem.type == ItemType.TASK,
                AgendaItem.assigned_to_user_id == user_id,
                AgendaItem.due_date >= date,
                AgendaItem.due_date < date_end,
                AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
            )
        )
        if workspace_id:
            stmt = stmt.where(AgendaItem.workspace_id == workspace_id)
        result = await repo.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_new_items_since(
        self,
        repo: AgendaRepository,
        user_id: str,
        since: datetime,
        item_type: ItemType,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get new items of a type since a date."""
        stmt = select(AgendaItem).where(
            and_(
                AgendaItem.type == item_type,
                AgendaItem.created_at >= since,
                or_(
                    AgendaItem.assigned_to_user_id == user_id,
                    AgendaItem.requestor_user_id == user_id,
                ),
            )
        )
        if workspace_id:
            stmt = stmt.where(AgendaItem.workspace_id == workspace_id)
        result = await repo.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_completed_today(
        self,
        repo: AgendaRepository,
        user_id: str,
        today_start: datetime,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get tasks completed today."""
        stmt = select(AgendaItem).where(
            and_(
                AgendaItem.type == ItemType.TASK,
                AgendaItem.assigned_to_user_id == user_id,
                AgendaItem.status == ItemStatus.COMPLETED,
                AgendaItem.completed_at >= today_start,
            )
        )
        if workspace_id:
            stmt = stmt.where(AgendaItem.workspace_id == workspace_id)
        result = await repo.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_open_tasks(
        self,
        repo: AgendaRepository,
        user_id: str,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get open tasks."""
        stmt = select(AgendaItem).where(
            and_(
                AgendaItem.type == ItemType.TASK,
                AgendaItem.assigned_to_user_id == user_id,
                AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
            )
        )
        if workspace_id:
            stmt = stmt.where(AgendaItem.workspace_id == workspace_id)
        result = await repo.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_overdue_tasks(
        self,
        repo: AgendaRepository,
        user_id: str,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get overdue tasks."""
        now = datetime.utcnow()
        stmt = select(AgendaItem).where(
            and_(
                AgendaItem.type == ItemType.TASK,
                AgendaItem.assigned_to_user_id == user_id,
                AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                AgendaItem.due_date.isnot(None),
                AgendaItem.due_date < now,
            )
        )
        if workspace_id:
            stmt = stmt.where(AgendaItem.workspace_id == workspace_id)
        result = await repo.session.execute(stmt)
        return list(result.scalars().all())


def get_notification_engine() -> NotificationPolicyEngine:
    """Get the global notification policy engine."""
    return NotificationPolicyEngine()


def get_digest_service() -> DigestService:
    """Get the global digest service."""
    return DigestService()

