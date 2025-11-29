"""Views service: Predefined and custom views for agenda items."""

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select

from kiroween.agenda.models import AgendaItem, ItemStatus, ItemType, View
from kiroween.agenda.repository import AgendaRepository
from kiroween.agenda.service import AgendaService
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class ViewsService:
    """Service for managing predefined and custom views."""

    def __init__(self):
        self.agenda_service = AgendaService()

    async def get_my_tasks(
        self,
        user_id: str,
        workspace_id: str | None = None,
        include_completed: bool = False,
    ) -> list[AgendaItem]:
        """Get all tasks assigned to me, grouped by due date."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.assigned_to_user_id == user_id,
                )
            )

            if not include_completed:
                stmt = stmt.where(
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS])
                )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(
                AgendaItem.due_date.asc().nulls_last(),
                AgendaItem.priority.desc(),
                AgendaItem.created_at.desc(),
            )

            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def get_what_i_owe(
        self,
        user_id: str,
        requestor_user_id: str,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get tasks where assignee=me and requestor=requestor_user_id."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.TASK,
                    AgendaItem.assigned_to_user_id == user_id,
                    AgendaItem.requestor_user_id == requestor_user_id,
                    AgendaItem.status.in_([ItemStatus.OPEN, ItemStatus.IN_PROGRESS]),
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.due_date.asc().nulls_last())
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def get_decisions_for_project(
        self,
        project: str,
        workspace_id: str | None = None,
    ) -> list[AgendaItem]:
        """Get all decisions for a specific project."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.DECISION,
                    AgendaItem.project == project,
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.created_at.desc())
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def get_open_questions_i_asked(
        self,
        user_id: str,
        workspace_id: str | None = None,
        days: int = 7,
    ) -> list[AgendaItem]:
        """Get open questions created by me in the last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem).where(
                and_(
                    AgendaItem.type == ItemType.QUESTION,
                    AgendaItem.created_by_user_id == user_id,
                    AgendaItem.status == ItemStatus.OPEN,
                    AgendaItem.created_at >= cutoff_date,
                )
            )

            if workspace_id:
                stmt = stmt.where(AgendaItem.workspace_id == workspace_id)

            stmt = stmt.order_by(AgendaItem.created_at.desc())
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def create_view(
        self,
        workspace_id: str,
        name: str,
        filters: dict[str, Any],
        user_id: str | None = None,
        description: str | None = None,
        is_predefined: bool = False,
    ) -> View:
        """Create a custom view."""
        async with self.agenda_service.get_repository() as repo:
            view = View(
                workspace_id=workspace_id,
                user_id=user_id,
                name=name,
                description=description,
                is_predefined=is_predefined,
                filters=json.dumps(filters),
            )
            repo.session.add(view)
            await repo.session.commit()
            await repo.session.refresh(view)

            logger.info("created_view", view_id=view.id, name=name)
            return view

    async def get_view(self, view_id: str) -> View | None:
        """Get a view by ID."""
        async with self.agenda_service.get_repository() as repo:
            result = await repo.session.execute(select(View).where(View.id == view_id))
            return result.scalar_one_or_none()

    async def list_views(
        self,
        workspace_id: str,
        user_id: str | None = None,
        include_predefined: bool = True,
    ) -> list[View]:
        """List views for a workspace/user."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(View).where(View.workspace_id == workspace_id)

            if user_id:
                stmt = stmt.where(
                    or_(View.user_id == user_id, View.user_id.is_(None))
                )  # User's views + shared views
            else:
                stmt = stmt.where(View.user_id.is_(None))  # Only shared views

            if not include_predefined:
                stmt = stmt.where(View.is_predefined == False)

            stmt = stmt.order_by(View.is_predefined.desc(), View.name.asc())
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())

    async def update_view(
        self,
        view_id: str,
        name: str | None = None,
        description: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> View | None:
        """Update a view."""
        async with self.agenda_service.get_repository() as repo:
            view = await self.get_view(view_id)
            if not view:
                return None

            if name is not None:
                view.name = name
            if description is not None:
                view.description = description
            if filters is not None:
                view.filters = json.dumps(filters)

            view.updated_at = datetime.utcnow()
            await repo.session.commit()
            await repo.session.refresh(view)

            logger.info("updated_view", view_id=view_id)
            return view

    async def delete_view(self, view_id: str) -> bool:
        """Delete a view."""
        async with self.agenda_service.get_repository() as repo:
            view = await self.get_view(view_id)
            if not view:
                return False

            await repo.session.delete(view)
            await repo.session.commit()

            logger.info("deleted_view", view_id=view_id)
            return True

    async def execute_view(self, view_id: str, limit: int = 50) -> list[AgendaItem]:
        """Execute a view's filters and return matching agenda items."""
        view = await self.get_view(view_id)
        if not view:
            return []

        filters = json.loads(view.filters)
        return await self._apply_filters(filters, limit)

    async def _apply_filters(
        self,
        filters: dict[str, Any],
        limit: int = 50,
    ) -> list[AgendaItem]:
        """Apply filter criteria to agenda items."""
        async with self.agenda_service.get_repository() as repo:
            stmt = select(AgendaItem)

            conditions = []

            # Filter by assignees
            if assignees := filters.get("assignees"):
                if isinstance(assignees, list):
                    conditions.append(AgendaItem.assigned_to_user_id.in_(assignees))
                else:
                    conditions.append(AgendaItem.assigned_to_user_id == assignees)

            # Filter by project/topic
            if project := filters.get("project"):
                conditions.append(AgendaItem.project == project)
            if topic := filters.get("topic"):
                conditions.append(AgendaItem.topic == topic)

            # Filter by type
            if item_type := filters.get("type"):
                if isinstance(item_type, list):
                    types = [ItemType(t) for t in item_type]
                    conditions.append(AgendaItem.type.in_(types))
                else:
                    conditions.append(AgendaItem.type == ItemType(item_type))

            # Filter by status
            if status := filters.get("status"):
                if isinstance(status, list):
                    statuses = [ItemStatus(s) for s in status]
                    conditions.append(AgendaItem.status.in_(statuses))
                else:
                    conditions.append(AgendaItem.status == ItemStatus(status))

            # Filter by channel
            if channel_id := filters.get("channel_id"):
                conditions.append(AgendaItem.source_channel_id == channel_id)

            # Filter by date range
            if date_range := filters.get("date_range"):
                if date_from := date_range.get("from"):
                    if isinstance(date_from, str):
                        date_from = datetime.fromisoformat(date_from)
                    conditions.append(AgendaItem.created_at >= date_from)
                if date_to := date_range.get("to"):
                    if isinstance(date_to, str):
                        date_to = datetime.fromisoformat(date_to)
                    conditions.append(AgendaItem.created_at <= date_to)

            # Filter by workspace
            if workspace_id := filters.get("workspace_id"):
                conditions.append(AgendaItem.workspace_id == workspace_id)

            # Text search
            if query := filters.get("query"):
                conditions.append(
                    or_(
                        AgendaItem.title.ilike(f"%{query}%"),
                        AgendaItem.description.ilike(f"%{query}%"),
                        AgendaItem.raw_snippet.ilike(f"%{query}%"),
                    )
                )

            if conditions:
                stmt = stmt.where(and_(*conditions))

            # Ordering
            order_by = filters.get("order_by", "updated_at_desc")
            if order_by == "due_date_asc":
                stmt = stmt.order_by(AgendaItem.due_date.asc().nulls_last())
            elif order_by == "due_date_desc":
                stmt = stmt.order_by(AgendaItem.due_date.desc().nulls_last())
            elif order_by == "priority_desc":
                stmt = stmt.order_by(AgendaItem.priority.desc(), AgendaItem.updated_at.desc())
            else:
                stmt = stmt.order_by(AgendaItem.updated_at.desc())

            stmt = stmt.limit(limit)
            result = await repo.session.execute(stmt)
            return list(result.scalars().all())


def get_views_service() -> ViewsService:
    """Get the global views service instance."""
    return ViewsService()

