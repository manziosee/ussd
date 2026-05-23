"""
Pydantic schemas for USSD and admin endpoints.
"""
from datetime import datetime
from pydantic import BaseModel, Field


class USSDRequest(BaseModel):
    """Africa's Talking USSD callback — sent as form data (x-www-form-urlencoded)."""
    sessionId: str = Field(..., description="Unique session identifier from AT")
    serviceCode: str = Field(..., description="USSD shortcode, e.g. *384*72275#")
    phoneNumber: str = Field(..., description="User's phone number with country code")
    text: str = Field(default="", description="Accumulated user input, *-separated")
    networkCode: str = Field(default="", description="Mobile network code (optional)")


class SimulateRequest(BaseModel):
    """Used by the /simulate endpoint for local testing."""
    phone_number: str = Field(default="+250788123456", description="Phone number to simulate")
    text: str = Field(default="", description="USSD text input (use * to separate levels)")
    session_id: str = Field(default="test-session-001", description="Session ID")


class AdminStats(BaseModel):
    total_users: int
    total_interactions: int
    total_tokens_used: int
    cache_hit_rate: float
    sms_sent: int
    interactions_by_category: dict[str, int]


class InteractionOut(BaseModel):
    id: int
    session_id: str
    phone_number: str
    category: str
    question: str
    response: str
    tokens_used: int
    from_cache: bool
    sms_sent: bool
    created_at: datetime

    model_config = {"from_attributes": True}
