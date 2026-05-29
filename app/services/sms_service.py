"""
SMS service — sends messages via the internal SMS Gateway microservice.

The gateway (sms_gateway/) accepts POST /sms/send and routes the message
through Jasmin → SMPP → telecom operator.  This module is a thin HTTP client
that wraps that call so the rest of the app never knows about Jasmin directly.
"""
import logging

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()


async def send_sms(phone_number: str, message: str) -> bool:
    """
    Send an SMS via the SMS Gateway.
    Returns True on success, False on any failure (never raises).
    """
    if not settings.sms_enabled:
        log.debug("SMS disabled — skipping send to %s", phone_number)
        return False

    if not settings.sms_gateway_url:
        log.warning("SMS_GATEWAY_URL not configured — cannot send SMS")
        return False

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                f"{settings.sms_gateway_url}/sms/send",
                json={"to": phone_number, "message": message},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("success"):
                log.info(
                    "SMS sent to %s | connector=%s id=%s",
                    phone_number,
                    data.get("connector", "auto"),
                    data.get("message_id", "?"),
                )
                return True
            log.warning("SMS gateway rejected send to %s: %s", phone_number, data.get("error"))
            return False

    except httpx.HTTPStatusError as exc:
        log.error("SMS gateway HTTP error %d for %s", exc.response.status_code, phone_number)
        return False
    except Exception as exc:
        log.error("SMS gateway unreachable for %s: %s", phone_number, exc)
        return False


def format_sms_response(category: str, question: str, answer: str) -> str:
    """Format a full AI answer for SMS delivery."""
    labels = {
        "business":  "Business Tip",
        "farming":   "Farming Tip",
        "health":    "Health Info",
        "education": "Study Help",
        "general":   "AI Answer",
    }
    label = labels.get(category, "SmartAssist")
    return (
        f"SmartAssist - {label}\n\n"
        f"Q: {question[:100]}\n\n"
        f"A: {answer}\n\n"
        "Dial *384*72275# for more tips."
    )
