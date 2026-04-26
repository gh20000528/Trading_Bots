from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.trade import Trade

async def create_trade(db: AsyncSession, data: dict):
    trade = Trade(**data)
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade

async def get_trades(db: AsyncSession):
    result = await db.execute(select(Trade))
    return result.scalars().all()

async def get_trade(db: AsyncSession, trade_id: int):
    result = await db.execute(select(Trade).where(Trade.id == trade_id))
    return result.scalar_one_or_none()

async def update_trade(db: AsyncSession, trade_id: int, data: dict):
    trade = await get_trade(db, trade_id)
    if trade is None:
        return None
    for key, value in data.items():
        setattr(trade, key, value)
    await db.commit()
    await db.refresh(trade)
    return trade

async def delete_trade(db: AsyncSession, trade_id: int):
    trade = await get_trade(db, trade_id)
    if trade is None:
        return None
    await db.delete(trade)
    await db.commit()
    return trade
