"""
USSD webhook — Africa's Talking sends form-encoded POST requests here.

Africa's Talking expects a plain-text response:
  CON <text>  →  continue session (user sees a menu and can respond)
  END <text>  →  end session    (user sees final message)

There is also a /simulate endpoint for local testing without real AT credentials.
"""
import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..services.menu_service import process_ussd
from ..schemas.ussd import SimulateRequest

log = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/ussd",
    response_class=PlainTextResponse,
    summary="Africa's Talking USSD webhook",
    tags=["USSD"],
)
async def ussd_callback(
    request: Request,
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(default=""),
    networkCode: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Receives USSD callbacks from Africa's Talking.
    Returns CON or END plain text.
    """
    log.info(
        "USSD | session=%s phone=%s text=%r",
        sessionId, phoneNumber, text,
    )

    try:
        response = await process_ussd(
            session_id=sessionId,
            phone_number=phoneNumber,
            text=text,
            db=db,
        )
    except Exception as exc:
        log.exception("Unhandled error in USSD handler: %s", exc)
        response = "END Sorry, a system error occurred. Please try again."

    log.info("USSD response → %r", response[:80])
    return response


@router.post(
    "/simulate",
    response_class=PlainTextResponse,
    summary="Local USSD simulator (no AT credentials needed)",
    tags=["Simulator"],
)
async def simulate_ussd(
    body: SimulateRequest,
    db: AsyncSession = Depends(get_db),
) -> str:
    """
    Simulate a USSD session locally — useful for development and testing.
    Send JSON with phone_number, text, and session_id.
    """
    log.info(
        "SIM | session=%s phone=%s text=%r",
        body.session_id, body.phone_number, body.text,
    )

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
