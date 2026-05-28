"""
Tests for admin API routes.

Strategy
────────
- FastAPI app is tested via httpx.AsyncClient + ASGITransport (real HTTP layer).
- DB and Redis are fully mocked; startup I/O (init_redis, create_tables,
  seed_knowledge_cache) is patched so no external services are needed.
- Admin auth dependency is overridden with a no-op so every request passes.
- Each test that needs a specific DB response overrides `mock_db.execute`
  locally — other tests rely on the default (scalar_one=0, scalars=[]).
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient, ASGITransport

ADMIN_KEY = "test-admin-key-123"


# ── Shared mock-DB factory ─────────────────────────────────────────────────────

def make_admin_db():
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=0)
    result.scalar_one_or_none = MagicMock(return_value=None)
    result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
    result.all = MagicMock(return_value=[])

    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    return db


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_db():
    return make_admin_db()


@pytest.fixture
async def admin_client(admin_db, mock_redis):
    """Async HTTP client with admin auth bypass and mocked DB + startup."""
    from app.main import app
    from app.auth import require_admin_key
    from app.database import get_db

    async def _db():
        yield admin_db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[require_admin_key] = lambda: ADMIN_KEY

    try:
        with (
            patch("app.main.create_tables",        new_callable=AsyncMock),
            patch("app.main.seed_knowledge_cache", new_callable=AsyncMock),
            patch("app.main.init_redis",           new_callable=AsyncMock),
            patch("app.main.close_redis",          new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                yield client
    finally:
        app.dependency_overrides.clear()


# ── Auth guard ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auth_required_returns_401_or_503(mock_redis):
    """Without the admin key, /admin/stats must return 401 or 503."""
    from app.main import app
    from app.database import get_db

    async def _db():
        yield make_admin_db()

    app.dependency_overrides[get_db] = _db

    try:
        with (
            patch("app.main.create_tables",        new_callable=AsyncMock),
            patch("app.main.seed_knowledge_cache", new_callable=AsyncMock),
            patch("app.main.init_redis",           new_callable=AsyncMock),
            patch("app.main.close_redis",          new_callable=AsyncMock),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get("/admin/stats")
                assert r.status_code in (401, 503)
    finally:
        app.dependency_overrides.clear()


# ── /admin/stats ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_shape(admin_client):
    r = await admin_client.get("/admin/stats")
    assert r.status_code == 200
    data = r.json()
    assert "total_users" in data
    assert "total_interactions" in data
    assert "cache_hit_rate" in data
    assert "sms_sent" in data
    assert isinstance(data["interactions_by_category"], dict)


@pytest.mark.asyncio
async def test_stats_all_zeros(admin_client):
    r = await admin_client.get("/admin/stats")
    data = r.json()
    assert data["total_users"] == 0
    assert data["total_interactions"] == 0
    assert data["cache_hit_rate"] == 0.0


# ── /admin/interactions ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_interactions_empty(admin_client):
    r = await admin_client.get("/admin/interactions")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_interactions_category_filter(admin_client):
    r = await admin_client.get("/admin/interactions?category=business")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── /admin/users ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users_empty(admin_client):
    r = await admin_client.get("/admin/users")
    assert r.status_code == 200
    assert r.json() == []


# ── /admin/market-prices ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_market_prices_empty(admin_client):
    r = await admin_client.get("/admin/market-prices")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_upsert_market_price_creates_row(admin_client, admin_db):
    """PUT creates a new row when none exists; verifies db.add and db.commit called."""
    # scalar_one_or_none already returns None (no existing row)
    payload = {"district": "kigali", "crop": "Maize", "unit": "kg", "price_rwf": 400}

    # After db.refresh we need the new_row to look like a valid MarketPriceOut.
    # Simulate by capturing the added object and setting its attributes.
    added_rows: list = []
    original_add = admin_db.add

    def _capture_add(obj):
        obj.id = 1
        obj.updated_at = datetime(2026, 5, 28, tzinfo=timezone.utc)
        added_rows.append(obj)
        return original_add(obj)

    admin_db.add = _capture_add

    r = await admin_client.put("/admin/market-prices", json=payload)
    assert r.status_code == 200
    assert len(added_rows) == 1
    admin_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_upsert_market_price_updates_existing(admin_client, admin_db):
    """PUT updates an existing row when (district, crop) already exists."""
    existing = MagicMock()
    existing.id = 5
    existing.district = "kigali"
    existing.crop = "Maize"
    existing.unit = "kg"
    existing.price_rwf = 350
    existing.updated_by = None
    existing.updated_at = datetime(2026, 5, 1, tzinfo=timezone.utc)

    result_with_row = MagicMock()
    result_with_row.scalar_one_or_none = MagicMock(return_value=existing)
    admin_db.execute = AsyncMock(return_value=result_with_row)

    payload = {"district": "kigali", "crop": "Maize", "unit": "kg", "price_rwf": 420}
    r = await admin_client.put("/admin/market-prices", json=payload)
    assert r.status_code == 200
    admin_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delete_market_price_not_found(admin_client):
    r = await admin_client.delete("/admin/market-prices/999")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_market_price_ok(admin_client, admin_db):
    row = MagicMock()
    row.id = 3

    result_with_row = MagicMock()
    result_with_row.scalar_one_or_none = MagicMock(return_value=row)
    admin_db.execute = AsyncMock(return_value=result_with_row)

    r = await admin_client.delete("/admin/market-prices/3")
    assert r.status_code == 200
    assert r.json() == {"deleted": 3}
    admin_db.delete.assert_awaited_once_with(row)
    admin_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_bulk_upsert_market_prices(admin_client, admin_db):
    """POST /admin/market-prices/bulk accepts a list and calls commit once."""
    payload = [
        {"district": "kigali",  "crop": "Maize", "unit": "kg", "price_rwf": 400},
        {"district": "musanze", "crop": "Beans", "unit": "kg", "price_rwf": 700},
    ]

    added: list = []
    original_add = admin_db.add

    def _capture(obj):
        obj.id = len(added) + 1
        obj.updated_at = datetime(2026, 5, 28, tzinfo=timezone.utc)
        added.append(obj)
        return original_add(obj)

    admin_db.add = _capture

    r = await admin_client.post("/admin/market-prices/bulk", json=payload)
    assert r.status_code == 200
    admin_db.commit.assert_awaited()


# ── /admin/feedback ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_feedback_empty(admin_client, admin_db):
    result_empty = MagicMock()
    result_empty.all = MagicMock(return_value=[])
    admin_db.execute = AsyncMock(return_value=result_empty)

    r = await admin_client.get("/admin/feedback")
    assert r.status_code == 200
    assert r.json() == {}


@pytest.mark.asyncio
async def test_feedback_with_data(admin_client, admin_db):
    """Returns aggregated counts per category."""
    row1 = MagicMock()
    row1.category = "business"
    row1.rating = 1
    row1.cnt = 10

    row2 = MagicMock()
    row2.category = "business"
    row2.rating = -1
    row2.cnt = 2

    result_with_rows = MagicMock()
    result_with_rows.all = MagicMock(return_value=[row1, row2])
    admin_db.execute = AsyncMock(return_value=result_with_rows)

    r = await admin_client.get("/admin/feedback")
    assert r.status_code == 200
    data = r.json()
    assert "business" in data
    assert data["business"]["helpful"] == 10
    assert data["business"]["not_helpful"] == 2
    assert data["business"]["total"] == 12
    assert data["business"]["satisfaction_pct"] == round(10 / 12 * 100, 1)


# ── /admin/dashboard (HTML) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dashboard_returns_html(admin_client):
    r = await admin_client.get("/admin/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "SmartAssist" in r.text
