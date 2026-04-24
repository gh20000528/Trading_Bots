from pydantic import BaseModel
from datetime import date

class MarketBiasCreate(BaseModel):
    symbol: str
    bias: str
    notes: str = ""
    date: date

class SignalCreate(BaseModel):
    symbol: str
    timeframe: str
    signal_type: str
    direction: str
    price: float

class TradeCreate(BaseModel):
    symbol: str
    direction: str
    price: float
    stop_loss: float
    take_profit: float
    size: float
    