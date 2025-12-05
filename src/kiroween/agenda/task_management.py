"""Task and workflow management service."""

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select

from kiroween.agenda.models import AgendaItem, ItemStatus, ItemType
from kiroween.agenda.repository import AgendaRepository
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class TaskManagementService:
    """Service for managing task lifecycle and workflows."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def create_task_from_message(
        self,
        message_text: str,
        assignee_user_id: str | None = None,
        assignee_user_name: str | None = None,
        requestor_user_id: str | None = None,
        due_date: datetime | None = None,
        source_channel_id: str | None = None,
        source_thread_ts: str | None = None,
        priority: int = 0,
    ) -> AgendaItem:
        """Create a task from a message."""
        from kiroween.agenda.ingestion import MessageIngestionService

        ingestion = MessageIngestionService()
        title = ingestion.extract_title(message_text)

        item = await self.agenda_service.upsert_item(
            item_type=ItemType.TASK.value,
            title=title,
            description=message_text,
            status=ItemStatus.OPEN.value,
            assigned_to_user_id=assignee_user_id,
            assigned_to_user_name=assignee_user_name,
            source_channel_id=source_channel_id,
            source_thread_ts=source_thread_ts,
            priority=priority,
        )

        # Update with additional fields
        async with self.agenda_service.get_repository() as repo:
            item.requestor_user_id = requestor_user_id
            item.due_date = due_date
            item.due_at = due_date
            await repo.session.commit()
            await repo.session.refresh(item)

        logger.info("created_task", item_id=item.id, assignee=assignee_user_id)
        return item

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        changed_by: str | None = None,
    ) -> AgendaItem | None:
        """Update task status with history tracking."""
        async with self.agenda_service.get_repository() as repo:
            item = await repo.get_by_id(task_id)
            if not item:
                return None

            old_status = item.status.value
            item.status = ItemStatus(status)

            if status == ItemStatus.COMPLETED.value:
                item.completed_at = datetime.utcnow()
            elif status == ItemStatus.IN_PROGRESS.value and not item.completed_at:
                item.completed_at = None

            await repo.session.commit()
            await repo.session.refresh(item)

            logger.info(
                "updated_task_status",
                item_id=task_id,
                old_status=old_status,
                new_status=status,
            )

            return item

    async def close_tasks_in_thread(
        self,
        thread_ts: str,
        channel_id: str | None = None,
    ) -> int:
        """Close all open tasks in a thread."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.source_thread_ts == thread_ts,
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                )
            )
            if channel_id:
                stmt = stmt.where(AgendaItem.source_channel_id == channel_id)

            result = await repo.session.execute(stmt)
            items = list(result.scalars().all())

            count = 0
            for item in items:
                item.status = ItemStatus.COMPLETED
                item.completed_at = datetime.utcnow()
                count += 1

            await repo.session.commit()
            logger.info("closed_tasks_in_thread", thread_ts=thread_ts, count=count)
            return count

    async def get_overdue_tasks(
        self,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get all overdue tasks."""
        now = datetime.utcnow()
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                    AgendaItem.due_date.isnot(None),
                    AgendaItem.due_date < now,
                )
            )

            if user_id:
                stmt = stmt.where(AgendaItem.assigned_to_user_id == user_id)
            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.due_date.asc())
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def get_tasks_without_owner(
        self,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get tasks with no assignee."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                    or_(
                        AgendaItem.assigned_to_user_id.is_(None),
                        AgendaItem.assigned_to_user_id == "",
                    ),
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def get_tasks_without_due_date(
        self,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get tasks with no due date."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                    AgendaItem.due_date.is_(None),
                )
            )

            if user_id:
                stmt = stmt.where(AgendaItem.assigned_to_user_id == user_id)
            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def mark_stale_tasks(
        self,
        days_inactive: int = 30,
        workspace_id: str | None = None,
    ) -> int:
        """Mark tasks as stale if they haven't been updated in N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_inactive)
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                    AgendaItem.updated_at < cutoff_date,
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            result = await repo.session.execute(stmt)
            items = list(result.scalars().all())

            count = 0
            for item in items:
                item.status = ItemStatus.STALE
                count += 1

            await repo.session.commit()
            logger.info("marked_stale_tasks", count=count, days_inactive=days_inactive)
            return count


def get_task_management_service() -> TaskManagementService:
    """Get the global task management service instance."""
    return TaskManagementService()

