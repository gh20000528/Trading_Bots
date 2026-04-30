"""
Breakout vs Fake Break Classifier

For each key liquidity level (PDH / PDL / Asia H / Asia L):
  real_break  — close clearly beyond level AND sustained for lookback candles
  fake_break  — wick beyond level but close snapped back inside (= Manipulation)
  at_level    — close just barely beyond level, direction unresolved
  no_test     — price hasn't even reached the level

NO TRADE rule: fake_break OR at_level anywhere near a key level → wait.
"""
import pandas as pd

CLEAR_PCT = 0.003   # close must be ≥ 0.3% beyond level to count as "beyond"
REAL_PCT  = 0.005   # close ≥ 0.5% beyond level + all recent closes hold = real break


def _classify(df: pd.DataFrame, level: float, side: str, lookback: int = 3) -> str:
    """
    side: 'above' = testing level from below (bullish break)
          'below' = testing level from above (bearish break)
    """
    if len(df) < lookback or level <= 0:
        return "no_test"

    recent = df.iloc[-lookback:]
    close  = float(df["close"].iloc[-1])
    high   = float(df["high"].iloc[-1])
    low    = float(df["low"].iloc[-1])

    if side == "above":
        wick_past  = high  > level
        close_past = close > level
        if not wick_past:
            return "no_test"
        if close > level * (1 + REAL_PCT):
            # All recent closes must hold above
            if all(float(recent["close"].iloc[i]) > level for i in range(len(recent))):
                return "real_break"
            return "at_level"
        if close_past:
            return "at_level"
        return "fake_break"   # wick above, closed back below

    else:  # below
        wick_past  = low   < level
        close_past = close < level
        if not wick_past:
            return "no_test"
        if close < level * (1 - REAL_PCT):
            if all(float(recent["close"].iloc[i]) < level for i in range(len(recent))):
                return "real_break"
            return "at_level"
        if close_past:
            return "at_level"
        return "fake_break"   # wick below, closed back above


def analyze_breakouts(df_1h: pd.DataFrame, price: float,
                       pdh: float | None, pdl: float | None,
                       asia_high: float | None, asia_low: float | None) -> dict:
    """
    Returns:
      level_status  : { "PDH": "real_break", "Asia_Low": "fake_break", ... }
      fake_breaks   : list of level names with fake break
      real_breaks   : list of level names with real break
      at_level      : list of level names where break is unresolved
      has_fake_break: bool
      pending       : bool (price at level, direction unresolved)
    """
    checks: dict[str, str] = {}
    if pdh:       checks["PDH"]       = _classify(df_1h, pdh,       "above")
    if pdl:       checks["PDL"]       = _classify(df_1h, pdl,       "below")
    if asia_high: checks["Asia_High"] = _classify(df_1h, asia_high, "above")
    if asia_low:  checks["Asia_Low"]  = _classify(df_1h, asia_low,  "below")

    fake  = [k for k, v in checks.items() if v == "fake_break"]
    real  = [k for k, v in checks.items() if v == "real_break"]
    at_lv = [k for k, v in checks.items() if v == "at_level"]

    return {
        "level_status":    checks,
        "fake_breaks":     fake,
        "real_breaks":     real,
        "at_level":        at_lv,
        "has_fake_break":  bool(fake),
        "pending":         bool(at_lv),
    }
