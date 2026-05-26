"""
Cron trigger endpoints — called by an external scheduler (Railway, GitHub Actions, etc.)

All endpoints require  ?secret=<CRON_SECRET>  in the query string.
Leave CRON_SECRET empty in .env to disable the endpoints entirely.

Recommended schedule
────────────────────
  POST /cron/daily-tips   →  every day at 04:00 UTC (07:00 EAT)

GitHub Actions example (.github/workflows/daily_tips.yml):
  on:
    schedule:
      - cron: "0 4 * * *"
  jobs:
    broadcast:
      runs-on: ubuntu-latest
      steps:
        - run: |
            curl -sf -X POST \\
              "${{ secrets.APP_URL }}/cron/daily-tips?secret=${{ secrets.CRON_SECRET }}"
"""
import logging

from fastapi import APIRouter, HTTPException, Query

from ..config import get_settings
from ..services.broadcast_service import broadcast_daily_tips

log = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/cron", tags=["Cron"])


def _check_secret(secret: str) -> None:
    """Raise HTTP 403 if the cron secret is wrong or not configured."""
    if not settings.cron_secret:
        raise HTTPException(status_code=403, detail="Cron endpoint is disabled. Set CRON_SECRET in .env.")
    if secret != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Invalid cron secret.")


@router.post(
    "/daily-tips",
    summary="Broadcast daily tip SMS to all opted-in users",
    description=(
        "Triggers the daily tip broadcast. "
        "Protected by `?secret=<CRON_SECRET>`. "
        "A Redis distributed lock prevents duplicate runs if called more than once per day."
    ),
)
async def trigger_daily_tips(secret: str = Query(default="")) -> dict:
    """
    Send one daily tip SMS to every user who opted in via Account → Daily tips.

    Returns:
        {"sent": N, "failed": N, "total": N}   — broadcast ran
        {"skipped": true, ...}                  — already sent today
    """
    _check_secret(secret)
    log.info("Cron: daily-tips broadcast triggered via endpoint.")
    return await broadcast_daily_tips()
