"""
MarketPrice model — admin-maintained crop price table per district.

Updated weekly by admins via  PUT /admin/market-prices.
Read at runtime by Farming menu option 4 (zero AI cost).
"""
from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from ..database import Base


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id         = Column(Integer, primary_key=True, index=True)
    district   = Column(String(50),  nullable=False, index=True)
    crop       = Column(String(100), nullable=False)
    unit       = Column(String(30),  nullable=False, default="kg")
    price_rwf  = Column(Integer,     nullable=False)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("district", "crop", name="uq_market_price_district_crop"),
    )

    def __repr__(self) -> str:
        return f"<MarketPrice {self.district}/{self.crop} {self.price_rwf} RWF/{self.unit}>"
