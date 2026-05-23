"""
Pytest configuration — fixtures shared across all tests.

Strategy
────────
We mock Redis and the DB entirely so tests run without any external services.
The USSD menu logic (state machine) is tested in full; only the I/O layer is mocked.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# ── Async test mode ───────────────────────────────────────────────────────────
pytest_asyncio_mode = "auto"


# ── Patch Redis before any imports touch the module ──────────────────────────

@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Replace all Redis operations with AsyncMock so no real Redis is needed."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.exists = AsyncMock(return_value=0)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.expire = AsyncMock(return_value=True)
    redis_mock.ttl = AsyncMock(return_value=-2)  # key does not exist
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.ping = AsyncMock(return_value=True)

    import app.services.session_service as ss
    monkeypatch.setattr(ss, "_redis", redis_mock)
    return redis_mock


@pytest.fixture
def mock_db():
    """Lightweight AsyncSession mock that satisfies SQLAlchemy execute() calls."""
    db = AsyncMock()
    # scalar_one_or_none returns None by default → triggers user creation path
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def mock_ai():
    """Patch ai_service.get_ai_response to return a canned response instantly."""
    from app.services.ai_service import AIResult
    with patch(
        "app.services.menu_service.ai_service.get_ai_response",
        new_callable=AsyncMock,
        return_value=AIResult(
            text="Test AI response under 155 chars for USSD display.",
            tokens_used=42,
            from_cache=False,
        ),
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def mock_log_bg():
    """Prevent background DB logging tasks from running during tests."""
    with patch("app.services.menu_service.asyncio.create_task"):
        yield
