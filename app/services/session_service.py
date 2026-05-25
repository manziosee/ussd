"""
Redis-backed session, profile, AI-cache, rate-limit, and user-existence services.

Key namespaces
──────────────
  ussd:session:{session_id}           USSD session data          TTL = SESSION_TTL (5 min)
  ussd:profile:{phone_number}         Cached user profile        TTL = 1 hour
  ussd:ai:{category}:{question_hash}  Cached AI response         TTL = AI_CACHE_TTL (24 h)
  ussd:rate:{phone_number}:{hour}     Request counter            TTL = 1 hour (auto-expire)
  ussd:exists:{phone_number}          User-row-exists flag       TTL = 24 hours
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Max AI queries a single phone number may make per hour
RATE_LIMIT_PER_HOUR = 50

# Module-level Redis pool — initialised once at app startup
_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _redis


async def init_redis() -> None:
    """
    Connect to Redis. If the server is unreachable (e.g. Docker not running),
    fall back to an in-memory fakeredis instance so the app still works in dev.
    """
    global _redis
    try:
        client = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
        )
        await client.ping()
        _redis = client
        log.info("Redis connected at %s", settings.redis_url)
    except Exception as exc:
        log.warning(
            "Redis unavailable (%s) — falling back to in-memory fakeredis. "
            "Sessions and cache will reset on restart.",
            exc,
        )
        try:
            import fakeredis.aioredis as fakeredis_aio
            _redis = fakeredis_aio.FakeRedis(decode_responses=True)
            await _redis.ping()
            log.info("fakeredis in-memory store initialised (dev mode).")
        except ImportError:
            raise RuntimeError(
                "Redis is not running and 'fakeredis' is not installed. "
                "Either start Redis or run: pip install fakeredis"
            )


async def close_redis() -> None:
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
        log.info("Redis connection closed.")


# ── USSD Session ─────────────────────────────────────────────────────────────

def _session_key(session_id: str) -> str:
    return f"ussd:session:{session_id}"


async def get_session(session_id: str, phone_number: str) -> dict[str, Any]:
    """Return existing session or create a fresh one."""
    r = get_redis()
    raw = await r.get(_session_key(session_id))
    if raw:
        return json.loads(raw)
    session: dict[str, Any] = {
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


# ── User profile cache ────────────────────────────────────────────────────────

def _profile_key(phone: str) -> str:
    return f"ussd:profile:{phone}"


async def get_cached_profile(phone_number: str) -> dict[str, Any] | None:
    r = get_redis()
    raw = await r.get(_profile_key(phone_number))
    return json.loads(raw) if raw else None


async def cache_profile(phone_number: str, profile: dict) -> None:
    r = get_redis()
    await r.setex(_profile_key(phone_number), 3600, json.dumps(profile))


async def clear_profile_cache(phone_number: str) -> None:
    r = get_redis()
    await r.delete(_profile_key(phone_number))


# ── AI response cache ─────────────────────────────────────────────────────────

def _ai_key(category: str, question: str) -> str:
    normalised = question.lower().strip()[:120]
    return f"ussd:ai:{category}:{normalised}"


async def get_cached_ai_response(category: str, question: str) -> str | None:
    r = get_redis()
    return await r.get(_ai_key(category, question))


async def cache_ai_response(category: str, question: str, response: str) -> None:
    r = get_redis()
    await r.setex(_ai_key(category, question), settings.ai_cache_ttl, response)


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _rate_key(phone: str) -> str:
    hour = datetime.now(timezone.utc).strftime("%Y%m%d%H")
    return f"ussd:rate:{phone}:{hour}"


async def check_rate_limit(phone_number: str) -> tuple[bool, int]:
    """
    Increment the per-phone hourly counter.
    Returns (allowed: bool, remaining: int).
    """
    r = get_redis()
    key = _rate_key(phone_number)
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 3600)  # auto-expire at end of hour
    remaining = max(0, RATE_LIMIT_PER_HOUR - count)
    allowed = count <= RATE_LIMIT_PER_HOUR
    if not allowed:
        log.warning("Rate limit exceeded for %s (%d this hour)", phone_number, count)
    return allowed, remaining


# ── User-exists flag (avoids a DB SELECT on every USSD request) ───────────────

def _exists_key(phone: str) -> str:
    return f"ussd:exists:{phone}"


async def user_exists_cached(phone_number: str) -> bool:
    r = get_redis()
    return await r.exists(_exists_key(phone_number)) == 1


async def mark_user_exists(phone_number: str) -> None:
    r = get_redis()
    await r.setex(_exists_key(phone_number), 86400, "1")
