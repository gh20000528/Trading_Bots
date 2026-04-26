from sqlalchemy import ForeignKey
from sqlalchemy import Column, Integer, String, Float, DateTime, Date
from sqlalchemy.sql import func
from app.database import Base

class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    signal_id = Column(Integer, ForeignKey("signals.id"), nullable=True)
    symbol = Column(String)
    direction = Column(String)
    entry_price = Column(Float)
    stop_loss = Column(Float)
    take_profit = Column(Float)
    size = Column(Float)
    status = Column(String, default="open")
    pnl = Column(Float, nullable=True)
    create_at = Column(DateTime, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)

