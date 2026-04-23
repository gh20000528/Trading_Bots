from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services import signal_service

router = APIRouter(prefix="/signal", tags=["signal"])

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

@router.post("/")
async def create_signal(data: dict, db: AsyncSession = Depends(get_db)):
    return await signal_service.create_signal(db, data)

@router.get("/")
async def list_signal(db: AsyncSession = Depends(get_db)):
    return await signal_service.get_signals(db)

@router.get("/{signal_id}")
async def get_signal(signal_id: int, deb: AsyncSession = Depends(get_db)):
    return await signal_service.get_signal(db, signal_id)

@router.patch("/{signal_id}")
async def update_signal(signal_id: int, status: str, db: AsyncSession = Depends(get_db)):
    return await signal_service.update_signal_status(db, signal_id, status)

@router.delete("/{signal_id}")
async def delete_signal(signal_id: int, db: AsyncSession = Depends(get_db)):
    return await signal_service.delete_signal(db, signal_id)