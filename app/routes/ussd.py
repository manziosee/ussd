"""
USSD webhook — Africa's Talking sends form-encoded POST requests here.

Security layers
───────────────
1. URL token guard  — AT is configured to POST to /ussd?token=<AT_WEBHOOK_TOKEN>.
   Requests missing or mismatching the token are rejected with 403.
   (Skipped automatically when AT_WEBHOOK_TOKEN is empty — safe for sandbox.)

2. HMAC-SHA256 signature — AT signs every callback body with your API key.
   The resulting hex digest is sent as the  X-AT-Hash  header.
   We verify it before processing.  If AT_API_KEY is empty (sandbox without
   signing), the check is skipped.

Important — stream-consumed fix
────────────────────────────────
FastAPI's Form(...) dependencies consume the request stream before the handler
body runs, making a subsequent request.body() raise "Stream consumed".
Fix: avoid Form() entirely — call request.body() FIRST (Starlette caches the
result in self._body), then call request.form() which reuses that cache.

Response format
───────────────
  CON <text>  →  continue session (user sees a menu, can respond)
  END <text>  →  end session     (user sees final message)
"""
import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import verify_at_token
from ..config import get_settings
from ..database import get_db
from ..schemas.ussd import SimulateRequest
from ..services.menu_service import process_ussd

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


# ── HMAC helper ───────────────────────────────────────────────────────────────

def _verify_at_signature(body: bytes, received_hash: str | None) -> bool:
    """
    Verify the X-AT-Hash header Africa's Talking includes on every callback.

    Returns True when:
      - AT_API_KEY is not configured (dev / sandbox — skip check)
      - X-AT-Hash is absent and we are in sandbox mode
      - The computed HMAC-SHA256 digest matches the received header
    Returns False only when a hash is present but wrong.
    """
    if not settings.at_api_key:
        return True                                   # no key → skip (dev)
    if not received_hash:
        return settings.at_environment == "sandbox"   # absent = OK in sandbox

    expected = hmac.new(
        key=settings.at_api_key.encode(),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, received_hash.lower())


# ── Main USSD webhook ─────────────────────────────────────────────────────────

@router.post(
    "/ussd",
    response_class=PlainTextResponse,
    summary="Africa's Talking USSD webhook",
    tags=["USSD"],
    dependencies=[Depends(verify_at_token)],   # layer 1: URL token guard
)
async def ussd_callback(
    request: Request,
    x_at_hash: str | None = Header(default=None, alias="X-AT-Hash"),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Receives USSD callbacks from Africa's Talking.
    Returns a plain-text CON or END response.
    """
    # 1. Cache raw body FIRST — must happen before request.form()
    raw_body = await request.body()

    # 2. HMAC signature verification (layer 2)
    if not _verify_at_signature(raw_body, x_at_hash):
        log.warning("Invalid AT signature | hash=%s", x_at_hash)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid request signature.",
        )

    # 3. Parse form fields — Starlette reuses the cached body from step 1
    form         = await request.form()
    session_id   = str(form.get("sessionId",   ""))
    phone_number = str(form.get("phoneNumber", ""))
    text         = str(form.get("text",        ""))

    if not session_id or not phone_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required fields: sessionId, phoneNumber",
        )

    log.info("USSD | session=%s phone=%s text=%r", session_id, phone_number, text)

    # 4. Process USSD
    try:
        response = await process_ussd(
            session_id=session_id,
            phone_number=phone_number,
            text=text,
            db=db,
        )
    except Exception as exc:
        log.exception("Unhandled error in USSD handler: %s", exc)
        response = "END Sorry, a system error occurred. Please try again."

    log.info("USSD → %r", response[:80])
    return response


# ── Local simulator (no auth required) ───────────────────────────────────────

@router.post(
    "/simulate",
    response_class=PlainTextResponse,
    summary="Local USSD simulator — no AT credentials needed",
    tags=["Simulator"],
)
async def simulate_ussd(
    body: SimulateRequest,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Simulate a full USSD session locally via JSON. No auth needed."""
    log.info("SIM | session=%s phone=%s text=%r", body.session_id, body.phone_number, body.text)
    try:
        response = await process_ussd(
            session_id=body.session_id,
            phone_number=body.phone_number,
            text=body.text,
            db=db,
        )
    except Exception as exc:
        log.exception("Simulator error: %s", exc)
        response = "END System error."
    return response
