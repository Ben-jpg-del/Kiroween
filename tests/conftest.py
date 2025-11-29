"""Pytest fixtures for Kiroween tests."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from kiroween.agenda.models import Base


@pytest.fixture
async def db_session():
    """Create in-memory database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session

    await engine.dispose()


@pytest.fixture
def sample_agenda_item():
    """Sample agenda item data for testing."""
    return {
        "type": "task",
        "title": "Review PR #123",
        "description": "Review the pull request for the new feature",
        "status": "open",
        "assigned_to_user_id": "U123456",
        "assigned_to_user_name": "Alice",
        "source_channel_id": "C789",
        "source_thread_ts": "1234567890.123456",
        "priority": 1,
    }


@pytest.fixture
def mock_slack_messages():
    """Sample Slack messages for testing."""
    return [
        {
            "channel_id": "C123",
            "thread_ts": None,
            "user_id": "U001",
            "user_name": "alice",
            "text": "Can someone review PR #123?",
            "timestamp": "1234567890.000001",
            "reactions": ["eyes"],
        },
        {
            "channel_id": "C123",
            "thread_ts": None,
            "user_id": "U002",
            "user_name": "bob",
            "text": "I'll take a look at it today",
            "timestamp": "1234567890.000002",
            "reactions": ["thumbsup"],
        },
    ]
