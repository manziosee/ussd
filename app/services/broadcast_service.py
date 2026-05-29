"""
Daily tip broadcast service — sends one AI-generated tip per day via SMS to all
users who have opted in via Account → Daily tips.

Designed for multi-worker safety: a Redis distributed lock (SETNX, 24-h TTL)
ensures only one worker broadcasts per day, even when multiple uvicorn workers
or container replicas are running.

Trigger
───────
  POST /cron/daily-tips?secret=<CRON_SECRET>

Call this endpoint once per day at 07:00 EAT (04:00 UTC) from:
  • Railway cron jobs     (Settings → Cron Jobs)
  • GitHub Actions        (schedule: cron: '0 4 * * *')
  • Render cron service
  • Any Linux crontab     (0 4 * * * curl -X POST ...)
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select

from ..database import AsyncSessionLocal
from ..models.user import User
from . import ai_service, session_service, sms_service

log = logging.getLogger(__name__)

# ── Category labels for SMS header ────────────────────────────────────────────

_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "business":  "Business Tip",
        "farming":   "Farming Tip",
        "health":    "Health Tip",
        "education": "Study Tip",
        "general":   "Daily Tip",
    },
    "rw": {
        "business":  "Inama y'Ubucuruzi",
        "farming":   "Inama y'Ubuhinzi",
        "health":    "Inama y'Ubuzima",
        "education": "Inama y'Amasomo",
        "general":   "Inama ya Buri Munsi",
    },
}

def _footers() -> dict[str, str]:
    from ..config import get_settings
    code = get_settings().ussd_shortcode
    return {
        "en": f"Dial {code} for more AI tips.",
        "rw": f"Vugisha {code} kubona inama nyinshi.",
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _profession_to_category(profession: str | None) -> str | None:
    """Map user profession to the most relevant tip category."""
    if not profession:
        return None
    return {
        "farmer":         "farming",
        "student":        "education",
        "business owner": "business",
    }.get(profession)


def _format_tip_sms(category: str, tip: str, language: str) -> str:
    lang_labels = _LABELS.get(language, _LABELS["en"])
    label  = lang_labels.get(category, "SmartAssist Tip")
    footer = _footers().get(language, _footers()["en"])
    return f"SmartAssist - {label}\n\n{tip}\n\n{footer}"


async def _get_daily_tip(category: str, language: str) -> str | None:
    """
    Generate a fresh daily tip for the given category.

    The date is embedded in the question so each day gets a new Redis cache key
    (and thus a new AI-generated tip, not the same cached answer every day).
    """
    today = date.today().isoformat()
    question = (
        f"Daily tip for {today}: Give one practical, specific, and actionable "
        f"{category} tip that a person in rural Africa can apply today."
    )
    try:
        result = await ai_service.get_ai_response(
            question=question,
            category=category,
            phone_number="broadcast",
            language=language,
        )
        return result.text
    except Exception as exc:
        log.error("Failed to generate daily tip [%s/%s]: %s", category, language, exc)
        return None


# ── Main broadcast function ────────────────────────────────────────────────────

async def broadcast_daily_tips() -> dict:
    """
    Send one daily tip SMS to every opted-in user.

    Returns a summary dict: {"sent": int, "failed": int, "total": int, "skipped": bool}

    Uses a Redis distributed lock to prevent duplicate runs in multi-worker setups.
    """
    r = session_service.get_redis()
    today = date.today().isoformat()
    lock_key = f"ussd:cron:daily_tips:{today}"

    # Distributed lock: only one worker broadcasts per calendar day
    acquired = await r.setnx(lock_key, "running")
    if not acquired:
        log.info("Daily tips: lock already held for %s — skipping duplicate run.", today)
        return {"skipped": True, "sent": 0, "failed": 0, "total": 0}
    await r.expire(lock_key, 86400)  # lock expires at end of day

    sent   = 0
    failed = 0

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(User).where(User.daily_tips_enabled == True)  # noqa: E712
            )
            users: list[User] = result.scalars().all()

        total = len(users)
        log.info("Daily tips broadcast starting: %d opted-in users.", total)

        # Cache one tip per (category, language) pair to avoid redundant AI calls
        tip_cache: dict[tuple[str, str], str | None] = {}

        for user in users:
            category = (
                user.daily_tip_category
                or _profession_to_category(user.profession)
                or "general"
            )
            language = user.language or "en"

            cache_key = (category, language)
            if cache_key not in tip_cache:
                tip_cache[cache_key] = await _get_daily_tip(category, language)

            tip = tip_cache[cache_key]
            if not tip:
                log.warning("No tip available for %s/%s — skipping %s", category, language, user.phone_number)
                failed += 1
                continue

            message = _format_tip_sms(category, tip, language)
            success = await sms_service.send_sms(user.phone_number, message)
            if success:
                sent += 1
            else:
                failed += 1

        log.info(
            "Daily tips broadcast complete: sent=%d failed=%d total=%d",
            sent, failed, total,
        )
        return {"skipped": False, "sent": sent, "failed": failed, "total": total}

    except Exception as exc:
        log.exception("Daily tips broadcast error: %s", exc)
        # Release lock on unexpected error so it can retry
        await r.delete(lock_key)
        return {"skipped": False, "sent": sent, "failed": failed, "total": 0, "error": str(exc)}
