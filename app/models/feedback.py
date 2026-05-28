"""
Feedback model — stores user ratings after AI responses.

rating:  1 = helpful,  -1 = not helpful
Linked back to the Interaction table via session_id + category for admin analysis.
"""
from sqlalchemy import Column, DateTime, Integer, String
from sqlalchemy.sql import func

from ..database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id           = Column(Integer, primary_key=True, index=True)
    session_id   = Column(String(100), nullable=False, index=True)
    phone_number = Column(String(20),  nullable=False, index=True)
    category     = Column(String(50),  nullable=False)
    rating       = Column(Integer,     nullable=False)  # 1 = helpful, -1 = not helpful
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        label = "helpful" if self.rating == 1 else "not helpful"
        return f"<Feedback #{self.id} {self.phone_number} [{self.category}] {label}>"
