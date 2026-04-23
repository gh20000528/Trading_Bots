from sqlalchemy import Column, Integer, String, Float, DateTime, Date
from sqlalchemy.sql import func
from app.database import Base

class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String)
    timeframe = Column(String)
    signal_type = Column(String)
    price = Column(Float)
    status = Column(String, default = "active")
    create_at = Column(DateTime, server_default=func.now())