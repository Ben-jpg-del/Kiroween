"""SQLAlchemy ORM models for the Agenda database."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


class ItemType(str, Enum):
    """Types of agenda items."""

    TASK = "task"
    DECISION = "decision"
    OBLIGATION = "obligation"
    QUESTION = "question"
    ACTION_ITEM = "action_item"


class ItemStatus(str, Enum):
    """Status values for agenda items."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class AgendaItem(Base):
    """Core agenda item model for tracking tasks, decisions, and obligations."""

    __tablename__ = "agenda_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    type: Mapped[ItemType] = mapped_column(SQLEnum(ItemType), nullable=False)
    status: Mapped[ItemStatus] = mapped_column(
        SQLEnum(ItemStatus), default=ItemStatus.OPEN, nullable=False
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Slack source tracking
    source_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_channel_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_message_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Assignment and scheduling
    assigned_to_user_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    assigned_to_user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Metadata
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 0=normal, 1=high, 2=urgent
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)  # comma-separated

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    history: Mapped[list["AgendaItemHistory"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )

    def to_dict(self) -> dict:
        """Convert the model to a dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "source_channel_id": self.source_channel_id,
            "source_channel_name": self.source_channel_name,
            "source_thread_ts": self.source_thread_ts,
            "source_url": self.source_url,
            "assigned_to_user_id": self.assigned_to_user_id,
            "assigned_to_user_name": self.assigned_to_user_name,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "priority": self.priority,
            "tags": self.tags.split(",") if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AgendaItemHistory(Base):
    """Tracks changes to agenda items."""

    __tablename__ = "agenda_item_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agenda_items.id", ondelete="CASCADE"), nullable=False
    )
    field_changed: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    changed_by: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Slack user_id

    item: Mapped["AgendaItem"] = relationship(back_populates="history")
