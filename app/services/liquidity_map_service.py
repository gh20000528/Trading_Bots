"""
Liquidity Map Service
Detects Equal Highs (EQH) / Equal Lows (EQL) from 1H swing points,
and builds a unified table of all unswept liquidity targets.
"""
import pandas as pd
import smartmoneyconcepts as smc

EQH_EQL_TOL = 0.002   # 0.2% tolerance to classify swings as "equal"
MIN_TOUCHES  = 2       # at least 2 touches = equal level


def _group_equal_levels(points: list[tuple[int, float]], tol: float) -> list[dict]:
    used   = set()
    groups = []
    for i, (idx_a, px_a) in enumerate(points):
        if i in used:
            continue
        grp = [(idx_a, px_a)]
        for j, (idx_b, px_b) in enumerate(points):
            if j == i or j in used:
                continue
            if abs(px_b - px_a) / px_a <= tol:
                grp.append((idx_b, px_b))
                used.add(j)
        used.add(i)
        if len(grp) >= MIN_TOUCHES:
            avg  = sum(p for _, p in grp) / len(grp)
            last = max(ix for ix, _ in grp)
            groups.append({"level": round(avg, 4), "touches": len(grp), "last_index": last})
    return groups


def detect_equal_highs_lows(df_1h: pd.DataFrame, swing_length: int = 5) -> dict:
    """Return unswept EQH / EQL (up to 3 each, nearest to current price)."""
    swing_hl = smc.smc.swing_highs_lows(df_1h, swing_length=swing_length)

    highs = [(i, float(df_1h["high"].iloc[i])) for i in range(len(swing_hl))
              if swing_hl["HighLow"].iloc[i] == 1]
    lows  = [(i, float(df_1h["low"].iloc[i]))  for i in range(len(swing_hl))
              if swing_hl["HighLow"].iloc[i] == -1]

    curr = float(df_1h["close"].iloc[-1])

    # Keep levels that haven't been clearly swept
    eqh = [g for g in _group_equal_levels(highs, EQH_EQL_TOL)
            if curr <= g["level"] * (1 + EQH_EQL_TOL * 3)]
    eql = [g for g in _group_equal_levels(lows,  EQH_EQL_TOL)
            if curr >= g["level"] * (1 - EQH_EQL_TOL * 3)]

    return {
        "equal_highs": sorted(eqh, key=lambda x: x["level"])[-3:],
        "equal_lows":  sorted(eql, key=lambda x: x["level"])[:3],
    }


def build_liquidity_targets(price: float,
                             pdh: float | None, pdl: float | None,
                             eqh: list[dict], eql: list[dict]) -> list[dict]:
    """
    All unswept liquidity targets sorted by distance (nearest first).
    Each entry: { type, level, side, dist_pct, [touches] }
    """
    targets = []

    if pdh:
        targets.append({"type": "PDH", "level": round(pdh, 2), "side": "above",
                         "dist_pct": round((pdh - price) / price * 100, 2)})
    if pdl:
        targets.append({"type": "PDL", "level": round(pdl, 2), "side": "below",
                         "dist_pct": round((price - pdl) / price * 100, 2)})
    for g in eqh:
        targets.append({"type": "EQH", "level": round(g["level"], 2), "side": "above",
                         "touches": g["touches"],
                         "dist_pct": round((g["level"] - price) / price * 100, 2)})
    for g in eql:
        targets.append({"type": "EQL", "level": round(g["level"], 2), "side": "below",
                         "touches": g["touches"],
                         "dist_pct": round((price - g["level"]) / price * 100, 2)})

    targets.sort(key=lambda x: abs(x["dist_pct"]))
    return targets[:6]
