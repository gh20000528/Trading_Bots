# 1. 呼叫已有的 get_ohlcv() 拿 K 線資料（從 BingX）
# 2. 把資料轉成 pandas DataFrame（因為 smartmoneyconcepts 吃的格式是 DataFrame）
# 3. 丟進套件，取出 FVG 和 OB 的偵測結果                                                              
# 4. 整理成乾淨的格式回傳   


import numpy as np
import pandas as pd
import smartmoneyconcepts as smc
from app.services.market_service import get_ohlcv

async def get_analysis (symbol:str, timeframe:str, swing_length: int):
    ohlcv = await get_ohlcv(symbol, timeframe, limit=100)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", 'volume'])

    swing_hl = smc.smc.swing_highs_lows(df, swing_length=swing_length)
    fvg_result = smc.smc.fvg(df)
    ob_result = smc.smc.ob(df, swing_hl)
    bos_result = smc.smc.bos_choch(df, swing_hl)

    return {
        "fvg": [item for item in fvg_result.replace({np.nan: None}).to_dict(orient='records') if item["FVG"] is not None] ,
        "ob": [item for item in ob_result.replace({np.nan: None}).to_dict(orient='records') if item["OB"] is not None],
        "bos_choch": [item for item in bos_result.replace({np.nan: None}).to_dict(orient='records') if item["CHOCH"] is not None],
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
    # h4 = anaslysis["4h"]
    h1 = anaslysis["1h"]
    m5 = anaslysis["5m"]

    # 判斷大方向
    bias = "neutral"
    if daily["bos_choch"]:
        last = daily["bos_choch"][-1]
        if last.get("CHOCH") == 1.0 or last.get("BOS") == 1.0:
            bias = "bullish"
        elif last.get("CHOCH") == -1.0 or last.get("BOS") == -1.0:
            bias = "bearish"

    # 4h 進場區間
    ob_direction = 1.0 if bias == "bullish" else -1.0
    active_obs = [ob for ob in h1["ob"] if ob["OB"] == ob_direction and ob["MitigatedIndex"] == 0.0]
    entry_zone = None
    if active_obs:
        lastest_ob = active_obs[-1]
        entry_zone = {"top": lastest_ob["Top"], "bottom": lastest_ob["Bottom"]}

    # 5m 確認
    confirmed = False
    if m5["bos_choch"]:
        last_5m = m5["bos_choch"][-1]
        if bias == "bullish" and (last_5m.get("CHOCH") == 1.0 or last_5m.get("BOS") == 1.0):
            confirmed = True
        elif bias == "bearish" and (last_5m.get("CHOCH") == -1.0 or last_5m.get("BOS") == -1.0):
            confirmed = True

    return {
        "bias": bias,
        "confirmed": confirmed,
        "entry_zone": entry_zone
    }    
