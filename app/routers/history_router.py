from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.services.sent_signal_service import get_all_signals, update_outcome

router = APIRouter(prefix="/history", tags=["history"])


async def get_db():
    async with AsyncSessionLocal() as db:
        yield db


@router.get("/")
async def list_signals(limit: int = 100, db: AsyncSession = Depends(get_db)):
    signals = await get_all_signals(db, limit=limit)
    return [
        {
            "id":            s.id,
            "symbol":        s.symbol,
            "bias":          s.bias,
            "bias_score":    s.bias_score,
            "market_state":  s.market_state,
            "structure":     s.structure,
            "entry_status":  s.entry_status,
            "current_price": s.current_price,
            "decision":      s.decision,
            "chip_bias":     s.chip_bias,
            "chip_score":    s.chip_score,
            "outcome":       s.outcome,
            "outcome_price": s.outcome_price,
            "sent_at":       s.sent_at.isoformat() if s.sent_at else None,
            "closed_at":     s.closed_at.isoformat() if s.closed_at else None,
        }
        for s in signals
    ]


@router.patch("/{signal_id}/outcome")
async def mark_outcome(signal_id: int, outcome: str, price: float, db: AsyncSession = Depends(get_db)):
    """手動標記結果：outcome = win / loss / expired"""
    await update_outcome(db, signal_id, outcome, price)
    return {"ok": True}
