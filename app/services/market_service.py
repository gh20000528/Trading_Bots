import ccxt.async_support as ccxt
from app.config import settings

exchange = ccxt.bingx({
    "apiKey": settings.bingx_api_key,
    "secret": settings.bingx_secret
})

async def get_ohlcv(symbol: str, timeframe: str, limit: int = 100):
    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    return ohlcv