import httpx
import ccxt.async_support as ccxt
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.market_sentiment import MarketSentiment

exchange = ccxt.bingx()

async def get_funding_rate(symbol: str):
    # symbol 格式: 'BTC/USDT:USDT'
    async with httpx.AsyncClient() as client:
        res = await client.get('https://fapi.binance.com/fapi/v1/premiumIndex', params={'symbol': symbol} )
        data = res.json()
        print(data)
        return float(data['lastFundingRate'])

async def get_open_interest(symbol: str):
    # symbol 格式: 'BTC/USDT:USDT'
    data = await exchange.fetch_open_interest(symbol)
    return data['openInterestValue']

async def get_long_short_ratio(symbol: str):
    # symbol 格式: 'BTC/USDT:USDT'
    async with httpx.AsyncClient() as client:
        res = await client.get('https://fapi.binance.com/futures/data/globalLongShortAccountRatio',
        params={'symbol': symbol, 'period': '5m', 'limit': 1}  
        )
        data = res.json()
        return float(data[0]['longShortRatio'])

async def save_sentiment(db: AsyncSession, symbol: str, sentiment: dict):
    record = MarketSentiment(
        symbol = symbol,
        bias = sentiment['bias'],
        funding_rate = sentiment['funding_rate'],
        open_interest = sentiment['open_interest'],
        long_short_ratio = sentiment['long_short_ratio']
    )
    db.add(record)
    await db.commit()
    return record

async def get_market_sentiment(symbol_ccxt: str, symbol_binance: str):
    funding_rate = await get_funding_rate(symbol_binance)
    open_interest = await get_open_interest(symbol_ccxt)
    long_short_ratio = await get_long_short_ratio(symbol_binance)

    # 計算偏見分數
    score = 0

    if funding_rate > 0.0001:
        score += 1
    elif funding_rate < -0.0001:
        score -= 1

    if long_short_ratio > 1.0:
        score += 1
    elif long_short_ratio < 1.0:
        score -= 1
    
    if score >= 2:
        bias = 'bullish'
    elif score <= -2:
        bias = 'bearish'
    else:
        bias = 'neutral'
    
    return {
        'bias':bias,                                                                                                       'funding_rate': funding_rate,
        'open_interest': open_interest,                                                                                    'long_short_ratio': long_short_ratio,
    }