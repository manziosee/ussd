"""
Redis-backed USSD session manager.

A USSD session lives for SESSION_TTL seconds (default 5 min).
We also cache lightweight user profiles (language, name, profession) for 1 hour
so we don't hammer the DB on every request.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Module-level Redis pool — initialised in app lifespan
_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis


async def init_redis() -> None:
    global _redis
    _redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    await _redis.ping()
    log.info("Redis connected.")


async def close_redis() -> None:
    if _redis:
        await _redis.aclose()
        log.info("Redis connection closed.")


# ── Session helpers ──────────────────────────────────────────────────────────

def _session_key(session_id: str) -> str:
    return f"ussd:session:{session_id}"


def _profile_key(phone_number: str) -> str:
    return f"ussd:profile:{phone_number}"


async def get_session(session_id: str, phone_number: str) -> dict[str, Any]:
    """Return session dict, creating a fresh one if it doesn't exist."""
    r = get_redis()
    raw = await r.get(_session_key(session_id))
    if raw:
        return json.loads(raw)

    # New session — seed defaults
    session = {
        "session_id": session_id,
        "phone_number": phone_number,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "query_count": 0,
    }
    await _save_session(session_id, session)
    return session


async def _save_session(session_id: str, data: dict) -> None:
    r = get_redis()
    await r.setex(_session_key(session_id), settings.session_ttl, json.dumps(data))


async def increment_session_queries(session_id: str, phone_number: str) -> None:
    session = await get_session(session_id, phone_number)
    session["query_count"] = session.get("query_count", 0) + 1
    await _save_session(session_id, session)


# ── User profile cache ────────────────────────────────────────────────────────

async def get_cached_profile(phone_number: str) -> dict[str, Any] | None:
    r = get_redis()
    raw = await r.get(_profile_key(phone_number))
    return json.loads(raw) if raw else None


async def cache_profile(phone_number: str, profile: dict) -> None:
    r = get_redis()
    # Cache for 1 hour; DB is source of truth
    await r.setex(_profile_key(phone_number), 3600, json.dumps(profile))


async def clear_profile_cache(phone_number: str) -> None:
    r = get_redis()
    await r.delete(_profile_key(phone_number))


# ── AI response cache ─────────────────────────────────────────────────────────

def _ai_cache_key(category: str, question: str) -> str:
    # Normalise question for better cache hits
    normalised = question.lower().strip()[:120]
    return f"ussd:ai:{category}:{normalised}"


async def get_cached_ai_response(category: str, question: str) -> str | None:
    r = get_redis()
    return await r.get(_ai_cache_key(category, question))


async def cache_ai_response(category: str, question: str, response: str) -> None:
    r = get_redis()
    await r.setex(_ai_cache_key(category, question), settings.ai_cache_ttl, response)
