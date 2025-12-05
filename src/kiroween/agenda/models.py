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
    NOTE = "note"
    ANNOUNCEMENT = "announcement"


class ItemStatus(str, Enum):
    """Status values for agenda items."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"
    STALE = "stale"
    DONE = "done"  # Alias for completed, kept for compatibility


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
    raw_snippet: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Workspace and source tracking
    workspace_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_channel_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_message_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Assignment and ownership
    assigned_to_user_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    assigned_to_user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requestor_user_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    requestor_user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # Project and organization
    project: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    topic: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    labels: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Scheduling
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Metadata
    priority: Mapped[int] = mapped_column(Integer, default=0)  # 0=normal, 1=high, 2=urgent
    tags: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

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
            "raw_snippet": self.raw_snippet,
            "workspace_id": self.workspace_id,
            "source_channel_id": self.source_channel_id,
            "source_channel_name": self.source_channel_name,
            "source_thread_ts": self.source_thread_ts,
            "source_message_ts": self.source_message_ts,
            "source_url": self.source_url,
            "assigned_to_user_id": self.assigned_to_user_id,
            "assigned_to_user_name": self.assigned_to_user_name,
            "requestor_user_id": self.requestor_user_id,
            "requestor_user_name": self.requestor_user_name,
            "created_by_user_id": self.created_by_user_id,
            "project": self.project,
            "topic": self.topic,
            "labels": self.labels.split(",") if self.labels else [],
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "due_at": self.due_at.isoformat() if self.due_at else None,
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


class UserProfile(Base):
    """User profile with notification preferences and focus settings."""

    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    workspace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    user_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_email: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Notification preferences (JSON stored as text)
    notification_preferences: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    focus_mode_enabled: Mapped[bool] = mapped_column(default=False)
    focus_mode_settings: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WorkspaceConfig(Base):
    """Workspace configuration: which channels to watch, what's important."""

    __tablename__ = "workspace_configs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    workspace_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    workspace_name: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Watched channels (JSON array stored as text)
    watched_channels: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    important_channels: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    ignored_channels: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Configuration (JSON stored as text)
    config: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class View(Base):
    """Saved filter views for agenda items."""

    __tablename__ = "views"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    workspace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_predefined: Mapped[bool] = mapped_column(default=False)

    # Filter criteria (JSON stored as text)
    filters: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ThreadTitle(Base):
    """Virtual thread titles inferred from Slack threads."""

    __tablename__ = "thread_titles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    workspace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_ts: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    inferred_by: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # Thread metadata
    last_activity_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    is_resolved: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Decision(Base):
    """Extracted decisions from threads."""

    __tablename__ = "decisions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    workspace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    agenda_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agenda_items.id", ondelete="SET NULL"), nullable=True
    )
    thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    decision_message_ts: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    project: Mapped[str | None] = mapped_column(String(200), nullable=True)
    involved_user_ids: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agenda_item: Mapped["AgendaItem"] = relationship()


class FAQAnswer(Base):
    """FAQ and canonical answers derived from threads."""

    __tablename__ = "faq_answers"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=generate_uuid
    )
    workspace_id: Mapped[str] = mapped_column(String(50), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    source_thread_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_channel_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_message_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Metadata
    tags: Mapped[str | None] = mapped_column(String(500), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    is_canonical: Mapped[bool] = mapped_column(default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
