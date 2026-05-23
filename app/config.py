"""
Application configuration — all settings come from environment variables or .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Application ──────────────────────────────────────────────────────────
    app_name: str = "SmartAssist USSD"
    app_version: str = "1.0.0"
    debug: bool = False
    secret_key: str = "change-this-in-production"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/smartassist"

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    session_ttl: int = 300      # 5 min — USSD timeout
    ai_cache_ttl: int = 86400   # 24 h — cache repeated AI answers

    # ── Anthropic / Claude ────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5-20251001"
    max_ai_tokens: int = 150

    # ── Africa's Talking ──────────────────────────────────────────────────────
    at_username: str = "sandbox"
    at_api_key: str = ""
    at_shortcode: str = "SMARTASSIST"
    at_environment: str = "sandbox"   # "sandbox" | "production"

    # ── SMS ───────────────────────────────────────────────────────────────────
    sms_enabled: bool = True
    sms_char_limit: int = 155  # show truncated + SMS offer if AI reply > this

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
