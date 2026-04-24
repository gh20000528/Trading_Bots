from sqlalchemy import ForeignKey
from sqlalchemy import Column, Integer, String, Float, DateTime, Date
from sqlalchemy.sql import func
from app.database import Base

class MarketBias(Base):
    __tablename__ = "market_bias"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    bias = Column(String)
    notes = Column(String, nullable=True)
    date = Column(Date)
    create_at = Column(DateTime, server_default=func.now())