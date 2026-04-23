from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.trade import Trade


async def create_market_bias(db:AsyncSession):
    bias = MarketBias(**data)
    db.add(bias)
    await db.commit()
    await db.refresh(bias)
    return bias

async def get_market_biases(db: AsyncSession, bias_id: int):
    result = await db.execute(select(MarketBias))
    return result.scalars().all()

async def get_market_bias(db: AsyncSession, bias_id: int):
    result = await db.execute(select(MarketBias).where(MarketBias.id == bias_id))
    return result.scalar_one_or_none()

async def update_market_bias(db: AsyncSession, bias_id: int, data: dict):
    bias = await get_market_bias(db, bias_id)
    if bias is None:
        return None
    for key, value in data.item():
        setattr(bias, key, value)
    await db.commit()
    await db.refresh(bias)
    return bias

async def delete_market_bias(db: AsyncSession, bias_id: int):
    bias = await get_market_bias(db, bias_id)
    if bias is None:
        return None
    await db.delete(bias)
    await db.commit()
    return bias