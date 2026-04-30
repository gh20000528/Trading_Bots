"""
Multi-Timeframe Historical Backtest v4

Strategy:
  1H  — CHoCH structural direction
  1H  — EMA-9 / EMA-21 cross (informational only, not a filter)
  5M  — active OB or FVG in CHoCH direction at current price
  5M  — Fibonacci quality filter: OB/FVG midpoint must be within
         the 38.2%–78.6% retracement zone of the last 50-bar swing
  SL  — 5M zone boundary × (1 ± 0.3%)
  TP1 — +1.5% / TP2 — +3.0%
  Min RR 1.5 enforced; 24H expiry (288 × 5M bars)

Data limit: 5M ≈ 2000 bars ≈ 7 days max.
"""

import asyncio
import numpy as np
import pandas as pd
import smartmoneyconcepts as smc
from app.services.market_service import get_ohlcv

# ── Window / expiry ────────────────────────────────────────────────────────────
WINDOW_1H  = 100   # 1H bars for CHoCH + EMA (~4 days context)
WINDOW_5M  = 100   # 5M bars for OB/FVG analysis (~8H context)
EXPIRE_5M  = 288   # 24H in 5M bars
MAX_DAYS   = 7

# ── EMA (informational only) ───────────────────────────────────────────────────
EMA_FAST = 9
EMA_SLOW = 21

# ── Trade parameters ───────────────────────────────────────────────────────────
TP1_PCT = 0.015   # 1.5%
TP2_PCT = 0.030   # 3.0%
SL_PCT  = 0.003   # 0.3% buffer beyond OB/FVG boundary
OB_TOL  = 0.002   # 0.2% tolerance for "price inside zone"
MIN_RR  = 1.5

# ── Fibonacci filter ───────────────────────────────────────────────────────────
FIB_LOOKBACK = 50   # last N 5M bars used to find swing range
FIB_LO       = 0.382
FIB_HI       = 0.786


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _fetch(symbol: str, tf: str, limit: int) -> pd.DataFrame:
    ohlcv = await get_ohlcv(symbol, tf, limit=limit)
    return pd.DataFrame(
        ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )


def _choch_direction(window_1h: pd.DataFrame) -> float | None:
    """Last CHoCH direction in the 1H window: 1.0 bullish, -1.0 bearish."""
    try:
        swing = smc.smc.swing_highs_lows(window_1h, swing_length=5)
        bos   = smc.smc.bos_choch(window_1h, swing)
        rows  = [
            r for r in bos.replace({np.nan: None}).to_dict(orient="records")
            if r.get("CHOCH") is not None
        ]
        if not rows:
            return None
        last = rows[-1]
        d = last.get("BOS") or last.get("CHOCH")
        return d if d in (1.0, -1.0) else None
    except Exception:
        return None


def _analyze_5m(window_5m: pd.DataFrame) -> dict:
    """OB and FVG lists from a 5M window."""
    try:
        swing  = smc.smc.swing_highs_lows(window_5m, swing_length=5)
        ob_df  = smc.smc.ob(window_5m, swing)
        fvg_df = smc.smc.fvg(window_5m, join_consecutive=False)
        ob_list = [
            r for r in ob_df.replace({np.nan: None}).to_dict(orient="records")
            if r.get("OB") is not None
        ]
        fvg_list = [
            r for r in fvg_df.replace({np.nan: None}).to_dict(orient="records")
            if r.get("FVG") is not None
        ]
        return {"ob": ob_list, "fvg": fvg_list}
    except Exception:
        return {"ob": [], "fvg": []}


def _fib_quality(window_5m: pd.DataFrame, zone_bot: float, zone_top: float,
                 bias: str) -> bool:
    """
    True if the OB/FVG midpoint falls within the 38.2%–78.6% retracement zone
    of the recent swing (last FIB_LOOKBACK bars).

    Bullish: retrace downward from the recent high.
    Bearish: retrace upward from the recent low.
    """
    sub  = window_5m.iloc[-FIB_LOOKBACK:].reset_index(drop=True)
    s_hi = float(sub["high"].max())
    s_lo = float(sub["low"].min())
    rng  = s_hi - s_lo

    if rng < s_lo * 0.005:   # range < 0.5% → too tight to measure, allow through
        return True

    mid = (zone_bot + zone_top) / 2.0

    if bias == "bullish":
        lo_bound = s_hi - FIB_HI * rng   # deeper end  (78.6% from top)
        hi_bound = s_hi - FIB_LO * rng   # shallow end (38.2% from top)
    else:
        lo_bound = s_lo + FIB_LO * rng   # 38.2% up from bottom
        hi_bound = s_lo + FIB_HI * rng   # 78.6% up from bottom

    return lo_bound <= mid <= hi_bound


def _find_zone(ana: dict, ob_dir: float, price: float) -> tuple | None:
    """
    Most recent active 5M OB (preferred) or FVG at price.
    Returns (bottom, top, zone_type) or None.
    """
    for ob in reversed(ana["ob"]):
        if ob.get("OB") != ob_dir or ob.get("MitigatedIndex") != 0.0:
            continue
        bot, top = ob.get("Bottom"), ob.get("Top")
        if not (bot and top):
            continue
        if bot * (1 - OB_TOL) <= price <= top * (1 + OB_TOL):
            return float(bot), float(top), "OB"

    for fvg in reversed(ana["fvg"]):
        if fvg.get("FVG") != ob_dir or fvg.get("MitigatedIndex") != 0.0:
            continue
        bot, top = fvg.get("Bottom"), fvg.get("Top")
        if not (bot and top):
            continue
        if bot * (1 - OB_TOL) <= price <= top * (1 + OB_TOL):
            return float(bot), float(top), "FVG"

    return None


def _simulate(df_5m: pd.DataFrame, start: int, bias: str,
              entry: float, sl: float) -> dict:
    tp1 = entry * (1 + TP1_PCT) if bias == "bullish" else entry * (1 - TP1_PCT)
    tp2 = entry * (1 + TP2_PCT) if bias == "bullish" else entry * (1 - TP2_PCT)

    outcome    = "expired"
    exit_price = None

    for _, row in df_5m.iloc[start: start + EXPIRE_5M].iterrows():
        h, l = float(row["high"]), float(row["low"])
        bull_candle = float(row["close"]) >= float(row["open"])

        if bias == "bullish":
            hit_sl, hit_t2, hit_t1 = l <= sl, h >= tp2, h >= tp1
            if hit_sl and not (bull_candle and (hit_t1 or hit_t2)):
                outcome, exit_price = "loss",    sl;  break
            if hit_t2: outcome, exit_price = "win_tp2", tp2; break
            if hit_t1: outcome, exit_price = "win_tp1", tp1; break
            if hit_sl: outcome, exit_price = "loss",    sl;  break
        else:
            hit_sl, hit_t2, hit_t1 = h >= sl, l <= tp2, l <= tp1
            if hit_sl and not (not bull_candle and (hit_t1 or hit_t2)):
                outcome, exit_price = "loss",    sl;  break
            if hit_t2: outcome, exit_price = "win_tp2", tp2; break
            if hit_t1: outcome, exit_price = "win_tp1", tp1; break
            if hit_sl: outcome, exit_price = "loss",    sl;  break

    return {
        "outcome":    outcome,
        "exit_price": round(exit_price, 4) if exit_price else None,
        "tp1": round(tp1, 4),
        "tp2": round(tp2, 4),
        "sl":  round(sl,  4),
    }


# ── Entry point ────────────────────────────────────────────────────────────────

async def run_backtest(symbol: str, days: int = 7) -> dict:
    effective = min(days, MAX_DAYS)

    limit_1h = min((effective + 5) * 24 + WINDOW_1H,  2000)
    limit_5m = min((effective + 2) * 288 + WINDOW_5M, 2000)

    df_1h, df_5m = await asyncio.gather(
        _fetch(symbol, "1h", limit_1h),
        _fetch(symbol, "5m", limit_5m),
    )
    df_1h = df_1h.reset_index(drop=True)
    df_5m = df_5m.reset_index(drop=True)

    ts_5m     = df_5m["timestamp"].values
    ts_5m_min = int(ts_5m[0])
    ts_5m_max = int(ts_5m[-1])

    cutoff   = df_1h["timestamp"].iloc[-1] - effective * 24 * 3_600_000
    valid_1h = df_1h[
        (df_1h["timestamp"] >= cutoff) &
        (df_1h["timestamp"] >= ts_5m_min) &
        (df_1h["timestamp"] <= ts_5m_max)
    ]
    if valid_1h.empty:
        return {"symbol": symbol, "days": effective,
                "error": "No overlapping 1H / 5M data"}

    start_i = max(int(valid_1h.index[0]), WINDOW_1H)

    signals      = []
    skip_zone    = 0
    skip_fib     = 0
    skip_rr      = 0

    for i in range(start_i, len(df_1h)):
        ts_1h = int(df_1h.iloc[i]["timestamp"])
        if ts_1h > ts_5m_max:
            break

        # ── 1H CHoCH ────────────────────────────────────────────────
        w1h       = df_1h.iloc[i - WINDOW_1H: i].copy().reset_index(drop=True)
        direction = _choch_direction(w1h)
        if direction is None:
            continue

        bias   = "bullish" if direction == 1.0 else "bearish"
        ob_dir = direction
        price  = float(w1h["close"].iloc[-1])

        # ── EMA-9 / EMA-21 (informational) ──────────────────────────
        closes   = w1h["close"]
        ema9     = float(closes.ewm(span=EMA_FAST, adjust=False).mean().iloc[-1])
        ema21    = float(closes.ewm(span=EMA_SLOW, adjust=False).mean().iloc[-1])
        ema_cross = "golden" if ema9 > ema21 else "death"

        # ── 5M alignment ─────────────────────────────────────────────
        idx_5m = int(np.searchsorted(ts_5m, ts_1h, side="right")) - 1
        if idx_5m < WINDOW_5M or idx_5m + EXPIRE_5M >= len(df_5m):
            continue

        w5m    = df_5m.iloc[idx_5m - WINDOW_5M: idx_5m].copy().reset_index(drop=True)
        ana    = _analyze_5m(w5m)
        zone   = _find_zone(ana, ob_dir, price)

        if zone is None:
            skip_zone += 1
            continue

        bot, top, zone_type = zone

        # ── Fibonacci quality filter ──────────────────────────────────
        if not _fib_quality(w5m, bot, top, bias):
            skip_fib += 1
            continue

        sl = round(bot * (1 - SL_PCT), 4) if bias == "bullish" \
             else round(top * (1 + SL_PCT), 4)

        # ── RR check ──────────────────────────────────────────────────
        sl_dist = abs(price - sl) / price
        if sl_dist == 0 or (TP1_PCT / sl_dist) < MIN_RR:
            skip_rr += 1
            continue

        rr  = round(TP1_PCT / sl_dist, 2)
        sim = _simulate(df_5m, idx_5m, bias, price, sl)

        signals.append({
            "timestamp": ts_1h,
            "bias":      bias,
            "zone":      zone_type,
            "ema_cross": ema_cross,
            "entry":     round(price, 4),
            "rr":        rr,
            **sim,
        })

    # Deduplicate: same direction within 4H
    deduped = []
    last_ts  = {"bullish": 0, "bearish": 0}
    for s in signals:
        if s["timestamp"] - last_ts[s["bias"]] >= 4 * 3_600_000:
            deduped.append(s)
            last_ts[s["bias"]] = s["timestamp"]

    settled = [s for s in deduped if s["outcome"] != "expired"]
    wins    = [s for s in settled if "win" in s["outcome"]]
    losses  = [s for s in settled if s["outcome"] == "loss"]

    rr_vals = [s["rr"] for s in wins if s.get("rr")]
    avg_rr  = round(sum(rr_vals) / len(rr_vals), 2) if rr_vals else None

    return {
        "symbol":        symbol,
        "days":          effective,
        "total_signals": len(deduped),
        "settled":       len(settled),
        "wins":          len(wins),
        "losses":        len(losses),
        "expired":       len(deduped) - len(settled),
        "win_rate":      round(len(wins) / len(settled) * 100, 1) if settled else None,
        "avg_rr":        avg_rr,
        "skip_zone":     skip_zone,
        "skip_fib":      skip_fib,
        "skip_rr":       skip_rr,
        "signals":       deduped[-100:],
    }
