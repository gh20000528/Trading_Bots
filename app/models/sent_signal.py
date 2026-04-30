from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from app.database import Base


class SentSignal(Base):
    __tablename__ = "sent_signals"

    id            = Column(Integer, primary_key=True, index=True)
    symbol        = Column(String, nullable=False)
    bias          = Column(String)
    bias_score    = Column(Integer)
    market_state  = Column(String)
    structure     = Column(String)
    entry_status  = Column(String)   # LONG / SHORT / WATCH LONG / WATCH SHORT
    grade         = Column(String)   # A / B / C
    session       = Column(String)   # Asia / London / NY / Off-Hours
    current_price = Column(Float)
    sl            = Column(Float, nullable=True)
    tp1           = Column(Float, nullable=True)
    rr1           = Column(Float, nullable=True)
    decision      = Column(String)
    chip_bias     = Column(String)
    chip_score    = Column(Integer)
    outcome       = Column(String, default="open")   # open / win / loss / expired
    outcome_price = Column(Float, nullable=True)
    sent_at       = Column(DateTime, server_default=func.now())
    closed_at     = Column(DateTime, nullable=True)
