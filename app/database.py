"""
Async SQLAlchemy database setup with PostgreSQL (Neon-compatible).

Neon is a serverless PostgreSQL provider that requires SSL on every connection.
asyncpg handles this via connect_args={"ssl": "require"}.
The URL itself uses the postgresql+asyncpg:// scheme (no sslmode/channel_binding
query params — those are psycopg2/libpq-only).
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

log = logging.getLogger(__name__)
settings = get_settings()

# Detect Neon (or any hosted DB) by checking if URL host is not localhost
_is_remote = "localhost" not in settings.database_url and "127.0.0.1" not in settings.database_url

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,          # Neon serverless: keep pool small
    max_overflow=10,
    pool_pre_ping=True,   # drop stale connections (important for serverless)
    connect_args={"ssl": "require"} if _is_remote else {},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables():
    """Create all tables on startup (idempotent)."""
    from . import models  # noqa: F401 — registers all models with Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("Database tables ready.")
