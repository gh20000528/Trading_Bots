from fastapi import FastAPI
from app.database import init_db
from contextlib import asynccontextmanager
from app.models import signal, trade, market_bias
from app.routers import signal_router, trade_router, market_bias_router



async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(title="ICT Trading Bot", lifespan=lifespan)
app.include_router(signal_router.router)
app.include_router(trade_router.router)
app.include_router(market_bias_router.router)

@app.get("/health")
async def health():
    return {"status" : "ok"}

