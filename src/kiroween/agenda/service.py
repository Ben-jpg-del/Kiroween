"""Business logic for agenda operations."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from kiroween.agenda.models import AgendaItem, ItemStatus, ItemType
from kiroween.agenda.repository import AgendaRepository, get_async_session_factory
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


class AgendaService:
    """Service layer for agenda operations."""

    def __init__(self):
        self._session_factory = get_async_session_factory()

    @asynccontextmanager
    async def get_repository(self) -> AsyncGenerator[AgendaRepository, None]:
        """Get a repository instance with managed session."""
        async with self._session_factory() as session:
            yield AgendaRepository(session)

    async def upsert_item(
        self,
        item_type: str,
        title: str,
        description: str | None = None,
        status: str = "open",
        item_id: str | None = None,
        assigned_to_user_id: str | None = None,
        assigned_to_user_name: str | None = None,
        source_channel_id: str | None = None,
        source_channel_name: str | None = None,
        source_thread_ts: str | None = None,
        source_url: str | None = None,
        priority: int = 0,
        tags: list[str] | None = None,
    ) -> AgendaItem:
        """Create or update an agenda item.

        Args:
            item_type: Type of item (task, decision, obligation, etc.)
            title: Brief title
            description: Detailed description
            status: Status (open, in_progress, completed, deferred)
            item_id: ID for updates, None for new items
            assigned_to_user_id: Slack user ID of assignee
            assigned_to_user_name: Display name of assignee
            source_channel_id: Source Slack channel ID
            source_channel_name: Source Slack channel name
            source_thread_ts: Source thread timestamp
            source_url: Link to the source message
            priority: Priority level (0=normal, 1=high, 2=urgent)
            tags: List of tags

        Returns:
            The created or updated AgendaItem.
        """
        item_data = {
            "type": ItemType(item_type),
            "title": title,
            "description": description,
            "status": ItemStatus(status),
            "assigned_to_user_id": assigned_to_user_id,
            "assigned_to_user_name": assigned_to_user_name,
            "source_channel_id": source_channel_id,
            "source_channel_name": source_channel_name,
            "source_thread_ts": source_thread_ts,
            "source_url": source_url,
            "priority": priority,
            "tags": ",".join(tags) if tags else None,
        }

        if item_id:
            item_data["id"] = item_id

        async with self.get_repository() as repo:
            return await repo.upsert_item(item_data)

    async def search_items(
        self,
        query: str | None = None,
        item_type: str | None = None,
        status: str | None = None,
        assigned_to: str | None = None,
        channel_id: str | None = None,
        limit: int = 50,
    ) -> list[AgendaItem]:
        """Search agenda items with filters.

        Args:
            query: Text search in title/description
            item_type: Filter by item type
            status: Filter by status
            assigned_to: Filter by assigned user ID
            channel_id: Filter by source channel
            limit: Maximum number of results

        Returns:
            List of matching AgendaItems.
        """
        async with self.get_repository() as repo:
            return await repo.search(
                query=query,
                item_type=ItemType(item_type) if item_type else None,
                status=ItemStatus(status) if status else None,
                assigned_to=assigned_to,
                channel_id=channel_id,
                limit=limit,
            )

    async def get_item(self, item_id: str) -> AgendaItem | None:
        """Get a specific agenda item by ID."""
        async with self.get_repository() as repo:
            return await repo.get_by_id(item_id)

    async def complete_item(self, item_id: str) -> AgendaItem | None:
        """Mark an agenda item as completed."""
        async with self.get_repository() as repo:
            return await repo.mark_completed(item_id)

    async def delete_item(self, item_id: str) -> bool:
        """Delete an agenda item."""
        async with self.get_repository() as repo:
            return await repo.delete(item_id)


# Global service instance
_agenda_service: AgendaService | None = None


def get_agenda_service() -> AgendaService:
    """Get the global agenda service instance."""
    global _agenda_service
    if _agenda_service is None:
        _agenda_service = AgendaService()
    return _agenda_service
