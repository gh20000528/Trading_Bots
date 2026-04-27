import ccxt.async_support as ccxt
from app.config import settings

exchange = ccxt.bingx({
    "apiKey": settings.bingx_api_key,
    "secret": settings.bingx_secret
})

public_exchange = ccxt.bingx() 

async def get_ohlcv(symbol: str, timeframe: str, limit: int = 100):
    ohlcv = await public_exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    return ohlcv