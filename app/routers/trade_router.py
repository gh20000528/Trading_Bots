from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services import trade_service

router = APIRouter(prefix="/trade", tags=["trades"])


async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


@router.post("/")
async def create_trade(data: dict, db: AsyncSession = Depends(get_db)):
    return await trade_service.create_trade(db, data)

@router.get("/")
async def list_trades(db: AsyncSession = Depends(get_db)):
    return await trade_service.get_trades(db)

@router.get("/{trade_id}")
async def get_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    return await trade_service.get_trade(db, trade_id)

@router.patch("/{trade_id}")
async def update_trade(trade_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    return await trade_service.update_trade(db, trade_id, data)

@router.delete("/{trade_id}")
async def delete_trade(trade_id: int, db: AsyncSession = Depends(get_db)):
    return await trade_service.delete_trade(db, trade_id)