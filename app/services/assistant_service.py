import pandas as pd
import smartmoneyconcepts as smc
from app.services.market_service import get_ohlcv
from app.services.analysis_service import get_analysis
from app.services.po3_service import (
    analyze_retracement, check_weakness, analyze_po3,
    build_waiting_conditions, build_forbidden_reasons,
)
from app.services.liquidity_map_service import detect_equal_highs_lows, build_liquidity_targets
from app.services.session_service import get_session_context, get_asia_sweep_signal
from app.services.breakout_service import analyze_breakouts
from app.services.sltp_service import compute_sltp
from app.services.liquidation_service import estimate_liquidation_levels


async def _fetch_df(symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
    ohlcv = await get_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df


def _get_asia_hl(df: pd.DataFrame) -> dict:
    """Asia session = 00:00–08:00 UTC 的最高 / 最低"""
    today = df["datetime"].dt.date.iloc[-1]
    asia = df[(df["datetime"].dt.date == today) & (df["datetime"].dt.hour < 8)]
    if asia.empty:
        return {"asia_high": None, "asia_low": None}
    return {
        "asia_high": float(asia["high"].max()),
        "asia_low":  float(asia["low"].min()),
    }


def _get_utc8_daily_open(df: pd.DataFrame) -> float | None:
    """
    UTC+8 日開 = 每天 00:00 HKT = 前一天 16:00 UTC。
    根據當前時間找正確的 16:00 UTC 蠟燭。
    """
    last = df["datetime"].iloc[-1]
    if last.hour >= 16:
        target = last.normalize() + pd.Timedelta(hours=16)
    else:
        target = last.normalize() - pd.Timedelta(hours=8)

    row = df[df["datetime"] == target]
    return float(row["open"].iloc[0]) if not row.empty else None


def _get_utc8_weekly_open(df: pd.DataFrame) -> float | None:
    """
    UTC+8 週開 = 每週一 00:00 HKT = 週日 16:00 UTC。
    在 1H dataframe 中找最近的週日 16:00 UTC。
    """
    for i in range(len(df) - 1, -1, -1):
        ts = df["datetime"].iloc[i]
        if ts.weekday() == 6 and ts.hour == 16:
            return float(df["open"].iloc[i])
    return None


def _get_swing_structure(df: pd.DataFrame, swing_length: int = 5) -> str:
    """從 1H swing highs/lows 判斷結構：HH+HL / LH+LL / HH+LL / LH+HL"""
    swing_hl = smc.smc.swing_highs_lows(df, swing_length=swing_length)
    highs = [df["high"].iloc[i] for i in range(len(swing_hl)) if swing_hl["HighLow"].iloc[i] == 1]
    lows  = [df["low"].iloc[i]  for i in range(len(swing_hl)) if swing_hl["HighLow"].iloc[i] == -1]
    if len(highs) >= 2 and len(lows) >= 2:
        hh = highs[-1] > highs[-2]
        hl = lows[-1]  > lows[-2]
        if hh and hl:           return "HH+HL"
        if not hh and not hl:   return "LH+LL"
        if hh:                  return "HH+LL"
        return "LH+HL"
    return "unknown"


def _score_bias(daily, h1, m5, weekly_open, daily_open, h1_structure) -> dict:
    """
    Bias scoring 最高 ±6 分：
      ±1  價格 vs 日開
      ±1  價格 vs 週開
      ±2  Daily BOS/CHoCH 方向
      ±1  1H BOS/CHoCH 方向
      ±1  1H 結構 HH+HL / LH+LL
    >= 3 = Bullish，<= -3 = Bearish，其餘 = Neutral
    """
    score = 0
    reasons = []
    price = m5["last_close"]

    if daily_open:
        if price > daily_open:
            score += 1; reasons.append(f"站上日開 {round(daily_open, 2)} (+1)")
        else:
            score -= 1; reasons.append(f"跌破日開 {round(daily_open, 2)} (-1)")

    if weekly_open:
        if price > weekly_open:
            score += 1; reasons.append(f"站上週開 {round(weekly_open, 2)} (+1)")
        else:
            score -= 1; reasons.append(f"跌破週開 {round(weekly_open, 2)} (-1)")

    if daily["bos_choch"]:
        last_d = daily["bos_choch"][-1]
        d_dir  = last_d.get("BOS") or last_d.get("CHOCH")
        if d_dir == 1.0:
            score += 2; reasons.append("Daily BOS/CHoCH ↑ (+2)")
        elif d_dir == -1.0:
            score -= 2; reasons.append("Daily BOS/CHoCH ↓ (-2)")

    if h1["bos_choch"]:
        last_h1 = h1["bos_choch"][-1]
        h1_dir  = last_h1.get("BOS") or last_h1.get("CHOCH")
        if h1_dir == 1.0:
            score += 1; reasons.append("1H BOS/CHoCH ↑ (+1)")
        elif h1_dir == -1.0:
            score -= 1; reasons.append("1H BOS/CHoCH ↓ (-1)")

    if h1_structure == "HH+HL":
        score += 1; reasons.append("1H 結構 HH+HL (+1)")
    elif h1_structure == "LH+LL":
        score -= 1; reasons.append("1H 結構 LH+LL (-1)")

    if score >= 3:
        bias = "bullish"
    elif score <= -3:
        bias = "bearish"
    else:
        bias = "neutral"

    return {"bias": bias, "score": score, "max_score": 6, "reasons": reasons}


def _classify_market_state(h1, m5, bias) -> str:
    bos_list = h1.get("bos_choch", [])
    if not bos_list:
        return "Range"

    dir_val = 1.0 if bias == "bullish" else -1.0
    recent  = bos_list[-4:]

    has_choch = any(b.get("CHOCH") not in (None, 0, 0.0) for b in recent[-2:])
    same_dir  = [b for b in recent if b.get("BOS") == dir_val]

    if has_choch and same_dir:
        return "Liquidity Sweep"

    price = m5["last_close"]
    ob_dir = 1.0 if bias == "bullish" else -1.0
    active_obs = [ob for ob in h1["ob"] if ob["OB"] == ob_dir and ob["MitigatedIndex"] == 0.0]

    if len(same_dir) >= 1:
        near_ob = False
        if active_obs:
            ob = active_obs[-1]
            near_ob = (
                (bias == "bullish" and price <= ob["Top"]    * 1.005) or
                (bias == "bearish" and price >= ob["Bottom"] * 0.995)
            )
        if near_ob:
            return "Pullback"
        return "Trend"

    return "Range"


def _get_entry_status(bias_data, market_state, h1, m5, in_kill_zone) -> dict:
    bias = bias_data["bias"]

    if bias == "neutral":
        return {"status": "❌", "label": "不可進場", "met": [], "missing": ["無明確 Bias"]}
    if market_state == "Range":
        return {"status": "❌", "label": "不可進場", "met": [], "missing": ["盤整中，無結構"]}

    ob_dir    = 1.0 if bias == "bullish" else -1.0
    choch_dir = 1.0 if bias == "bullish" else -1.0
    price     = m5["last_close"]
    met, missing = [], []

    active_obs  = [ob for ob in h1["ob"]  if ob["OB"]  == ob_dir and ob["MitigatedIndex"] == 0.0]
    active_fvgs = [f  for f  in h1["fvg"] if f["FVG"]  == ob_dir and f.get("MitigatedIndex") == 0]
    in_zone = False

    if active_obs:
        ob = active_obs[-1]
        if ob["Bottom"] * 0.997 <= price <= ob["Top"] * 1.003:
            in_zone = True
            met.append(f"在 OB {round(ob['Bottom'],2)}–{round(ob['Top'],2)}")

    if not in_zone and active_fvgs:
        fvg = active_fvgs[-1]
        if fvg["Bottom"] * 0.997 <= price <= fvg["Top"] * 1.003:
            in_zone = True
            met.append(f"在 FVG {round(fvg['Bottom'],2)}–{round(fvg['Top'],2)}")

    if not in_zone:
        missing.append("尚未回測 OB/FVG")

    confirmed = False
    if m5["bos_choch"]:
        last5 = m5["bos_choch"][-1]
        if last5.get("CHOCH") == choch_dir or last5.get("BOS") == choch_dir:
            confirmed = True
    if confirmed:
        met.append("5m CHoCH/BOS 確認")
    else:
        missing.append("等 5m CHoCH 確認")

    if in_kill_zone:
        met.append("在 Kill Zone")
    else:
        missing.append("不在 Kill Zone")

    if not missing:
        return {"status": "✅", "label": "可進場",  "met": met, "missing": missing}
    if not met:
        return {"status": "❌", "label": "不可進場", "met": met, "missing": missing}
    return     {"status": "⚠️", "label": "可觀察",  "met": met, "missing": missing}


def _classify_entry_timing(entry_status: dict, in_kill_zone: bool) -> str:
    """
    right_side: In zone + 5m CHoCH confirmed + Kill Zone → full alignment
    left_side:  In zone but waiting for 5m CHoCH or Kill Zone
    no_setup:   Not in any OB/FVG zone
    """
    met       = entry_status.get("met", [])
    in_zone   = any("OB" in c or "FVG" in c for c in met)
    confirmed = any("CHoCH" in c or "BOS" in c for c in met)

    if not in_zone:
        return "no_setup"
    if confirmed and in_kill_zone:
        return "right_side"
    return "left_side"


def compute_trade_grade(
    bias_data:     dict,
    market_state:  str,
    entry_status:  dict,
    po3:           dict,
    retracement:   dict,
    weakness:      dict,
    entry_timing:  str,
    breakout_info: dict,
    session_info:  dict,
    chip:          dict | None = None,
) -> dict:
    """
    Tiered trade grading system.
    Returns: { grade, signal, action, no_trade_reasons }
      grade:  'A' | 'B' | 'C'
      signal: 'LONG' | 'SHORT' | 'WATCH LONG' | 'WATCH SHORT' | 'NO TRADE'
      action: short Chinese description
      no_trade_reasons:
        A → []
        B → what's needed to upgrade to A
        C → what's blocking
    """
    score     = bias_data["score"]
    bias      = bias_data["bias"]
    abs_score = abs(score)
    po3_state = po3.get("state", "")
    wk_score  = weakness.get("score", 0)
    in_kz     = session_info.get("in_kill_zone", False)

    met       = entry_status.get("met", [])
    in_zone   = any("OB" in c or "FVG" in c for c in met)
    confirmed = any("CHoCH" in c or "BOS" in c for c in met)

    fib_too_deep  = retracement.get("available") and retracement.get("pullback_type") == "deep"
    has_fake_brk  = breakout_info.get("has_fake_break", False)
    manip_trap    = (po3_state == "Manipulation High" and bias == "bullish") or \
                   (po3_state == "Manipulation Low"  and bias == "bearish")

    chip_conflict = False
    if chip:
        cb = chip.get("bias", "neutral")
        cs = chip.get("score", 0)
        if cb not in ("neutral", bias) and cs >= 4:
            chip_conflict = True

    # ── 硬性 C 級阻止條件（這些出現直接 C，不給 B）────────────────────────
    hard_blocks = []

    if market_state == "Range":
        hard_blocks.append("市場盤整（Range），無結構可做")
    if po3_state == "Accumulation":
        hard_blocks.append("PO3 Accumulation：等待掃單完成")
    if manip_trap:
        hard_blocks.append(f"PO3 {po3_state}：禁止同向追單（假突破陷阱）")
    if fib_too_deep:
        hard_blocks.append("Fib 回調超過 78.6%，結構可能已破")
    if has_fake_brk:
        fb = ", ".join(breakout_info["fake_breaks"])
        hard_blocks.append(f"Fake Break 偵測：{fb}")
    if chip_conflict:
        hard_blocks.append(f"籌碼衝突（{chip.get('bias')} {chip.get('score')}/6）vs ICT Bias")

    # Bias 完全中立（score 0 或 ±1）→ 硬性 C
    if abs_score <= 1:
        hard_blocks.append(f"Bias 太弱（{score}/{bias_data['max_score']}，需達 ±2）")

    if hard_blocks:
        return {"grade": "C", "signal": "NO TRADE", "action": "完全不進場",
                "no_trade_reasons": hard_blocks}

    # ── 方向（score ±2 以上就有方向，不依賴 bias label）─────────────────
    is_bullish = score >= 2

    # ── Grade A：全條件滿足 ────────────────────────────────────────────────
    a_ok = (
        abs_score >= 3          # Bias ≥ ±3
        and in_zone             # 在 OB/FVG 區間
        and confirmed           # 5m CHoCH/BOS 確認
        and wk_score >= 3       # Weakness ≥ 3
        and in_kz               # 在 Kill Zone
    )

    if a_ok:
        return {
            "grade":  "A",
            "signal": "LONG" if is_bullish else "SHORT",
            "action": "可以進場（A 級主倉位）",
            "no_trade_reasons": [],
        }

    # ── Grade B：部分條件滿足，有明確方向 ────────────────────────────────
    b_ok = (
        abs_score >= 2                              # Bias ≥ ±2
        and (in_zone or entry_timing == "left_side")  # 在區間或接近
        and wk_score >= 2                           # Weakness ≥ 2
    )

    if b_ok:
        missing = []
        if abs_score < 3:
            missing.append(f"Bias 還差 {3 - abs_score} 分（目前 {score}/{bias_data['max_score']}）")
        if po3_state in ("Manipulation High", "Manipulation Low"):
            missing.append(f"PO3 仍在 {po3_state}，等 Distribution BOS 確認")
        if not in_zone:
            missing.append("等回測進入 OB/FVG 區間")
        elif not confirmed:
            missing.append("等 5m CHoCH / BOS 確認")
        if wk_score < 3:
            missing.append(f"Weakness {wk_score}/4（升 A 需達 3）")
        if not in_kz:
            missing.append("等 Kill Zone（London 02-05 / NY 13-16 UTC）")

        return {
            "grade":  "B",
            "signal": "WATCH LONG" if is_bullish else "WATCH SHORT",
            "action": "等確認再入場（或小倉位試探）",
            "no_trade_reasons": missing,
        }

    # ── Grade C：方向有但條件不足 ─────────────────────────────────────────
    soft_blocks = []
    if not in_zone and entry_timing != "left_side":
        soft_blocks.append("未進入 OB/FVG 進場區間")
    if wk_score < 2:
        soft_blocks.append(f"Weakness 不足（{wk_score}/4，需達 2）")

    return {
        "grade":  "C",
        "signal": "NO TRADE",
        "action": "完全不進場",
        "no_trade_reasons": soft_blocks if soft_blocks else ["條件不足"],
    }


def _get_decision(bias, market_state, entry_status) -> str:
    """根據組合輸出一句話操作建議（保留供 Telegram 使用）"""
    status  = entry_status["status"]
    missing = entry_status.get("missing", [])
    dir_zh  = "多" if bias == "bullish" else "空"

    if bias == "neutral":
        return "現在不要做（無明確方向）"
    if market_state == "Range":
        return "盤整中，等結構形成再說"
    if market_state == "Liquidity Sweep":
        return f"流動性剛被掃，等反彈結構確認再做{dir_zh}"
    if status == "✅":
        return f"條件完整，可考慮做{dir_zh}（嚴守止損）"
    if status == "⚠️":
        if "尚未回測 OB/FVG" in missing:
            return f"等回測 OB/FVG 再做{dir_zh}"
        if "等 5m CHoCH 確認" in missing and "在 Kill Zone" not in entry_status.get("met", []):
            return f"在進場區，等 Kill Zone + 5m CHoCH"
        if "等 5m CHoCH 確認" in missing:
            return f"在進場區，等 5m CHoCH 確認後做{dir_zh}"
        if "不在 Kill Zone" in missing:
            return f"條件接近，等 Kill Zone（London / NY）開啟"
    return f"條件不足，不要做{dir_zh}"


async def build_assistant_report(symbol: str, chip: dict | None = None) -> dict:
    """完整 assistant 分析，整合所有模組"""
    daily = await get_analysis(symbol, "1d", swing_length=5)
    h1    = await get_analysis(symbol, "1h", swing_length=5)
    m5    = await get_analysis(symbol, "5m", swing_length=3)

    df_1h = await _fetch_df(symbol, "1h", limit=200)
    df_5m = await _fetch_df(symbol, "5m", limit=100)

    daily_open   = _get_utc8_daily_open(df_1h)
    weekly_open  = _get_utc8_weekly_open(df_1h)
    asia_hl      = _get_asia_hl(df_1h)
    h1_structure = _get_swing_structure(df_1h)

    pdh = daily.get("prev_high")
    pdl = daily.get("prev_low")
    asia_high = asia_hl.get("asia_high")
    asia_low  = asia_hl.get("asia_low")
    price     = m5["last_close"]

    liq = h1.get("liquidity", [])
    unswept_highs = [item["Level"] for item in liq if item.get("Liquidity") == 1  and item.get("Swept") == 0 and item.get("Level")]
    unswept_lows  = [item["Level"] for item in liq if item.get("Liquidity") == -1 and item.get("Swept") == 0 and item.get("Level")]

    bias_data    = _score_bias(daily, h1, m5, weekly_open, daily_open, h1_structure)
    market_state = _classify_market_state(h1, m5, bias_data["bias"])
    in_kill_zone = m5.get("in_kill_zone", False)
    entry_status = _get_entry_status(bias_data, market_state, h1, m5, in_kill_zone)
    decision     = _get_decision(bias_data["bias"], market_state, entry_status)

    # ── Analysis modules ──────────────────────────────────────────────────
    po3         = analyze_po3(df_1h, h1)
    retracement = analyze_retracement(df_1h, h1, bias_data["bias"])
    weakness    = check_weakness(df_5m, m5, bias_data["bias"])
    in_zone     = any("OB" in c or "FVG" in c for c in entry_status.get("met", []))

    # ── New: Liquidity Map ────────────────────────────────────────────────
    eq_hl       = detect_equal_highs_lows(df_1h)
    liq_targets = build_liquidity_targets(
        price, pdh, pdl, eq_hl["equal_highs"], eq_hl["equal_lows"]
    )

    # ── New: Session ──────────────────────────────────────────────────────
    session_info = get_session_context()
    asia_sweep   = get_asia_sweep_signal(price, session_info["session"], asia_high, asia_low)

    # ── New: Breakout classifier ──────────────────────────────────────────
    breakout_info = analyze_breakouts(df_1h, price, pdh, pdl, asia_high, asia_low)

    # ── New: Entry timing ─────────────────────────────────────────────────
    entry_timing = _classify_entry_timing(entry_status, in_kill_zone)

    # ── Trade grade (A / B / C) ───────────────────────────────────────────
    grade_result = compute_trade_grade(
        bias_data, market_state, entry_status,
        po3, retracement, weakness,
        entry_timing, breakout_info,
        session_info, chip,
    )

    waiting_conditions = build_waiting_conditions(
        bias_data["bias"], po3, retracement, weakness, in_kill_zone, in_zone
    )
    forbidden_reasons = build_forbidden_reasons(
        bias_data["bias"], po3, retracement, market_state,
        chip_bias=chip.get("bias") if chip else None,
    )

    return {
        "symbol":             symbol,
        "current_price":      price,
        "bias":               bias_data,
        "market_state":       market_state,
        "entry_status":       entry_status,
        "decision":           decision,
        "structure":          h1_structure,
        "in_kill_zone":       in_kill_zone,
        "weekly_open":        weekly_open,
        "daily_open":         daily_open,
        # Analysis modules
        "po3":                po3,
        "retracement":        retracement,
        "weakness":           weakness,
        "entry_timing":       entry_timing,
        # New modules
        "session":            session_info,
        "asia_sweep":         asia_sweep,
        "breakout":           breakout_info,
        # Trade grade
        "grade":              grade_result["grade"],
        "signal":             grade_result["signal"],
        "action":             grade_result["action"],
        "no_trade_reasons":   grade_result["no_trade_reasons"],
        # SL/TP (only for A/B grade)
        "sltp": compute_sltp(bias_data["bias"], price, h1, liq_targets)
                if grade_result["grade"] in ("A", "B") else None,
        # Liquidation levels (estimated, no API key needed)
        "liquidation": estimate_liquidation_levels(price),
        # Decision text helpers (for Telegram)
        "waiting_conditions": waiting_conditions,
        "forbidden_reasons":  forbidden_reasons,
        # Liquidity
        "liquidity": {
            "asia_high":     asia_high,
            "asia_low":      asia_low,
            "prev_day_high": pdh,
            "prev_day_low":  pdl,
            "equal_highs":   eq_hl["equal_highs"],
            "equal_lows":    eq_hl["equal_lows"],
            "unswept_highs": unswept_highs[-3:],
            "unswept_lows":  unswept_lows[-3:],
            "targets":       liq_targets,
        },
    }
