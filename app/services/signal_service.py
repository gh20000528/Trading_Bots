from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.signal import Signal

async def create_signal(db: AsyncSession, data: dict):
    signal = Signal(**data)
    db.app(signal)
    await db.commit()
    await db.refresh(singal)
    return signal

async def get_signals(db: AsyncSession):
    result = await db.execute(select(Signal))
    return result.scalars().all()

async def get_signal(db: AsyncSession, signal_id: int):
    result = await db.execute(select(Signal).where(Signal.id == signal_id))
    return result.scalar_one_or_none()

async def update_signal_status(db: AsyncSession, signal_id: int, status: str):
    signal = await get_signal(db, siganl_id)
    if signal is None:
        return None
    signal.status = status
    await db.commit()
    await db.refresh(signal)
    return signal


async def delete_signal(db: AsyncSession, signal_id: int):
    signal = await get_signal(db, signal_id)
    if signal is None:
        return None
    await db.delete(signal)
    await db.commit()
    return signal