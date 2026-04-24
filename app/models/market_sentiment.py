from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base

class MarketSentiment(Base):
    __tablename__ = "market_sentiment"

    id = Column(Integer, primary_key=True)
    symbol = Column(String)
    bias = Column(String)
    funding_rate = Column(Float)
    open_interest = Column(Float)
    long_short_ratio = Column(Float)
    create_at = Column(DateTime, server_default=func.now())