"""
User model — stores persistent info per phone number.
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from ..database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)

    # Profile (optional, set via Account menu)
    name = Column(String(100), nullable=True)
    profession = Column(String(100), nullable=True)   # farmer, student, business, other
    language = Column(String(10), default="en", nullable=False)

    # Stats
    total_queries = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.phone_number}>"
