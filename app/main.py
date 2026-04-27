from fastapi import FastAPI
from app.database import init_db
from contextlib import asynccontextmanager
from app.models import signal, trade, market_bias, market_sentiment
from app.routers import signal_router, trade_router, market_bias_router, sentiment_router, analysis_router
from app.services.market_service import get_ohlcv
from fastapi.middleware.cors import CORSMiddleware
from app.services.market_sentiment_service import get_market_sentiment



async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="ICT Trading Bot", lifespan=lifespan)
app.include_router(signal_router.router)
app.include_router(trade_router.router)
app.include_router(market_bias_router.router)
app.include_router(sentiment_router.router)
app.include_router(analysis_router.router)


app.add_middleware(
    CORSMiddleware,                                                                                                        allow_origins=["http://localhost:5173"],
    allow_methods=["*"],                    
    allow_headers=["*"],  
)

@app.get("/test-market")
async def test_market():
    data = await get_ohlcv("BTC/USDT", "1d", limit = 3)
    return {"data" : data}

@app.get("/test-sentiment")
async def test_sentiment():
    data = await get_market_sentiment('BTC/USDT:USDT', 'BTCUSDT')
    return data

