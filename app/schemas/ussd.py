"""
Pydantic schemas for USSD and admin endpoints.
"""
from datetime import datetime
from pydantic import BaseModel, Field


class USSDRequest(BaseModel):
    """USSD gateway callback — sent as form data (x-www-form-urlencoded)."""
    sessionId:   str = Field(..., description="Unique session identifier from the USSD gateway")
    serviceCode: str = Field(..., description="USSD shortcode, e.g. *123#")
    phoneNumber: str = Field(..., description="User's phone number in E.164 format")
    text:        str = Field(default="", description="Accumulated user input, *-separated")
    networkCode: str = Field(default="", description="Mobile network code (optional)")


class SimulateRequest(BaseModel):
    """Used by the /simulate endpoint for local testing."""
    phone_number: str = Field(default="+1555000001", description="Phone number to simulate (E.164)")
    text:         str = Field(default="", description="USSD text input (use * to separate levels)")
    session_id:   str = Field(default="test-session-001", description="Session ID")


class AdminStats(BaseModel):
    total_users: int
    total_interactions: int
    total_tokens_used: int
    cache_hit_rate: float
    sms_sent: int
    interactions_by_category: dict[str, int]


class InteractionOut(BaseModel):
    id:           int
    session_id:   str
    phone_number: str
    category:     str
    question:     str
    response:     str
    tokens_used:  int
    from_cache:   bool
    sms_sent:     bool
    created_at:   datetime

    model_config = {"from_attributes": True}


class MarketPriceIn(BaseModel):
    district:   str = Field(..., description="District or region name (operator-defined)")
    crop:       str = Field(..., description="Crop or product name, e.g. 'Maize'")
    unit:       str = Field(default="kg", description="Unit of measure, e.g. 'kg' or 'bunch'")
    price:      int = Field(..., gt=0, description="Price in local currency")
    currency:   str = Field(default="RWF", description="ISO 4217 currency code (RWF, KES, NGN, USD …)")
    updated_by: str | None = Field(default=None, description="Admin identifier (optional)")


class MarketPriceOut(BaseModel):
    id:         int
    district:   str
    crop:       str
    unit:       str
    price:      int
    currency:   str
    updated_by: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}
