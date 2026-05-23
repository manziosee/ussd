"""
Africa's Talking SMS service.

Used as USSD fallback: when an AI response is too long for USSD,
we send the full answer via SMS so the user still gets complete information.
"""
import logging

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Africa's Talking API endpoints
_AT_SMS_SANDBOX = "https://api.sandbox.africastalking.com/version1/messaging"
_AT_SMS_PROD = "https://api.africastalking.com/version1/messaging"


def _sms_url() -> str:
    return _AT_SMS_SANDBOX if settings.at_environment == "sandbox" else _AT_SMS_PROD


async def send_sms(phone_number: str, message: str) -> bool:
    """
    Send an SMS via Africa's Talking.
    Returns True on success, False on failure (never raises).
    """
    if not settings.sms_enabled:
        log.debug("SMS disabled — skipping send to %s", phone_number)
        return False

    if not settings.at_api_key:
        log.warning("AT_API_KEY not set — cannot send SMS")
        return False

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _sms_url(),
                data={
                    "username": settings.at_username,
                    "to": phone_number,
                    "message": message,
                    "from": settings.at_shortcode,
                },
                headers={
                    "apiKey": settings.at_api_key,
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            status = data.get("SMSMessageData", {}).get("Recipients", [{}])[0].get("status", "unknown")
            if status == "Success":
                log.info("SMS sent to %s", phone_number)
                return True
            else:
                log.warning("SMS to %s failed: %s", phone_number, data)
                return False

    except Exception as exc:
        log.error("SMS error to %s: %s", phone_number, exc)
        return False


def format_sms_response(category: str, question: str, answer: str) -> str:
    """Format a full AI answer for SMS delivery."""
    cat_labels = {
        "business": "Business Tip",
        "farming": "Farming Tip",
        "health": "Health Info",
        "education": "Study Help",
        "general": "AI Answer",
    }
    label = cat_labels.get(category, "SmartAssist")
    return (
        f"SmartAssist - {label}\n\n"
        f"Q: {question[:100]}\n\n"
        f"A: {answer}\n\n"
        f"Dial *384*72275# for more tips."
    )
