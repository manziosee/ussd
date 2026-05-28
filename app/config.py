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

    # ── Groq ──────────────────────────────────────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    max_ai_tokens: int = 150

    # ── Africa's Talking ──────────────────────────────────────────────────────
    at_username: str = "sandbox"
    at_api_key: str = ""
    at_shortcode: str = "SMARTASSIST"
    at_environment: str = "sandbox"   # "sandbox" | "production"
    # Secret token appended to the USSD callback URL → /ussd?token=<value>
    # AT is configured to POST to that URL; requests missing this token are rejected.
    at_webhook_token: str = ""

    # ── Admin API ─────────────────────────────────────────────────────────────
    # Sent as  X-Admin-Key: <value>  header on every /admin/* request.
    admin_api_key: str = ""

    # ── Cron ──────────────────────────────────────────────────────────────────
    # Secret token for  POST /cron/daily-tips?secret=<value>
    # Call this endpoint daily (e.g. Railway / GitHub Actions cron) to broadcast
    # morning tips to all opted-in subscribers.
    # Leave empty to disable the endpoint.
    cron_secret: str = ""

    # ── SMS ───────────────────────────────────────────────────────────────────
    sms_enabled: bool = True
    sms_char_limit: int = 155  # show truncated + SMS offer if AI reply > this

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
