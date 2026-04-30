"""
SL / TP Calculator (ICT rules)

Long:
  SL  = bottom of triggering OB/FVG  × (1 - SL_BUFFER)
  TP1 = nearest unswept EQH / PDH above entry
  TP2 = next liquidity target above

Short:
  SL  = top of triggering OB/FVG × (1 + SL_BUFFER)
  TP1 = nearest unswept EQL / PDL below entry
  TP2 = next liquidity target below
"""

SL_BUFFER = 0.003   # 0.3% beyond OB/FVG boundary


def compute_sltp(
    bias: str,
    price: float,
    h1: dict,
    liq_targets: list,
) -> dict | None:
    """
    Returns { sl, tp1, tp1_type, tp2, tp2_type, rr1, rr2, risk_pct }
    or None if no valid OB/FVG zone found at current price.
    """
    if bias not in ("bullish", "bearish"):
        return None

    ob_dir = 1.0 if bias == "bullish" else -1.0

    # ── Find active zone price is currently in ─────────────────────────────
    zone = _find_active_zone(price, h1, ob_dir)
    if not zone:
        return None

    z_bottom, z_top, z_type = zone

    if bias == "bullish":
        sl = round(z_bottom * (1 - SL_BUFFER), 4)
    else:
        sl = round(z_top * (1 + SL_BUFFER), 4)

    risk = abs(price - sl)
    if risk == 0:
        return None

    # ── TP from liquidity targets ──────────────────────────────────────────
    if bias == "bullish":
        candidates = sorted(
            [t for t in liq_targets if t["side"] == "above" and t["level"] > price],
            key=lambda x: x["level"]
        )
    else:
        candidates = sorted(
            [t for t in liq_targets if t["side"] == "below" and t["level"] < price],
            key=lambda x: x["level"], reverse=True
        )

    def _rr(tp_price: float) -> float:
        return round(abs(tp_price - price) / risk, 1)

    result: dict = {
        "sl":       round(sl, 2),
        "risk_pct": round(risk / price * 100, 2),
        "zone_type": z_type,
    }

    if candidates:
        t1 = candidates[0]
        result["tp1"]      = t1["level"]
        result["tp1_type"] = t1["type"]
        result["rr1"]      = _rr(t1["level"])

    if len(candidates) >= 2:
        t2 = candidates[1]
        result["tp2"]      = t2["level"]
        result["tp2_type"] = t2["type"]
        result["rr2"]      = _rr(t2["level"])

    return result


def _find_active_zone(price: float, h1: dict,
                      ob_dir: float) -> tuple[float, float, str] | None:
    """Return (bottom, top, type) of the OB or FVG that price is currently in."""
    active_obs = [
        ob for ob in h1["ob"]
        if ob["OB"] == ob_dir and ob["MitigatedIndex"] == 0.0
    ]
    for ob in reversed(active_obs):
        if ob["Bottom"] * 0.997 <= price <= ob["Top"] * 1.003:
            return (ob["Bottom"], ob["Top"], "OB")

    active_fvgs = [
        f for f in h1["fvg"]
        if f["FVG"] == ob_dir and f.get("MitigatedIndex", 0) == 0
    ]
    for fvg in reversed(active_fvgs):
        if fvg["Bottom"] * 0.997 <= price <= fvg["Top"] * 1.003:
            return (fvg["Bottom"], fvg["Top"], "FVG")

    return None
