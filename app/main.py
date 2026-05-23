"""
SmartAssist USSD — FastAPI application entry point.

Startup:
  1. Connect to Redis
  2. Create DB tables (idempotent)
  3. Register routers

Shutdown:
  1. Close Redis connection
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import create_tables
from .services.session_service import init_redis, close_redis
from .routes.ussd import router as ussd_router
from .routes.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    log.info("Starting %s v%s", settings.app_name, settings.app_version)
    await init_redis()
    await create_tables()
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────────
    log.info("Shutting down…")
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "AI-powered USSD assistant for African users. "
        "Integrates with Africa's Talking for USSD/SMS and Claude (Anthropic) for AI."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow all origins for dev; tighten in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(ussd_router)
app.include_router(admin_router)


@app.get("/", tags=["Health"])
async def root():
    return {"service": settings.app_name, "version": settings.app_version, "status": "ok"}


@app.get("/health", tags=["Health"])
async def health():
    return JSONResponse({"status": "ok"})
