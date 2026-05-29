"""Pydantic schemas for the SMS Gateway API."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator
import re


class SMSRequest(BaseModel):
    """Send a single SMS message."""
    to: str = Field(..., description="Destination phone number in E.164 format (+250788000001)")
    message: str = Field(..., min_length=1, max_length=1600, description="Message text")
    sender_id: str | None = Field(default=None, description="Sender ID override (alphanumeric, ≤11 chars)")
    country: str | None = Field(default=None, description="ISO 3166-1 alpha-2 country code (e.g. 'ke', 'ng', 'in'). Auto-detected from phone number if omitted.")

    @field_validator("to")
    @classmethod
    def validate_e164(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^\+\d{7,15}$", v):
            raise ValueError("Phone number must be in E.164 format: +<country_code><number>")
        return v


class SMSResponse(BaseModel):
    """Result of a single SMS send attempt."""
    success: bool
    message_id: str | None = None
    connector: str | None = None
    country_code: str | None = None
    error: str | None = None


class BulkSMSRequest(BaseModel):
    """Send the same message to multiple recipients."""
    recipients: list[str] = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=1600)
    sender_id: str | None = None


class BulkSMSResponse(BaseModel):
    sent: int
    failed: int
    results: list[SMSResponse]


class HealthResponse(BaseModel):
    status: str
    jasmin_reachable: bool
    version: str = "1.0.0"
