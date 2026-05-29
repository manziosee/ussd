"""
SmartAssist SMS Gateway — standalone microservice.

Architecture
────────────
  Main App  →  POST /sms/send  →  This gateway  →  Jasmin jHttpApi  →  SMPP  →  Telecom

This service sits between the main USSD app and Jasmin, providing:
  • E.164 phone number validation
  • Country-code → SMPP connector routing
  • Unicode detection (GSM7 vs UCS-2 coding)
  • Health check with Jasmin reachability
  • Bulk send endpoint for daily tip broadcasts

Run locally:
  uvicorn sms_gateway.main:app --port 8001 --reload

Docker:
  See docker-compose.yml — service name: sms-gateway, port: 8001
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .routes.sms import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
settings = get_settings()

app = FastAPI(
    title="SmartAssist SMS Gateway",
    version="1.0.0",
    description=(
        "Internal SMS microservice: validates messages, routes by country code, "
        "and delivers via Jasmin SMPP gateway to telecom operators."
    ),
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["Info"])
async def root():
    return JSONResponse({
        "service": "SmartAssist SMS Gateway",
        "version": "1.0.0",
        "jasmin": f"{settings.jasmin_host}:{settings.jasmin_http_port}",
        "docs": "/docs",
    })


@app.on_event("startup")
async def on_startup():
    from .services.jasmin_client import health_check
    ok = await health_check()
    if ok:
        log.info("✓ SMS Gateway ready — Jasmin reachable at %s:%d",
                 settings.jasmin_host, settings.jasmin_http_port)
    else:
        log.warning(
            "⚠  SMS Gateway started but Jasmin is NOT reachable at %s:%d — "
            "SMS sending will fail until Jasmin is available.",
            settings.jasmin_host, settings.jasmin_http_port,
        )
