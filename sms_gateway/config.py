"""
SMS Gateway configuration — read from environment variables.

All settings use the SMS_GW_ prefix to avoid clashing with the main app.
"""
import json
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Jasmin HTTP API ───────────────────────────────────────────────────────
    jasmin_host: str = "localhost"
    jasmin_http_port: int = 1401
    jasmin_username: str = "admin"
    jasmin_password: str = "admin"
    jasmin_timeout: float = 10.0

    # ── Sender identity ───────────────────────────────────────────────────────
    default_sender_id: str = "SmartAssist"

    # ── Connector routing (JSON dict: dialing_prefix → Jasmin connector CID) ──
    # Default is EMPTY — Jasmin's own MT routing table handles dispatch globally.
    # Add entries only to override routing for specific country prefixes.
    # Connector names should be ISO 3166-1 alpha-2 country codes (rw, ke, ng …).
    # Example: '{"250":"rw","254":"ke","1":"us"}'
    connector_map_json: str = "{}"

    model_config = {
        "env_prefix": "SMS_GW_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    @property
    def connector_map(self) -> dict[str, str]:
        try:
            return json.loads(self.connector_map_json)
        except (ValueError, TypeError):
            return {}

    @property
    def jasmin_send_url(self) -> str:
        return f"http://{self.jasmin_host}:{self.jasmin_http_port}/send"


@lru_cache
def get_settings() -> Settings:
    return Settings()
