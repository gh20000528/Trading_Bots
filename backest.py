import asyncio
import pandas as pd
import ccxt.async_support as ccxt
from datetime import datetime, timezone
from app.services.analysis_service import get_analysis, interpret_signal

async def fetch_from_bingx(symbol):
    exchange = ccxt.bingx()
    all_1h = []
    all_5m = []

    since = None
    for _ in range(12):
        batch = await exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
        if not batch:
            break
        all_1h = batch + all_1h
        since = batch[0][0] - 1000 * 60 * 60 * 1000

    since_5m = None
    for _ in range(36):
        batch = await exchange.fetch_ohlcv(symbol, "5m", since=since_5m, limit=1000)
        if not batch:
            break
        all_5m = batch + all_5m
        since_5m = batch[0][0] - 1000 * 5 * 60 * 1000

    ohlcv_1d = await exchange.fetch_ohlcv(symbol, "1d", limit=200)
    await exchange.close()
    return all_1h, all_5m, ohlcv_1d

async def fetch_from_binance(symbol):
    exchange = ccxt.binance({"enableRateLimit": True})
    all_1h = []
    all_5m = []

    since = None
    for _ in range(12):
        batch = await exchange.fetch_ohlcv(symbol, "1h", since=since, limit=1000)
        if not batch:
            break
        all_1h = batch + all_1h
        since = batch[0][0] - 1000 * 60 * 60 * 1000

    since_5m = None
    for _ in range(36):
        batch = await exchange.fetch_ohlcv(symbol, "5m", since=since_5m, limit=1000)
        if not batch:
            break
        all_5m = batch + all_5m
        since_5m = batch[0][0] - 1000 * 5 * 60 * 1000

    ohlcv_1d = await exchange.fetch_ohlcv(symbol, "1d", limit=200)
    await exchange.close()
    return all_1h, all_5m, ohlcv_1d

async def fetch_historical(symbol, source="binance"):
    if source == "binance":
        all_1h, all_5m, ohlcv_1d = await fetch_from_binance(symbol)
    else:
        all_1h, all_5m, ohlcv_1d = await fetch_from_bingx(symbol)

    df_1h = pd.DataFrame(all_1h, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_1h = df_1h.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)

    df_5m = pd.DataFrame(all_5m, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_5m = df_5m.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)

    df_1d = pd.DataFrame(ohlcv_1d, columns=["timestamp", "open", "high", "low", "close", "volume"])

    return df_1h, df_1d, df_5m

async def run_backest(symbol, swing_length, window=100, lookahead=48, source="binance"):
    df_1h, df_1d, df_5m = await fetch_historical(symbol, source=source)
    print(f"1H: {len(df_1h)} 根，從 {datetime.fromtimestamp(df_1h.iloc[0]['timestamp']/1000).strftime('%Y-%m-%d')}")
    print(f"5m: {len(df_5m)} 根，從 {datetime.fromtimestamp(df_5m.iloc[0]['timestamp']/1000).strftime('%Y-%m-%d')}")
    results = []
    seen_zones = {}  # zone_key -> last_traded_timestamp

    for i in range(window, len(df_1h) - lookahead):
        window_1h = df_1h.iloc[i - window:i].reset_index(drop=True)

        current_ts = df_1h.iloc[i - 1]["timestamp"]

        # Kill Zone 過濾：London 02-05 UTC，NY 13-16 UTC
        # current_hour = datetime.fromtimestamp(current_ts / 1000, tz=timezone.utc).hour
        # if not (2 <= current_hour < 5 or 13 <= current_hour < 16):
        #     continue

        daily_window = df_1d[df_1d["timestamp"] <= current_ts].tail(100).reset_index(drop=True)
        if len(daily_window) < 20:
            continue

        m5_window = df_5m[df_5m["timestamp"] <= current_ts].tail(100).reset_index(drop=True)
        if len(m5_window) < 20:
            continue

        h1_analysis = await get_analysis(symbol, "1h", swing_length, df=window_1h)
        daily_analysis = await get_analysis(symbol, "1d", swing_length, df=daily_window)
        m5_analysis = await get_analysis(symbol, "5m", 3, df=m5_window)
        multi = {"daily": daily_analysis, "1h": h1_analysis, "5m": m5_analysis}
        signal = interpret_signal(multi)

        if signal["entry_zone"] is None:
            continue

        zone_key = (signal["entry_zone"]["top"], signal["entry_zone"]["bottom"])
        if zone_key in seen_zones and current_ts - seen_zones[zone_key] < 24 * 60 * 60 * 1000:
            continue
        seen_zones[zone_key] = current_ts

        entry = (signal["entry_zone"]["top"] + signal["entry_zone"]["bottom"]) / 2
        sl = signal["stop_loss"]
        if sl is None:
            continue

        tp = signal["take_profit"]
        if tp is None:
            continue

        min_distance = entry * 0.005
        if abs(tp - entry) < min_distance:
            continue

        future = df_1h.iloc[i:i + lookahead]
        ob_top = signal["entry_zone"]["top"]
        ob_bottom = signal["entry_zone"]["bottom"]

        if signal["bias"] == "bullish":
            enters_ob = any(future["low"] <= ob_top)
        else:
            enters_ob = any(future["high"] >= ob_bottom)

        if not enters_ob:
            continue

        hit_tp = any(future["high"] >= tp) if signal["bias"] == "bullish" else any(future["low"] <= tp)
        hit_sl = any(future["low"] <= sl) if signal["bias"] == "bullish" else any(future["high"] >= sl)

        if hit_tp and hit_sl:
            tp_index = future[future["high"] >= tp].index[0] if signal["bias"] == "bullish" else future[future["low"] <= tp].index[0]
            sl_index = future[future["low"] <= sl].index[0] if signal["bias"] == "bullish" else future[future["high"] >= sl].index[0]
            outcome = "win" if tp_index < sl_index else "loss"
        elif hit_tp:
            outcome = "win"
        elif hit_sl:
            outcome = "loss"
        else:
            outcome = "open"

        time_str = datetime.fromtimestamp(df_1h.iloc[i]["timestamp"] / 1000).strftime("%Y-%m-%d %H:%M")

        results.append({
            "time": time_str,
            "bias": signal["bias"],
            "entry": round(entry, 2),
            "sl": round(sl, 2),
            "tp": round(tp, 2),
            "outcome": outcome
        })

    return results

async def main():
    symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "SUI/USDT"]

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"回測標的: {symbol}")
        print(f"{'='*60}")
        results = await run_backest(symbol, swing_length=5, source="binance")

        total = len(results)
        wins = len([r for r in results if r["outcome"] == "win"])
        losses = len([r for r in results if r["outcome"] == "loss"])
        opens = len([r for r in results if r["outcome"] == "open"])

        if total > 0:
            df = pd.DataFrame(results)
            print(df.to_string(index=False))
            print(f"\n信號: {total} | 勝: {wins} | 敗: {losses} | 未結: {opens} | 勝率: {round(wins/total*100,1)}%")
        else:
            print("無信號")

asyncio.run(main())
