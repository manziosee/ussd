"""
Redis-backed session, profile, AI-cache, rate-limit, and user-existence services.

Key namespaces
──────────────
  ussd:session:{session_id}               USSD session data           TTL = SESSION_TTL (5 min)
  ussd:profile:{phone_number}             Cached user profile         TTL = 1 hour
  ussd:ai:{category}:{question_hash}      Cached AI response          TTL = AI_CACHE_TTL (24 h)
  ussd:rate:{phone_number}:{hour}         Request counter             TTL = 1 hour (auto-expire)
  ussd:exists:{phone_number}              User-row-exists flag        TTL = 24 hours
  ussd:dedup:{session_id}:{text_hash}     Dedup cache for AT retries  TTL = 30 s
  ussd:resume:{phone_number}              Last CON position for resume TTL = 10 min
  ussd:resume_offered:{session_id}        Flag: resume prompt shown    TTL = SESSION_TTL
  ussd:lastresponse:{phone}:{category}    Last AI response text        TTL = SESSION_TTL (5 min)
"""
from __future__ import annotations

import hashlib
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

# Dedup window (seconds) — covers Africa's Talking retry delay
_DEDUP_TTL = 30

# How long to remember a dropped-session resume position (seconds)
_RESUME_TTL = 600   # 10 minutes

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


# ── USSD Session ──────────────────────────────────────────────────────────────

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


# ── User-exists flag ──────────────────────────────────────────────────────────

def _exists_key(phone: str) -> str:
    return f"ussd:exists:{phone}"


async def user_exists_cached(phone_number: str) -> bool:
    r = get_redis()
    return await r.exists(_exists_key(phone_number)) == 1


async def mark_user_exists(phone_number: str) -> None:
    r = get_redis()
    await r.setex(_exists_key(phone_number), 86400, "1")


# ── Webhook deduplication ─────────────────────────────────────────────────────
# Africa's Talking retries the same (sessionId, text) if our response is slow.
# We cache the response for _DEDUP_TTL seconds so retries get the exact same reply.

def _dedup_key(session_id: str, text: str) -> str:
    # Hash text so the key is short and safe for any input
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
    return f"ussd:dedup:{session_id}:{text_hash}"


async def get_dedup_response(session_id: str, text: str) -> str | None:
    """Return the cached response for this (session, text) pair, or None."""
    r = get_redis()
    return await r.get(_dedup_key(session_id, text))


async def store_dedup_response(session_id: str, text: str, response: str) -> None:
    """Cache the response so AT retries within the next 30 s get the same reply."""
    r = get_redis()
    await r.setex(_dedup_key(session_id, text), _DEDUP_TTL, response)


# ── Session resume after drop ─────────────────────────────────────────────────
# When a CON response is sent we save the current text input as "resume position".
# If the user's session drops (poor signal) and they re-dial, they are offered
# the chance to jump straight back to where they were.

def _resume_key(phone: str) -> str:
    return f"ussd:resume:{phone}"


async def get_resume_position(phone_number: str) -> dict | None:
    """Return {text, label} saved from the last CON response, or None."""
    r = get_redis()
    raw = await r.get(_resume_key(phone_number))
    return json.loads(raw) if raw else None


async def set_resume_position(phone_number: str, text: str, label: str) -> None:
    """Save current menu position so the user can resume after a session drop."""
    r = get_redis()
    data = {"text": text, "label": label}
    await r.setex(_resume_key(phone_number), _RESUME_TTL, json.dumps(data))


async def clear_resume_position(phone_number: str) -> None:
    """Clear the saved position (call on END response or explicit main-menu return)."""
    r = get_redis()
    await r.delete(_resume_key(phone_number))


# ── Resume-offered flag ───────────────────────────────────────────────────────
# Tracks whether the "Resume? 1.Yes 2.No" prompt was already shown in this
# session — prevents routing collisions where "1" means both "Yes, resume"
# and "Business category".

def _resume_offered_key(session_id: str) -> str:
    return f"ussd:resume_offered:{session_id}"


async def was_resume_offered(session_id: str) -> bool:
    r = get_redis()
    return await r.exists(_resume_offered_key(session_id)) == 1


async def mark_resume_offered(session_id: str) -> None:
    r = get_redis()
    await r.setex(_resume_offered_key(session_id), settings.session_ttl, "1")


async def clear_resume_offered(session_id: str) -> None:
    r = get_redis()
    await r.delete(_resume_offered_key(session_id))


# ── Last AI response cache (for "Tell me more" / "More detail" follow-up) ─────
# Stores the most recent AI response text per (phone, category) so the follow-up
# call can pass it as context without re-fetching from DB or the full AI cache.

def _last_response_key(phone: str, category: str) -> str:
    return f"ussd:lastresponse:{phone}:{category}"


async def set_last_ai_response(phone_number: str, category: str, response: str) -> None:
    """Save the last AI response for this user + category (5-min TTL = session lifetime)."""
    r = get_redis()
    await r.setex(_last_response_key(phone_number, category), 300, response)


async def get_last_ai_response(phone_number: str, category: str) -> str | None:
    """Return the most recent AI response for this user + category, or None."""
    r = get_redis()
    return await r.get(_last_response_key(phone_number, category))
