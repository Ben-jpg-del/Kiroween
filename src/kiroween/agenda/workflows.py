"""Personal workflows and user controls service."""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, select

from kiroween.agenda.models import AgendaItem, ItemStatus, ItemType, UserProfile
from kiroween.agenda.repository import AgendaRepository
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class PersonalWorkflowsService:
    """Service for personal workflows: focus modes, quick actions, etc."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def get_focus_mode_tasks(
        self,
        user_id: str,
        top_n: int = 5,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get top N tasks for focus mode, suppressing low-priority noise."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.assigned_to_user_id == user_id,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                    # Suppress low priority (priority 0) unless due soon
                    or_(
                        AgendaItem.priority > 0,  # High or urgent
                        and_(
                            AgendaItem.priority == 0,
                            AgendaItem.due_date.isnot(None),
                            AgendaItem.due_date <= datetime.utcnow() + timedelta(days=1),
                        ),
                    ),
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            # Order by priority, then due date
            stmt = stmt.order_by(
                AgendaItem.priority.desc(),
                AgendaItem.due_date.asc().nulls_last(),
            ).limit(top_n)

            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def get_meeting_mode_items(
        self,
        user_id: str,
        related_user_id: str | None = None,
        project: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, list[AgendaItem]]:
        """Get agenda items related to a specific person or project for a meeting."""
        async with self.agenda_service.get_repository() as repo:
            conditions = [
                or_(
                    AgendaItem.assigned_to_user_id == user_id,
                    AgendaItem.requestor_user_id == user_id,
                ),
                AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
            ]

            if related_user_id:
                conditions.append(
                    or_(
                        AgendaItem.assigned_to_user_id == related_user_id,
                        AgendaItem.requestor_user_id == related_user_id,
                    )
                )

            if project:
                conditions.append(AgendaItem.project == project)

            if workspace_id:
                conditions.append(AgendaItem.workspace_id == workspace_id)

            stmt = select(AgendaItem).where(and_(*conditions))
            stmt = stmt.order_by(AgendaItem.priority.desc(), AgendaItem.due_date.asc().nulls_last())

            result = await repo.session.execute(stmt)
            items = list(result.scalars().all())

            # Group by type
            by_type = {}
            for item in items:
                item_type = item.type.value
                if item_type not in by_type:
                    by_type[item_type] = []
                by_type[item_type].append(item)

            return by_type

    async def snooze_task(
        self,
        task_id: str,
        hours: int,
        changed_by: str | None = None,
    ) -> AgendaItem | None:
        """Snooze a task for N hours (updates due_date)."""
        async with self.agenda_service.get_repository() as repo:
            item = await repo.get_by_id(task_id)
            if not item or item.type != ItemType.TASK:
                return None

            new_due_date = datetime.utcnow() + timedelta(hours=hours)
            old_due_date = item.due_date

            item.due_date = new_due_date
            item.due_at = new_due_date
            item.updated_at = datetime.utcnow()

            await repo.session.commit()
            await repo.session.refresh(item)

            logger.info(
                "snoozed_task",
                task_id=task_id,
                hours=hours,
                new_due_date=new_due_date.isoformat(),
            )

            return item

    async def reassign_task(
        self,
        task_id: str,
        new_assignee_user_id: str,
        new_assignee_user_name: str | None = None,
        changed_by: str | None = None,
    ) -> AgendaItem | None:
        """Reassign a task to a different user."""
        async with self.agenda_service.get_repository() as repo:
            item = await repo.get_by_id(task_id)
            if not item or item.type != ItemType.TASK:
                return None

            old_assignee = item.assigned_to_user_id
            item.assigned_to_user_id = new_assignee_user_id
            item.assigned_to_user_name = new_assignee_user_name
            item.updated_at = datetime.utcnow()

            await repo.session.commit()
            await repo.session.refresh(item)

            logger.info(
                "reassigned_task",
                task_id=task_id,
                old_assignee=old_assignee,
                new_assignee=new_assignee_user_id,
            )

            return item

    async def change_priority(
        self,
        task_id: str,
        priority: int,
        changed_by: str | None = None,
    ) -> AgendaItem | None:
        """Change task priority (0=normal, 1=high, 2=urgent)."""
        if priority not in [0, 1, 2]:
            raise ValueError("Priority must be 0, 1, or 2")

        async with self.agenda_service.get_repository() as repo:
            item = await repo.get_by_id(task_id)
            if not item:
                return None

            old_priority = item.priority
            item.priority = priority
            item.updated_at = datetime.utcnow()

            await repo.session.commit()
            await repo.session.refresh(item)

            logger.info(
                "changed_priority",
                task_id=task_id,
                old_priority=old_priority,
                new_priority=priority,
            )

            return item

    async def convert_to_ticket(
        self,
        item_id: str,
        ticket_system: str = "external",
        ticket_id: str | None = None,
    ) -> AgendaItem | None:
        """Convert a decision/task into a ticket/event (marks with label)."""
        async with self.agenda_service.get_repository() as repo:
            item = await repo.get_by_id(item_id)
            if not item:
                return None

            # Add label
            labels = item.labels.split(",") if item.labels else []
            ticket_label = f"ticket:{ticket_system}"
            if ticket_id:
                ticket_label += f":{ticket_id}"

            if ticket_label not in labels:
                labels.append(ticket_label)
                item.labels = ",".join(labels)
                item.updated_at = datetime.utcnow()
                await repo.session.commit()
                await repo.session.refresh(item)

            logger.info(
                "converted_to_ticket",
                item_id=item_id,
                ticket_system=ticket_system,
                ticket_id=ticket_id,
            )

            return item

    async def enable_focus_mode(
        self,
        user_id: str,
        top_n_tasks: int = 5,
        suppress_low_priority: bool = True,
    ) -> UserProfile:
        """Enable focus mode for a user."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()

            if not profile:
                # Create profile if it doesn't exist
                profile = UserProfile(
                    user_id=user_id,
                    workspace_id="",  # Will need to be set
                    focus_mode_enabled=True,
                    focus_mode_settings=json.dumps({
                        "top_n_tasks": top_n_tasks,
                        "suppress_low_priority": suppress_low_priority,
                    }),
                )
                repo.session.add(profile)
            else:
                profile.focus_mode_enabled = True
                profile.focus_mode_settings = json.dumps({
                    "top_n_tasks": top_n_tasks,
                    "suppress_low_priority": suppress_low_priority,
                })

            await repo.session.commit()
            await repo.session.refresh(profile)

            logger.info("enabled_focus_mode", user_id=user_id)
            return profile

    async def disable_focus_mode(self, user_id: str) -> UserProfile | None:
        """Disable focus mode for a user."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()

            if not profile:
                return None

            profile.focus_mode_enabled = False
            await repo.session.commit()
            await repo.session.refresh(profile)

            logger.info("disabled_focus_mode", user_id=user_id)
            return profile

    async def get_user_profile(self, user_id: str) -> UserProfile | None:
        """Get user profile."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            return result.scalar_one_or_none()


def get_personal_workflows_service() -> PersonalWorkflowsService:
    """Get the global personal workflows service instance."""
    return PersonalWorkflowsService()

