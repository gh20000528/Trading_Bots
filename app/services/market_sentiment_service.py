import httpx
import ccxt.async_support as ccxt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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

async def get_previus_open_interrest(db: AsyncSession, symbol: str):
    result = await db.execute(
        select(MarketSentiment)
        .where(MarketSentiment.symbol == symbol)
        .order_by(MarketSentiment.id.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    return record.open_interest if record else None


# 1. Funding Rate（資金費率                                                                             
#   - 多方付費給空方 → 市場偏多（多單過多）
#   - 空方付費給多方 → 市場偏空（空單過多                                    
                                                                                                                                     
#   2. Long/Short Ratio（多空比）                                                            
#   - 比值 > 1 → 多單比空單多
#   - 比值 < 1 → 空單比多單多                                                                
                                                                                                                                     
#   3. Open Interest 趨勢（未平倉量變化）                                                    
#   - OI 上升 → 新資金進場，趨勢加強
#   - OI 下降 → 資金離場，趨勢減弱                                                         
#   - 現在：跟上一筆相同（1375848145.6），OI 沒有變化

async def get_market_sentiment(db: AsyncSession, symbol_ccxt: str, symbol_binance: str):
    funding_rate = await get_funding_rate(symbol_binance)
    open_interest = await get_open_interest(symbol_ccxt)
    long_short_ratio = await get_long_short_ratio(symbol_binance)
    prev_oi = await get_previus_open_interrest(db, symbol_ccxt.split('/')[0])

    # 計算偏見分數
    score = 0

    if funding_rate > 0.00005:
        score += 1
    elif funding_rate < -0.00005:
        score -= 1

    if long_short_ratio > 1.0:
        score += 1
    elif long_short_ratio < 1.0:
        score -= 1
    
    if prev_oi and open_interest > prev_oi:
        score += 1
    elif prev_oi and open_interest < prev_oi:
        score -= 1

    if score >= 1:
        bias = 'bullish'
    elif score <= -1:
        bias = 'bearish'
    else:
        bias = 'neutral'

    print(f"funding_rate: {funding_rate}")
    print(f"long_short_ratio: {long_short_ratio}")
    print(f"open_interest: {open_interest}") 
    print(f"prev_oi: {prev_oi}")
    print(f"score: {score}")
    print(f"bias: {bias}") 
    
    return {
        'bias':bias,                                                                                                       'funding_rate': funding_rate,
        'open_interest': open_interest,                                                                                    'long_short_ratio': long_short_ratio,
    }