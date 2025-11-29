"""Data access layer for agenda items."""

from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from kiroween.agenda.models import AgendaItem, AgendaItemHistory, ItemStatus, ItemType
from kiroween.config import get_settings
from kiroween.utils.errors import AgendaDBError
from kiroween.utils.logging import get_logger

logger = get_logger(__name__)


def get_async_engine():
    """Create async database engine."""
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=settings.app_env == "development",
        pool_pre_ping=True,
    )


def get_async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create async session factory."""
    engine = get_async_engine()
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class AgendaRepository:
    """Data access layer for agenda items."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, item_id: str) -> AgendaItem | None:
        """Get an agenda item by its ID."""
        result = await self.session.execute(
            select(AgendaItem).where(AgendaItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def upsert_item(self, item_data: dict) -> AgendaItem:
        """Create or update an agenda item.

        Args:
            item_data: Dictionary containing item fields.
                       If 'id' is provided and exists, updates the item.
                       Otherwise, creates a new item.

        Returns:
            The created or updated AgendaItem.
        """
        try:
            item_id = item_data.get("id")

            if item_id:
                existing = await self.get_by_id(item_id)
                if existing:
                    # Track changes for history
                    changes = []
                    for key, value in item_data.items():
                        if key == "id":
                            continue
                        if hasattr(existing, key):
                            old_value = getattr(existing, key)
                            if old_value != value:
                                changes.append((key, str(old_value), str(value)))
                                setattr(existing, key, value)

                    # Add history entries for changes
                    for field, old_val, new_val in changes:
                        history = AgendaItemHistory(
                            item_id=item_id,
                            field_changed=field,
                            old_value=old_val,
                            new_value=new_val,
                        )
                        self.session.add(history)

                    await self.session.commit()
                    await self.session.refresh(existing)
                    logger.info("updated_agenda_item", item_id=item_id, changes=len(changes))
                    return existing

            # Create new item
            # Convert type and status strings to enums if needed
            if "type" in item_data and isinstance(item_data["type"], str):
                item_data["type"] = ItemType(item_data["type"])
            if "status" in item_data and isinstance(item_data["status"], str):
                item_data["status"] = ItemStatus(item_data["status"])

            item = AgendaItem(**item_data)
            self.session.add(item)
            await self.session.commit()
            await self.session.refresh(item)
            logger.info("created_agenda_item", item_id=item.id, title=item.title)
            return item

        except Exception as e:
            await self.session.rollback()
            logger.error("agenda_db_error", error=str(e))
            raise AgendaDBError(f"Failed to upsert agenda item: {e}") from e

    async def search(
        self,
        query: str | None = None,
        item_type: ItemType | None = None,
        status: ItemStatus | None = None,
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
        stmt = select(AgendaItem)

        conditions = []
        if query:
            conditions.append(
                or_(
                    AgendaItem.title.ilike(f"%{query}%"),
                    AgendaItem.description.ilike(f"%{query}%"),
                )
            )
        if item_type:
            conditions.append(AgendaItem.type == item_type)
        if status:
            conditions.append(AgendaItem.status == status)
        if assigned_to:
            conditions.append(AgendaItem.assigned_to_user_id == assigned_to)
        if channel_id:
            conditions.append(AgendaItem.source_channel_id == channel_id)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(AgendaItem.updated_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_completed(self, item_id: str) -> AgendaItem | None:
        """Mark an agenda item as completed."""
        item = await self.get_by_id(item_id)
        if item:
            item.status = ItemStatus.COMPLETED
            item.completed_at = datetime.utcnow()
            await self.session.commit()
            await self.session.refresh(item)
            logger.info("completed_agenda_item", item_id=item_id)
        return item

    async def delete(self, item_id: str) -> bool:
        """Delete an agenda item."""
        item = await self.get_by_id(item_id)
        if item:
            await self.session.delete(item)
            await self.session.commit()
            logger.info("deleted_agenda_item", item_id=item_id)
            return True
        return False
