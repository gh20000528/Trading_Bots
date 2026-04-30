from fastapi import APIRouter
from app.services.backtest_service import run_backtest

router = APIRouter(prefix="/backtest", tags=["backtest"])


@router.get("/run")
async def backtest_endpoint(symbol: str = "BTC/USDT", days: int = 60):
    return await run_backtest(symbol, days)
