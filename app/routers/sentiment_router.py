from fastapi import APIRouter
from app.database import AsyncSessionLocal
from app.services.market_sentiment_service import get_market_sentiment, save_sentiment

router = APIRouter(prefix = '/sentiment', tags=['sentiment'])

@router.get("/{symbol}")
async def get_sentiment(symbol: str):
    async with AsyncSessionLocal() as db:
        symbol_map = {
            'BTC': ('BTC/USDT:USDT', 'BTCUSDT'),
            'ETH': ('ETH/USDT:USDT', 'ETHUSDT'), 
        }
        if symbol not in symbol_map:
            return {"error": "symbol not supported"}
        
        symbol_ccxt, symbol_binance = symbol_map[symbol]
        result = await get_market_sentiment(symbol_ccxt, symbol_binance)
        await save_sentiment(db, symbol, result)
        return await get_market_sentiment(symbol_ccxt, symbol_binance)