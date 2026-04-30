from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

router = APIRouter(prefix="/tv", tags=["tradingview"])

# In-memory store — 保存最新一筆 TradingView 報告
_latest_report: dict = {}


class ScoreLog(BaseModel):
    text: str


class Zone(BaseModel):
    top: float
    bottom: float


class KillZone(BaseModel):
    in_kz: bool
    name: str
    overlap: Optional[bool] = False


class OhlcData(BaseModel):
    open: float
    high: float
    low: float
    close: float


class TVReportIn(BaseModel):
    symbol: str
    bingx_symbol: str
    interval: str
    timeframe: str
    live_price: float
    ema9: float
    ema21: float
    ema_cross: str
    bias_score: int
    bias: str
    score_log: List[str]
    ob: Optional[Zone] = None
    fvg: Optional[Zone] = None
    in_zone: bool
    kill_zone: KillZone
    grade: str
    direction: str
    reason: List[str]
    sl: Optional[float] = None
    tp1: Optional[float] = None
    tp2: Optional[float] = None
    daily_ohlc: Optional[OhlcData] = None
    weekly_open: Optional[float] = None
    h4_ohlc: Optional[OhlcData] = None
    h1_ohlc: Optional[OhlcData] = None


@router.post("/report")
async def receive_tv_report(report: TVReportIn):
    global _latest_report
    _latest_report = {
        **report.dict(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    return {"ok": True}


@router.get("/report")
async def get_tv_report():
    return _latest_report
