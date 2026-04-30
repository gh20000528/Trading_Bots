from fastapi import APIRouter
from app.database import AsyncSessionLocal
from app.services.sent_signal_service import get_analytics_summary, get_all_signals

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary():
    async with AsyncSessionLocal() as db:
        return await get_analytics_summary(db)


@router.get("/signals")
async def list_signals(limit: int = 200):
    async with AsyncSessionLocal() as db:
        rows = await get_all_signals(db, limit=limit)
        return [
            {
                "id":            r.id,
                "symbol":        r.symbol,
                "bias":          r.bias,
                "bias_score":    r.bias_score,
                "grade":         r.grade,
                "signal":        r.entry_status,
                "market_state":  r.market_state,
                "session":       r.session,
                "current_price": r.current_price,
                "sl":            r.sl,
                "tp1":           r.tp1,
                "rr1":           r.rr1,
                "chip_bias":     r.chip_bias,
                "chip_score":    r.chip_score,
                "outcome":       r.outcome,
                "outcome_price": r.outcome_price,
                "sent_at":       r.sent_at.isoformat() if r.sent_at else None,
                "closed_at":     r.closed_at.isoformat() if r.closed_at else None,
            }
            for r in rows
        ]
