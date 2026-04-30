"""
PO3 + Retracement + Weakness Confirmation Service

Module 1 - Retracement：
  找最近 impulse → Fibonacci 回測深度 + OB/FVG confluence

Module 2 - Weakness Confirmation：
  4 個進場條件逐一評分（rejection wick / LH or HL / 5m BOS / 短線破位）

Module 3 - PO3：
  Power of Three：Accumulation → Manipulation → Distribution
"""

import pandas as pd
import smartmoneyconcepts as smc

FIB_RATIOS     = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
ACCUM_LOOKBACK = 20     # 偵測 accumulation 用幾根 1H
MANIP_LOOKBACK = 6      # 偵測 manipulation 用幾根 1H
ACCUM_PCT      = 0.03   # range < 3% 才算 accumulation
WICK_THRESHOLD = 0.40   # 引線佔整根 K 棒 40% 以上算 rejection


# ═══════════════════════════════════════════════════════════════════════════════
# Module 1 — Retracement（Fibonacci）
# ═══════════════════════════════════════════════════════════════════════════════

def _extract_swings(df: pd.DataFrame, swing_hl, which: str) -> list[tuple[int, float]]:
    """回傳 (index, price) list，which = 'high' or 'low'"""
    flag = 1 if which == "high" else -1
    col  = "high" if which == "high" else "low"
    return [(i, float(df[col].iloc[i])) for i in range(len(swing_hl))
            if swing_hl["HighLow"].iloc[i] == flag]


def _find_impulse(df: pd.DataFrame, swing_hl, bias: str) -> dict | None:
    """找最近一段有意義的 impulse move"""
    highs = _extract_swings(df, swing_hl, "high")
    lows  = _extract_swings(df, swing_hl, "low")

    if not highs or not lows:
        return None

    if bias == "bullish":
        last_high   = highs[-1]
        prior_lows  = [(i, p) for i, p in lows if i < last_high[0]]
        if not prior_lows:
            return None
        pivot_low = prior_lows[-1]
        return {
            "direction": "up",
            "start":     {"index": pivot_low[0], "price": pivot_low[1]},
            "end":       {"index": last_high[0], "price": last_high[1]},
            "move_pct":  round((last_high[1] - pivot_low[1]) / pivot_low[1] * 100, 2),
        }
    else:
        last_low    = lows[-1]
        prior_highs = [(i, p) for i, p in highs if i < last_low[0]]
        if not prior_highs:
            return None
        pivot_high = prior_highs[-1]
        return {
            "direction": "down",
            "start":     {"index": pivot_high[0], "price": pivot_high[1]},
            "end":       {"index": last_low[0],   "price": last_low[1]},
            "move_pct":  round((pivot_high[1] - last_low[1]) / pivot_high[1] * 100, 2),
        }


def _compute_fib_levels(impulse: dict) -> dict[float, float]:
    high = max(impulse["start"]["price"], impulse["end"]["price"])
    low  = min(impulse["start"]["price"], impulse["end"]["price"])
    diff = high - low
    levels = {}
    for r in FIB_RATIOS:
        if impulse["direction"] == "up":
            levels[r] = round(high - diff * r, 6)   # 多頭回踩往下
        else:
            levels[r] = round(low  + diff * r, 6)   # 空頭反彈往上
    return levels


def _classify_pullback(price: float, fib: dict[float, float], direction: str) -> str:
    full_range = abs(fib[1.0] - fib[0.0])
    if full_range == 0:
        return "unknown"
    retraced = abs(price - fib[0.0])
    ratio    = retraced / full_range
    if ratio <= 0:
        return "no_pullback"
    if ratio < 0.382:
        return "shallow"
    if ratio <= 0.618:
        return "normal"
    return "deep"


def _find_confluences(fib: dict, h1_ob: list, h1_fvg: list, bias: str) -> list[dict]:
    ob_dir = 1.0 if bias == "bullish" else -1.0
    result = []
    for ratio, price in fib.items():
        if ratio in (0.0, 1.0):
            continue
        for ob in h1_ob:
            if ob["OB"] == ob_dir and ob["MitigatedIndex"] == 0.0:
                if ob["Bottom"] <= price <= ob["Top"]:
                    result.append({"ratio": ratio, "price": price, "type": "OB",
                                   "zone": {"top": ob["Top"], "bottom": ob["Bottom"]}})
        for fvg in h1_fvg:
            if fvg["FVG"] == ob_dir and fvg.get("MitigatedIndex", 0) == 0:
                if fvg["Bottom"] <= price <= fvg["Top"]:
                    result.append({"ratio": ratio, "price": price, "type": "FVG",
                                   "zone": {"top": fvg["Top"], "bottom": fvg["Bottom"]}})
    return result


def analyze_retracement(df_1h: pd.DataFrame, h1: dict, bias: str) -> dict:
    """完整 Fibonacci 回測分析"""
    if bias == "neutral":
        return {"available": False}

    swing_hl  = smc.smc.swing_highs_lows(df_1h, swing_length=5)
    impulse   = _find_impulse(df_1h, swing_hl, bias)
    if not impulse:
        return {"available": False}

    fib          = _compute_fib_levels(impulse)
    current      = float(df_1h["close"].iloc[-1])
    pullback     = _classify_pullback(current, fib, impulse["direction"])
    confluences  = _find_confluences(fib, h1["ob"], h1["fvg"], bias)
    nearest_fib  = min(fib.items(), key=lambda x: abs(x[1] - current))

    return {
        "available":      True,
        "impulse_pct":    impulse["move_pct"],
        "direction":      impulse["direction"],
        "fib_levels":     {str(k): round(v, 2) for k, v in fib.items()},
        "pullback_type":  pullback,
        "nearest_fib":    {"ratio": nearest_fib[0], "price": round(nearest_fib[1], 2)},
        "confluences":    confluences,
        "in_confluence":  len(confluences) > 0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Module 2 — Weakness Confirmation
# ═══════════════════════════════════════════════════════════════════════════════

def _has_rejection_wick(df: pd.DataFrame, direction: str, lookback: int = 3) -> bool:
    recent = df.iloc[-lookback:]
    for _, row in recent.iterrows():
        total = row["high"] - row["low"]
        if total == 0:
            continue
        body_top    = max(row["open"], row["close"])
        body_bottom = min(row["open"], row["close"])
        if direction == "bearish":
            wick = row["high"] - body_top
        else:
            wick = body_bottom - row["low"]
        if wick / total >= WICK_THRESHOLD:
            return True
    return False


def _has_lh_or_hl(df: pd.DataFrame, swing_hl, direction: str) -> bool:
    if direction == "bearish":
        highs = [float(df["high"].iloc[i]) for i in range(len(swing_hl))
                 if swing_hl["HighLow"].iloc[i] == 1]
        return len(highs) >= 2 and highs[-1] < highs[-2]   # LH
    else:
        lows = [float(df["low"].iloc[i]) for i in range(len(swing_hl))
                if swing_hl["HighLow"].iloc[i] == -1]
        return len(lows) >= 2 and lows[-1] > lows[-2]      # HL


def _broke_short_term_level(df: pd.DataFrame, swing_hl, direction: str) -> bool:
    price = float(df["close"].iloc[-1])
    if direction == "bearish":
        lows = [float(df["low"].iloc[i]) for i in range(len(swing_hl))
                if swing_hl["HighLow"].iloc[i] == -1]
        return len(lows) >= 2 and price < lows[-2]
    else:
        highs = [float(df["high"].iloc[i]) for i in range(len(swing_hl))
                 if swing_hl["HighLow"].iloc[i] == 1]
        return len(highs) >= 2 and price > highs[-2]


def check_weakness(df_5m: pd.DataFrame, m5: dict, bias: str) -> dict:
    """
    弱勢 / 強勢確認（4 個條件）
    score >= 3 = ready，score 2 = 觀察中，< 2 = 未確認
    """
    direction   = "bearish" if bias == "bearish" else "bullish"
    swing_5m    = smc.smc.swing_highs_lows(df_5m, swing_length=3)
    choch_dir   = -1.0 if direction == "bearish" else 1.0

    c1 = _has_rejection_wick(df_5m, direction)
    c2 = _has_lh_or_hl(df_5m, swing_5m, direction)
    c3 = bool(m5["bos_choch"] and (
            m5["bos_choch"][-1].get("CHOCH") == choch_dir or
            m5["bos_choch"][-1].get("BOS")   == choch_dir))
    c4 = _broke_short_term_level(df_5m, swing_5m, direction)

    label = {
        "rejection_wick": "rejection wick" if direction == "bearish" else "lower wick",
        "structure":      "LH 形成"        if direction == "bearish" else "HL 形成",
        "bos_choch":      "5m BOS/CHoCH ↓" if direction == "bearish" else "5m BOS/CHoCH ↑",
        "level_broken":   "跌破短線低點"   if direction == "bearish" else "突破短線高點",
    }
    conditions = {
        "rejection_wick": c1,
        "structure":      c2,
        "bos_choch":      c3,
        "level_broken":   c4,
    }
    met   = [label[k] for k, v in conditions.items() if v]
    score = len(met)

    return {
        "direction":      direction,
        "score":          score,
        "max_score":      4,
        "conditions":     conditions,
        "conditions_met": met,
        "ready":          score >= 3,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Module 3 — PO3（Power of Three）
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_po3(df_1h: pd.DataFrame, h1: dict) -> dict:
    """
    偵測 PO3 各階段：
      Accumulation / Manipulation High / Manipulation Low /
      Distribution Bullish / Distribution Bearish / Trending
    """
    need = ACCUM_LOOKBACK + MANIP_LOOKBACK
    if len(df_1h) < need:
        return {"state": "unknown"}

    # ① 累積區間（Accumulation）
    accum_df  = df_1h.iloc[-(need):-MANIP_LOOKBACK]
    acc_high  = float(accum_df["high"].max())
    acc_low   = float(accum_df["low"].min())
    acc_range = (acc_high - acc_low) / acc_low if acc_low else 0

    is_accum  = acc_range < ACCUM_PCT

    # ② 近期掃單（Manipulation）
    recent        = df_1h.iloc[-MANIP_LOOKBACK:]
    current_close = float(df_1h["close"].iloc[-1])

    swept_high  = float(recent["high"].max()) > acc_high * 1.001
    swept_low   = float(recent["low"].min())  < acc_low  * 0.999
    back_inside_high = current_close < acc_high
    back_inside_low  = current_close > acc_low

    manip_high = swept_high and back_inside_high
    manip_low  = swept_low  and back_inside_low

    # ③ 發力 / Distribution（掃完後 BOS 反向）
    bos_list  = h1.get("bos_choch", [])
    recent_bos = bos_list[-4:] if bos_list else []
    bos_up   = any(b.get("BOS") == 1.0  or b.get("CHOCH") == 1.0  for b in recent_bos)
    bos_down = any(b.get("BOS") == -1.0 or b.get("CHOCH") == -1.0 for b in recent_bos)

    dist_bull = manip_low  and bos_up   and current_close > acc_high
    dist_bear = manip_high and bos_down and current_close < acc_low

    # 判斷 state
    if dist_bull:
        state = "Distribution Bullish"
    elif dist_bear:
        state = "Distribution Bearish"
    elif manip_high:
        state = "Manipulation High"
    elif manip_low:
        state = "Manipulation Low"
    elif is_accum:
        state = "Accumulation"
    else:
        state = "Trending"

    return {
        "state":       state,
        "acc_high":    round(acc_high, 2),
        "acc_low":     round(acc_low,  2),
        "range_pct":   round(acc_range * 100, 2),
        "manipulation": "high" if manip_high else "low" if manip_low else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 決策文字生成
# ═══════════════════════════════════════════════════════════════════════════════

def build_waiting_conditions(
    bias: str, po3: dict, retracement: dict,
    weakness: dict, in_kill_zone: bool, in_zone: bool
) -> list[str]:
    conds = []
    if bias == "neutral":
        conds.append("等 Bias 明確（Score 達 ±3）")
        return conds

    po3_state = po3.get("state", "")
    if po3_state == "Accumulation":
        conds.append("等 PO3 Manipulation 完成（掃高 or 掃低後收回）")
    if po3_state in ("Manipulation High", "Manipulation Low"):
        conds.append("等 Distribution BOS 確認方向")

    if retracement.get("available"):
        pt = retracement["pullback_type"]
        if pt == "no_pullback":
            conds.append("等回測 OB/FVG/Fib 區間")
        elif pt == "deep":
            conds.append("深度回調（>78.6%），等結構重新確認")
        if not retracement["in_confluence"]:
            conds.append("等 Fib 與 OB/FVG 形成 Confluence")

    if not in_zone:
        conds.append("等價格進入 OB / FVG 區間")

    wk = weakness.get("conditions", {})
    if not wk.get("rejection_wick"):
        conds.append("等 rejection wick 出現" if bias == "bearish" else "等 lower wick 出現")
    if not wk.get("structure"):
        conds.append("等 5m LH 形成" if bias == "bearish" else "等 5m HL 形成")
    if not wk.get("bos_choch"):
        conds.append("等 5m CHoCH/BOS ↓ 確認" if bias == "bearish" else "等 5m CHoCH/BOS ↑ 確認")

    if not in_kill_zone:
        conds.append("等 Kill Zone（London 02-05 / NY 13-16 UTC）")

    return conds


def build_forbidden_reasons(
    bias: str, po3: dict, retracement: dict,
    market_state: str, chip_bias: str | None
) -> list[str]:
    reasons = []
    if bias == "neutral":
        reasons.append("無明確方向，Bias 評分不足")
        return reasons

    if market_state == "Range":
        reasons.append("盤整中，無結構可做")

    po3_state = po3.get("state", "")
    # 禁止在 Manipulation 中順向追單
    if po3_state == "Manipulation High" and bias == "bullish":
        reasons.append("PO3 Manipulation High：禁止追多，可能是假突破")
    if po3_state == "Manipulation Low" and bias == "bearish":
        reasons.append("PO3 Manipulation Low：禁止追空，可能是假跌破")

    if retracement.get("available") and retracement["pullback_type"] == "deep":
        reasons.append("回調超過 Fib 78.6%，結構可能已破，禁止盲目逆勢")

    if chip_bias and chip_bias != "neutral" and chip_bias != bias:
        reasons.append(f"籌碼方向（{chip_bias}）與 ICT Bias（{bias}）衝突")

    return reasons
