"""
Interaction model — logs every AI query for analytics and cost tracking.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func

from ..database import Base


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)

    # What was asked and answered
    category = Column(String(50), nullable=False)  # business | farming | health | education | general
    question = Column(Text, nullable=False)
    response = Column(Text, nullable=False)

    # Cost & cache tracking
    tokens_used = Column(Integer, default=0, nullable=False)
    from_cache = Column(Boolean, default=False, nullable=False)
    sms_sent = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Interaction #{self.id} {self.phone_number} [{self.category}]>"
