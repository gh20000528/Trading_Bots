# 1. 呼叫已有的 get_ohlcv() 拿 K 線資料（從 BingX）
# 2. 把資料轉成 pandas DataFrame（因為 smartmoneyconcepts 吃的格式是 DataFrame）
# 3. 丟進套件，取出 FVG 和 OB 的偵測結果                                                              
# 4. 整理成乾淨的格式回傳   


import numpy as np
import pandas as pd
import smartmoneyconcepts as smc
from app.services.market_service import get_ohlcv

async def get_analysis (symbol:str, timeframe:str, swing_length: int, df=None):
    if df is None:
        ohlcv = await get_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", 'volume'])


    swing_hl = smc.smc.swing_highs_lows(df, swing_length=swing_length)
    fvg_result = smc.smc.fvg(df)
    ob_result = smc.smc.ob(df, swing_hl)
    bos_result = smc.smc.bos_choch(df, swing_hl)
    london_kz = smc.smc.sessions(df, session="London open kill zone", time_zone="UTC+0")
    ny_kz = smc.smc.sessions(df, session="New York kill zone", time_zone="UTC+0")
    in_kill_zone = bool(london_kz["Active"].iloc[-1] == 1 or ny_kz["Active"].iloc[-1] == 1)
    liq_request = smc.smc.liquidity(df, swing_hl)

    return {
        "fvg": [item for item in fvg_result.copy().assign(fvg_index=fvg_result.index).replace({np.nan: None}).to_dict(orient='records') if item["FVG"] is not None],
        "ob": [item for item in ob_result.copy().assign(ob_index=ob_result.index).replace({np.nan: None}).to_dict(orient='records') if item["OB"] is not None],
        "bos_choch": [item for item in bos_result.replace({np.nan: None}).to_dict(orient='records') if item["CHOCH"] is not None],
        "in_kill_zone": in_kill_zone,
        "liquidity": [item for item in liq_request.replace({np.nan: None}).to_dict(orient='records') if item["Liquidity"] is not None],
        "recent_high": float(df["high"].iloc[-50:].max()),
        "recent_low": float(df["low"].iloc[-50:].min()),
        "last_close": float(df["close"].iloc[-1]),
        "prev_high": float(df["high"].iloc[-2]) if len(df) >= 2 else None,
        "prev_low": float(df["low"].iloc[-2]) if len(df) >= 2 else None,
    }

async def get_multi_tf_analysis(symbol):
    daily = await get_analysis(symbol, "1d", swing_length=5)
    # hour_4 = await get_analysis(symbol, "4h", swing_length=10)
    hour_1 = await get_analysis(symbol, "1h", swing_length=5)
    min_5 = await get_analysis(symbol, "5m", swing_length=3)

    return {
        "daily" : daily,
        # "4h": hour_4,
        "1h": hour_1,
        "5m": min_5
    }


def interpret_signal(anaslysis: dict) -> dict:
    daily = anaslysis["daily"]
    h1 = anaslysis["1h"]
    m5 = anaslysis["5m"]
    in_kill_zone = m5.get("in_kill_zone", False)

    # Change 1: Daily Bias 改用前一天高低點判斷
    bias = "neutral"
    last_close = daily.get("last_close")
    prev_high = daily.get("prev_high")
    prev_low = daily.get("prev_low")

    if last_close and prev_high and prev_low:
        if last_close > prev_high:
            bias = "bullish"
        elif last_close < prev_low:
            bias = "bearish"

    # Fallback: 前一天高低點沒突破時，用 BOS/CHoCH 判斷結構方向
    if bias == "neutral" and daily["bos_choch"]:
        last = daily["bos_choch"][-1]
        if last.get("CHOCH") == 1.0 or last.get("BOS") == 1.0:
            bias = "bullish"
        elif last.get("CHOCH") == -1.0 or last.get("BOS") == -1.0:
            bias = "bearish"

    # liquidity sweep
    liquidity_list = m5.get("liquidity", [])
    liq_direction = -1.0 if bias == "bullish" else 1.0
    liquidity_swept = any(
        item["Liquidity"] == liq_direction and item["Swept"] != 0.0 and item["Swept"] >= 80
        for item in liquidity_list
    )

    ob_direction = 1.0 if bias == "bullish" else -1.0
    choch_direction = 1.0 if bias == "bullish" else -1.0
    entry_zone = None

    # 優先 1: Extreme OB — 造成最近一次 1H CHOCH 的 OB
    recent_choch = next((c for c in reversed(h1["bos_choch"]) if c.get("CHOCH") == choch_direction), None)
    if recent_choch:
        choch_broken_index = recent_choch.get("BrokenIndex", 0)
        pre_choch_obs = [
            ob for ob in h1["ob"]
            if ob["OB"] == ob_direction
            and ob.get("ob_index", 0) < choch_broken_index
            and ob["MitigatedIndex"] == 0.0
        ]
        if pre_choch_obs:
            extreme_ob = max(pre_choch_obs, key=lambda x: x.get("ob_index", 0))
            entry_zone = {"top": extreme_ob["Top"], "bottom": extreme_ob["Bottom"], "source": "extreme_ob"}

    # 優先 2: 最新未 mitigate 的一般 OB
    if entry_zone is None:
        active_obs = [ob for ob in h1["ob"] if ob["OB"] == ob_direction and ob["MitigatedIndex"] == 0.0]
        if active_obs:
            entry_zone = {"top": active_obs[-1]["Top"], "bottom": active_obs[-1]["Bottom"], "source": "ob"}

    # 優先 3: 1H FVG 備選
    if entry_zone is None:
        active_fvgs = [f for f in h1["fvg"] if f["FVG"] == ob_direction and f.get("MitigatedIndex") == 0]
        if active_fvgs:
            latest_fvg = active_fvgs[-1]
            entry_zone = {"top": latest_fvg["Top"], "bottom": latest_fvg["Bottom"], "source": "fvg"}

    # 止盈止損
    stop_loss = None
    if entry_zone:
        if bias == "bullish":
            stop_loss = round(entry_zone["bottom"] * 0.999, 2)
        elif bias == "bearish":
            stop_loss = round(entry_zone["top"] * 1.001, 2)

    take_profit = None
    h1_liq = h1.get("liquidity",[])
    day_liq = daily.get("liquidity", [])
    if h1_liq:
        liq = h1_liq
    elif day_liq:
        liq = day_liq
    else:
        liq = m5.get("liquidity", [])
    unswept = [item for item in liq if item["Swept"] == 0]

    if entry_zone:
        if bias == "bullish":
            recent_high = m5.get("recent_high")
            if recent_high and recent_high > entry_zone["top"]:
                take_profit = round(recent_high, 2)
        elif bias == "bearish":
            recent_low = m5.get("recent_low")
            if recent_low and recent_low < entry_zone["bottom"]:
                take_profit = round(recent_low, 2)
        

    # 5m 確認
    confirmed = False
    if m5["bos_choch"]:
        last_5m = m5["bos_choch"][-1]
        if bias == "bullish" and (last_5m.get("CHOCH") == 1.0 or last_5m.get("BOS") == 1.0):
            confirmed = True
        elif bias == "bearish" and (last_5m.get("CHOCH") == -1.0 or last_5m.get("BOS") == -1.0):
            confirmed = True


    
    # print("h1 liquidity:", h1.get("liquidity", [])) 
    # print("daily liquidity:", daily.get("liquidity", [])) 
    return {
        "bias": bias,
        "confirmed": confirmed,
        "entry_zone": entry_zone,
        "in_kill_zone": in_kill_zone,
        "liquidity_swept": liquidity_swept,
        "stop_loss": stop_loss,
        "take_profit": take_profit
    }    
