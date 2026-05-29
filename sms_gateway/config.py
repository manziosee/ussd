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

    # ── Connector routing (JSON dict: country_code → Jasmin connector CID) ───
    # Example: '{"250":"mtn_rw","254":"safaricom_ke","256":"mtn_ug"}'
    # When a country has no entry, Jasmin's own routing table decides.
    connector_map_json: str = (
        '{"250":"mtn_rw","254":"safaricom_ke","256":"mtn_ug",'
        '"255":"vodacom_tz","233":"mtn_gh","234":"mtn_ng",'
        '"27":"mtn_za","243":"airtel_cd","226":"orange_bf"}'
    )

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
