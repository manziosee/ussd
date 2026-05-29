"""
Jasmin HTTP API client.

Jasmin exposes a REST-ish HTTP interface (jHttpApi) on port 1401.
We POST form-encoded data and parse the plain-text response.

Request
───────
POST http://jasmin-host:1401/send
Content-Type: application/x-www-form-urlencoded

  username   Jasmin admin username
  password   Jasmin admin password
  to         Destination in E.164  (+250788000001)
  content    Message text (UTF-8)
  from       Sender ID (optional, ≤11 alphanumeric chars)
  smppconn   Jasmin connector CID to use (optional — lets Jasmin route if absent)
  coding     0 = GSM7 (default, 160 chars/SMS)
             8 = UCS-2 (70 chars/SMS, needed for Arabic/CJK/Kinyarwanda accents)

Response  (plain text)
────────
  Success "01234-5678-uuid"   → message accepted, returns message-id
  Error "No route found"      → Jasmin couldn't route the message
  Error "Authentication error"→ wrong username/password

Reference: https://docs.jasminsms.com/en/latest/apis/rest/index.html
"""
from __future__ import annotations

import logging
import re

import httpx

from ..config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

_SUCCESS_RE = re.compile(r'^Success\s+"([^"]+)"', re.IGNORECASE)
_ERROR_RE   = re.compile(r'^Error\s+"([^"]+)"',   re.IGNORECASE)


def _detect_coding(text: str) -> str:
    """Return '0' (GSM7) or '8' (UCS-2) based on whether text needs Unicode."""
    try:
        text.encode("ascii")
        return "0"
    except UnicodeEncodeError:
        pass
    # Check if all chars fit in GSM7 extended set
    _GSM7 = set(
        "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
        "0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijk"
        "lmnopqrstuvwxyzäöñüà"
    )
    if all(c in _GSM7 for c in text):
        return "0"
    return "8"


async def send_message(
    to: str,
    message: str,
    sender_id: str | None = None,
    connector: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Send one SMS via Jasmin's HTTP API.

    Returns:
        (success: bool, message_id: str | None, error: str | None)
    """
    payload: dict[str, str] = {
        "username": settings.jasmin_username,
        "password": settings.jasmin_password,
        "to":       to,
        "content":  message,
        "coding":   _detect_coding(message),
    }
    if sender_id:
        payload["from"] = sender_id[:11]   # SMPP limit
    if connector:
        payload["smppconn"] = connector

    try:
        async with httpx.AsyncClient(timeout=settings.jasmin_timeout) as client:
            resp = await client.post(
                settings.jasmin_send_url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            body = resp.text.strip()
            log.debug("Jasmin raw response [%d]: %s", resp.status_code, body)

            if m := _SUCCESS_RE.match(body):
                message_id = m.group(1)
                log.info("Jasmin accepted → %s  id=%s  connector=%s", to, message_id, connector or "auto")
                return True, message_id, None

            if m := _ERROR_RE.match(body):
                error = m.group(1)
                log.warning("Jasmin rejected [%s]: %s", to, error)
                return False, None, error

            # Unexpected response format
            log.error("Jasmin unexpected response: %r", body)
            return False, None, f"Unexpected Jasmin response: {body[:120]}"

    except httpx.TimeoutException:
        msg = f"Jasmin timeout after {settings.jasmin_timeout}s"
        log.error(msg)
        return False, None, msg
    except httpx.ConnectError as exc:
        msg = f"Cannot reach Jasmin at {settings.jasmin_send_url}: {exc}"
        log.error(msg)
        return False, None, msg
    except Exception as exc:
        log.error("Jasmin client error: %s", exc)
        return False, None, str(exc)


async def health_check() -> bool:
    """Ping Jasmin's HTTP API. Returns True if reachable and responding."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            # Send a request with bad credentials — Jasmin still replies fast
            resp = await client.post(
                settings.jasmin_send_url,
                data={"username": "healthcheck", "password": "x", "to": "+1", "content": "ping"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            # Any response (even auth error) means Jasmin is alive
            return resp.status_code < 500
    except Exception:
        return False
