from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services import market_bias_service

router = APIRouter(prefix="/market-bias", tags=["market-bias"])

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db

@router.post("/")
async def create_market_bias(data:dict, db: AsyncSession = Depends(get_db)):
    return await market_bias_service.create_market_bias(db, data)
    
@router.get("/")
async def list_market_bias(db: AsyncSession = Depends(get_db)):
    return await market_bias_service.get_market_biases(db)

@router.get("/{bias_id}")
async def get_market_bias(bias_id: int, db: AsyncSession = Depends(get_db)):
    return await market_bias_service.get_market_bias(db, bias_id)

@router.patch("/{bias_id}")
async def update_market_bias(bias_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    return await market_bias_service.update_market_bias(db, bias_id, data)

@router.delete("/{bias_id}")
async def delete_market_bias(bias_id: int, db: AsyncSession = Depends(get_db)):
    return await market_bias_service.delete_market_bias(db, bias_id)