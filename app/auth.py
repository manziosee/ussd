"""
Security dependencies used across the application.

Admin API key
─────────────
All /admin/* routes require the header:
    X-Admin-Key: <ADMIN_API_KEY from .env>

Returns HTTP 401 if the key is missing or wrong.
Returns HTTP 503 if ADMIN_API_KEY is not configured in .env (safe default —
the admin API is inaccessible until an operator explicitly sets the key).

Africa's Talking webhook token
───────────────────────────────
AT is configured to POST to  /ussd?token=<AT_WEBHOOK_TOKEN>.
Requests that omit or mismatch the token get HTTP 403.
If AT_WEBHOOK_TOKEN is empty in .env the guard is skipped — useful in
sandbox/development where the callback URL is managed by ngrok and changes
frequently.
"""
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import APIKeyHeader

from .config import get_settings

settings = get_settings()

# ── Admin API key ─────────────────────────────────────────────────────────────

_admin_key_header = APIKeyHeader(name="X-Admin-Key", auto_error=False)


async def require_admin_key(
    api_key: str | None = Depends(_admin_key_header),
) -> str:
    """
    FastAPI dependency — inject into any route that should be admin-only.

    Usage:
        @router.get("/stats", dependencies=[Depends(require_admin_key)])
    """
    if not settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API is disabled. Set ADMIN_API_KEY in .env to enable it.",
        )
    if api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Admin-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


# ── Africa's Talking webhook token ────────────────────────────────────────────

async def verify_at_token(
    token: str = Query(default="", description="AT webhook secret token"),
) -> None:
    """
    FastAPI dependency — verify the ?token= query param on the /ussd webhook.

    Skip verification when AT_WEBHOOK_TOKEN is not configured (dev / sandbox).
    Reject with HTTP 403 when the token is wrong in production.
    """
    if not settings.at_webhook_token:
        # Token guard disabled — OK for local dev and sandbox
        return
    if token != settings.at_webhook_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid webhook token.",
        )
