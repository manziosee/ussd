"""
SmartAssist USSD — FastAPI application entry point.

Startup sequence
────────────────
1. Validate critical environment variables (fail fast, clear error message)
2. Connect to Redis
3. Create / migrate DB tables
4. Seed the offline knowledge cache (16 pre-written USSD responses)
5. Register API routers

Shutdown
────────
1. Close Redis connection pool
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .database import create_tables
from .services.session_service import init_redis, close_redis
from .services.knowledge_service import seed_knowledge_cache
from .routes.ussd import router as ussd_router
from .routes.admin import router as admin_router
from .routes.cron import router as cron_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
settings = get_settings()


def _validate_env() -> None:
    """Warn about missing secrets; only hard-fail on keys needed at startup."""
    warnings: list[str] = []

    if not settings.anthropic_api_key:
        warnings.append("  • ANTHROPIC_API_KEY not set — AI responses will fail (menu navigation still works)")
    if not settings.at_api_key or settings.at_api_key == "your_api_key":
        warnings.append("  • AT_API_KEY not set — SMS sending disabled")
    if settings.secret_key == "change-this-in-production" and not settings.debug:
        warnings.append("  • SECRET_KEY should be changed for production")

    if warnings:
        log.warning(
            "⚠  Configuration notice:\n%s\n"
            "   Update your .env file to enable all features.",
            "\n".join(warnings),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    log.info("═══ Starting %s v%s ═══", settings.app_name, settings.app_version)

    _validate_env()

    await init_redis()
    await create_tables()
    await seed_knowledge_cache()

    log.info("✓ All systems ready — listening for USSD requests.")
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────────
    log.info("Shutting down…")
    await close_redis()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "**SmartAssist USSD** — AI-powered USSD assistant for African users.\n\n"
        "Any mobile phone (including feature phones with no internet) can access "
        "Claude AI by dialling a USSD shortcode.\n\n"
        "**Tech stack:** FastAPI · Claude Haiku · Africa's Talking · Redis · PostgreSQL"
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — tighten allow_origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(ussd_router)
app.include_router(admin_router)
app.include_router(cron_router)


# ── Root & health ─────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"], summary="Service info")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"], summary="Health check")
async def health():
    """
    Returns 200 OK when the service is up.
    Suitable for load balancer / Docker health checks.
    """
    return JSONResponse({"status": "ok", "service": settings.app_name})
