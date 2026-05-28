"""
User model — stores persistent info per phone number.
"""
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)

    # Profile (optional, set via Account menu)
    name       = Column(String(100), nullable=True)
    profession = Column(String(100), nullable=True)   # farmer | student | business owner | other
    language   = Column(String(10),  default="en", nullable=False, server_default="en")

    # Preferences
    sms_opt_out = Column(
        Boolean, default=False, nullable=False, server_default="false",
        comment="When True, skip sending full-answer SMS even if response exceeds char limit",
    )

    # Onboarding
    onboarded = Column(
        Boolean, default=False, nullable=False, server_default="false",
        comment="True once user completes initial language+profession setup",
    )

    # Daily tip subscription
    daily_tips_enabled = Column(
        Boolean, default=False, nullable=False, server_default="false",
        comment="User opted in to receive one tip per day via SMS",
    )
    daily_tip_category = Column(
        String(50), nullable=True,
        comment="Preferred tip category (business/farming/health/education). NULL = use profession",
    )

    # Stats
    total_queries = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.phone_number}>"
