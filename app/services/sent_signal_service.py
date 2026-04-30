from datetime import datetime, timezone
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.sent_signal import SentSignal


async def save_signal(db: AsyncSession, data: dict) -> SentSignal:
    record = SentSignal(**data)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_open_signals(db: AsyncSession) -> list[SentSignal]:
    result = await db.execute(
        select(SentSignal)
        .where(SentSignal.outcome == "open")
        .order_by(SentSignal.sent_at)
    )
    return result.scalars().all()


async def get_all_signals(db: AsyncSession, limit: int = 100) -> list[SentSignal]:
    result = await db.execute(
        select(SentSignal).order_by(SentSignal.sent_at.desc()).limit(limit)
    )
    return result.scalars().all()


async def update_outcome(db: AsyncSession, signal_id: int, outcome: str, price: float):
    result = await db.execute(select(SentSignal).where(SentSignal.id == signal_id))
    record = result.scalar_one_or_none()
    if record:
        record.outcome       = outcome
        record.outcome_price = price
        record.closed_at     = datetime.now(timezone.utc)
        await db.commit()


async def get_analytics_summary(db: AsyncSession) -> dict:
    """Performance breakdown by symbol / grade / market_state / session."""

    all_rows = (await db.execute(
        select(SentSignal).order_by(SentSignal.sent_at.desc())
    )).scalars().all()

    def _stats(rows):
        settled = [r for r in rows if r.outcome in ("win", "loss")]
        wins    = [r for r in settled if r.outcome == "win"]
        return {
            "total":    len(rows),
            "open":     sum(1 for r in rows if r.outcome == "open"),
            "settled":  len(settled),
            "win":      len(wins),
            "loss":     len(settled) - len(wins),
            "expired":  sum(1 for r in rows if r.outcome == "expired"),
            "win_rate": round(len(wins) / len(settled) * 100, 1) if settled else None,
            "avg_rr1":  round(
                sum(r.rr1 for r in wins if r.rr1) / len([r for r in wins if r.rr1]), 2
            ) if [r for r in wins if r.rr1] else None,
        }

    def _group(key_fn):
        groups: dict[str, list] = {}
        for r in all_rows:
            k = key_fn(r) or "unknown"
            groups.setdefault(k, []).append(r)
        return [{"key": k, **_stats(v)} for k, v in sorted(groups.items())]

    return {
        "overall":      _stats(all_rows),
        "by_symbol":    _group(lambda r: r.symbol),
        "by_grade":     _group(lambda r: r.grade),
        "by_market_state": _group(lambda r: r.market_state),
        "by_session":   _group(lambda r: r.session),
        "by_bias":      _group(lambda r: r.bias),
    }
