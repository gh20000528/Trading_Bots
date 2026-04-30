from fastapi import APIRouter
import pandas as pd
from app.services.market_service import get_ohlcv
from app.services.analysis_service import get_analysis, get_multi_tf_analysis, interpret_signal

router = APIRouter(prefix="/analysis", tags=["analysis"])

SYMBOL_MAP = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "BNB": "BNB/USDT",
    "SOL": "SOL/USDT",
}

BAR_SECONDS = {"1h": 3600, "5m": 300, "1d": 86400}


@router.get("/chart/{symbol}")
async def get_chart_data(symbol: str, timeframe: str = "1h"):
    ccxt_symbol = SYMBOL_MAP.get(symbol)
    if not ccxt_symbol:
        return {"error": "unsupported symbol"}

    limit = {"1h": 500, "4h": 400, "1d": 300}.get(timeframe, 500)
    ohlcv = await get_ohlcv(ccxt_symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])

    h1_analysis = await get_analysis(ccxt_symbol, timeframe, swing_length=5, df=df.copy())
    daily_analysis = await get_analysis(ccxt_symbol, "1d", swing_length=5)
    m5_analysis = await get_analysis(ccxt_symbol, "5m", swing_length=3)

    signal = interpret_signal({"daily": daily_analysis, "1h": h1_analysis, "5m": m5_analysis})

    timestamps_sec = [int(row[0] / 1000) for row in ohlcv]
    last_time = timestamps_sec[-1]
    future_time = last_time + 20 * BAR_SECONDS.get(timeframe, 3600)

    candles = [
        {"time": int(row[0] / 1000), "open": row[1], "high": row[2], "low": row[3], "close": row[4]}
        for row in ohlcv
    ]

    ob_zones = []
    for ob in h1_analysis["ob"]:
        if ob["MitigatedIndex"] != 0.0:
            continue
        idx = ob.get("ob_index")
        if idx is None:
            continue
        idx = int(idx)
        ob_zones.append({
            "top": ob["Top"],
            "bottom": ob["Bottom"],
            "direction": "bull" if ob["OB"] == 1.0 else "bear",
            "start_time": timestamps_sec[idx] if idx < len(timestamps_sec) else last_time,
            "end_time": future_time,
        })

    fvg_zones = []
    for fvg in h1_analysis["fvg"]:
        if fvg.get("MitigatedIndex") != 0:
            continue
        idx = fvg.get("fvg_index")
        if idx is None:
            continue
        idx = int(idx)
        fvg_zones.append({
            "top": fvg["Top"],
            "bottom": fvg["Bottom"],
            "direction": "bull" if fvg["FVG"] == 1.0 else "bear",
            "start_time": timestamps_sec[idx] if idx < len(timestamps_sec) else last_time,
            "end_time": future_time,
        })

    return {
        "candles": candles,
        "ob_zones": ob_zones,
        "fvg_zones": fvg_zones,
        "signal": signal,
    }


@router.get("/{symbol}")
async def get_analysis_result(symbol: str):
    ccxt_symbol = SYMBOL_MAP.get(symbol)
    if not ccxt_symbol:
        return {"error": "symbol not supported"}

    result = await get_multi_tf_analysis(ccxt_symbol)
    analysis = interpret_signal(result)
    return [result, analysis]
