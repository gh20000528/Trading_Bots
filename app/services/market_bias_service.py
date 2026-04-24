from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.market_bias import MarketBias


async def create_market_bias(db:AsyncSession, data: dict):
    bias = MarketBias(**data)
    db.add(bias)
    await db.commit()
    await db.refresh(bias)
    return bias

async def get_market_biases(db: AsyncSession):
    result = await db.execute(select(MarketBias))
    return result.scalars().all()

async def get_market_bias(db: AsyncSession, bias_id: int):
    result = await db.execute(select(MarketBias).where(MarketBias.id == bias_id))
    return result.scalar_one_or_none()

async def update_market_bias(db: AsyncSession, bias_id: int, data: dict):
    bias = await get_market_bias(db, bias_id)
    if bias is None:
        return None
    for key, value in data.items():
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

async def get_lastest_bias_by_symbol(db: AsyncSession, symbol: str):
    result = await db.execute(
        select(MarketBias)
        .where(MarketBias.symbol == symbol)
        .order_by(MarketBias.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()