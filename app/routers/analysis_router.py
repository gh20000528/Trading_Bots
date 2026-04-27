from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.analysis_service import get_multi_tf_analysis, interpret_signal


router = APIRouter(prefix="/analysis", tags=["analysis"])

@router.get("/{symbol}")
async def get_analysis_result(symbol: str):
    symbol_map = {
        'BTC': ('BTC/USDT', 'BTCUSDT'),
        'ETH': ('ETH/USDT', 'ETHUSDT'), 
    }
    if symbol not in symbol_map:
        return {"error": "symbol not supported"}
        
    symbol_ccxt, symbol_binance = symbol_map[symbol]
    result = await get_multi_tf_analysis(symbol_ccxt)

    analysis = interpret_signal(result)
    return [result, analysis]

