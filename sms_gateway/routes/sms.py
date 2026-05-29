"""
SMS API routes.

POST /sms/send       — send one message
POST /sms/send-bulk  — same message to multiple recipients
GET  /health         — gateway + Jasmin reachability
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, status

from ..config import get_settings
from ..schemas import BulkSMSRequest, BulkSMSResponse, HealthResponse, SMSRequest, SMSResponse
from ..services import jasmin_client
from ..services.routing import country_name, get_country_code, resolve_connector

log = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()


@router.post(
    "/sms/send",
    response_model=SMSResponse,
    summary="Send a single SMS via Jasmin",
)
async def send_sms(body: SMSRequest) -> SMSResponse:
    connector_map = settings.connector_map
    connector = resolve_connector(body.to, connector_map)
    country_code = get_country_code(body.to)

    sender = (body.sender_id or settings.default_sender_id)[:11]

    ok, msg_id, error = await jasmin_client.send_message(
        to=body.to,
        message=body.message,
        sender_id=sender,
        connector=connector,
    )

    log.info(
        "SMS send | to=%s country=%s connector=%s success=%s id=%s",
        body.to, country_code, connector or "auto", ok, msg_id,
    )

    return SMSResponse(
        success=ok,
        message_id=msg_id,
        connector=connector,
        country_code=country_code,
        error=error,
    )


@router.post(
    "/sms/send-bulk",
    response_model=BulkSMSResponse,
    summary="Send the same message to multiple recipients",
)
async def send_bulk(body: BulkSMSRequest) -> BulkSMSResponse:
    connector_map = settings.connector_map
    sender = (body.sender_id or settings.default_sender_id)[:11]

    async def _send(to: str) -> SMSResponse:
        connector = resolve_connector(to, connector_map)
        country_code = get_country_code(to)
        ok, msg_id, error = await jasmin_client.send_message(
            to=to,
            message=body.message,
            sender_id=sender,
            connector=connector,
        )
        return SMSResponse(
            success=ok, message_id=msg_id,
            connector=connector, country_code=country_code, error=error,
        )

    results = await asyncio.gather(*[_send(to) for to in body.recipients])
    sent   = sum(1 for r in results if r.success)
    failed = len(results) - sent

    log.info("Bulk SMS | recipients=%d sent=%d failed=%d", len(results), sent, failed)
    return BulkSMSResponse(sent=sent, failed=failed, results=list(results))


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Gateway health check — also pings Jasmin",
)
async def health() -> HealthResponse:
    jasmin_ok = await jasmin_client.health_check()
    return HealthResponse(
        status="ok" if jasmin_ok else "degraded",
        jasmin_reachable=jasmin_ok,
    )
