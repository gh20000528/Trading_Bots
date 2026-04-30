"""
籌碼面分析 (Chip / Flow Analysis)

指標：
  - Funding Rate  → 反向指標，負值代表空單付費（市場偏多信號）
  - OI Change     → OI ↑ + Price ↑ = 真趨勢；OI ↑ + Price ↓ = 空頭佈局
  - Long/Short    → 極端多 = 反向空信號；極端空 = 反向多信號
  - CVD           → 累積量差，判斷誰在主導買賣

資料來源：
  - Funding Rate / L/S Ratio → Binance Futures 公開 API
  - Open Interest            → BingX (ccxt)
  - CVD                      → 從 OHLCV 近似計算
"""

import asyncio
import httpx
import ccxt.async_support as ccxt
from app.services.market_service import get_ohlcv
from app.config import settings

_futures = ccxt.bingx()


# ─── 資料取得 ─────────────────────────────────────────────────────────────────

async def _get_funding_rate(symbol_binance: str) -> float | None:
    """從 Binance Futures 取目前資金費率（免費公開端點）"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(
                "https://fapi.binance.com/fapi/v1/premiumIndex",
                params={"symbol": symbol_binance},
            )
            return float(res.json()["lastFundingRate"])
    except Exception:
        return None


async def _get_oi_change(symbol_binance: str) -> float | None:
    """
    從 Binance Futures OI 歷史 API 取最近兩筆 1H 資料，計算百分比變化。
    不依賴記憶體 cache，重啟後仍然準確。
    """
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(
                "https://fapi.binance.com/futures/data/openInterestHist",
                params={"symbol": symbol_binance, "period": "1h", "limit": 2},
            )
            data = res.json()
            if isinstance(data, list) and len(data) >= 2:
                curr = float(data[-1]["sumOpenInterestValue"])
                prev = float(data[-2]["sumOpenInterestValue"])
                if prev > 0:
                    return (curr - prev) / prev * 100
    except Exception:
        pass
    return None


async def _get_long_short_ratio(symbol_binance: str) -> float | None:
    """從 Binance Futures 取全球多空比"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(
                "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                params={"symbol": symbol_binance, "period": "5m", "limit": 1},
            )
            return float(res.json()[0]["longShortRatio"])
    except Exception:
        return None


async def _get_real_cvd_trend(symbol_binance: str) -> str | None:
    """
    Coinalyze 真實 CVD（需設定 COINALYZE_API_KEY）。
    symbol 格式：BTCUSDT → BTCUSDT_PERP.A（Binance Perpetual）
    回傳 'rising' | 'falling' | 'neutral'
    """
    if not settings.coinalyze_api_key:
        return None
    coinalyze_sym = symbol_binance + "_PERP.A"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            res = await client.get(
                "https://api.coinalyze.net/v1/delta",
                params={
                    "symbols":  coinalyze_sym,
                    "interval": "1hour",
                    "limit":    3,
                    "api_key":  settings.coinalyze_api_key,
                },
            )
            data = res.json()
            if isinstance(data, list) and data:
                deltas = [d["delta"] for d in data[0].get("history", []) if "delta" in d]
                if len(deltas) >= 2:
                    net = sum(deltas[-3:])
                    if net > 0:  return "rising"
                    if net < 0:  return "falling"
                    return "neutral"
    except Exception:
        pass
    return None


def _compute_cvd_trend(ohlcv: list, lookback: int = 20) -> str:
    """
    從 OHLCV 近似 CVD（Cumulative Volume Delta）。
    多頭 K 棒（close > open）計正量，空頭 K 棒計負量，
    最後 N 根的淨量 > 0 代表買方主導。
    """
    recent = ohlcv[-lookback:]
    if not recent:
        return "neutral"
    net = sum(
        c[5] if c[4] > c[1] else -c[5]
        for c in recent
    )
    if net > 0:
        return "rising"
    if net < 0:
        return "falling"
    return "neutral"


# ─── 評分 ─────────────────────────────────────────────────────────────────────

def _score(funding_rate, oi_change_pct, long_short_ratio, cvd_trend) -> dict:
    """
    籌碼分數 (−6 ～ +6)：
      Funding Rate  : ±1 / ±2
      OI Change     : ±1
      L/S Ratio     : ±1 / ±2
      CVD           : ±1

    Chip Bias：>= +2 = bullish，<= -2 = bearish，其餘 = neutral
    """
    score = 0
    reasons = []

    # ── Funding Rate ─────────────────────────────────────────────
    if funding_rate is not None:
        fr_pct = round(funding_rate * 100, 4)
        if funding_rate < -0.0002:          # < -0.02%，空單付費
            score += 2
            reasons.append(f"FR {fr_pct}%：空單付費，偏多 (+2)")
        elif funding_rate < 0:
            score += 1
            reasons.append(f"FR {fr_pct}%：輕微偏多 (+1)")
        elif funding_rate > 0.001:          # > 0.1%，多單極度擠擁
            score -= 2
            reasons.append(f"FR {fr_pct}%：多單擠擁，反向偏空 (-2)")
        elif funding_rate > 0.0005:         # > 0.05%，偏高
            score -= 1
            reasons.append(f"FR {fr_pct}%：輕微偏空 (-1)")
        else:
            reasons.append(f"FR {fr_pct}%：中性 (0)")

    # ── OI Change ────────────────────────────────────────────────
    if oi_change_pct is not None:
        if oi_change_pct > 5:
            score += 1
            reasons.append(f"OI +{round(oi_change_pct,1)}%：資金流入 (+1)")
        elif oi_change_pct < -5:
            score -= 1
            reasons.append(f"OI {round(oi_change_pct,1)}%：資金流出 (-1)")
        else:
            reasons.append(f"OI {round(oi_change_pct,1)}%：中性 (0)")

    # ── Long/Short Ratio ─────────────────────────────────────────
    if long_short_ratio is not None:
        if long_short_ratio < 0.7:          # 空單極度擠擁，反向多
            score += 2
            reasons.append(f"L/S {round(long_short_ratio,2)}：空方擠擁，反向偏多 (+2)")
        elif long_short_ratio < 0.85:
            score += 1
            reasons.append(f"L/S {round(long_short_ratio,2)}：空方偏多，反向輕多 (+1)")
        elif long_short_ratio > 2.0:
            score -= 2
            reasons.append(f"L/S {round(long_short_ratio,2)}：多方擠擁，反向偏空 (-2)")
        elif long_short_ratio > 1.5:
            score -= 1
            reasons.append(f"L/S {round(long_short_ratio,2)}：多方偏多，輕空 (-1)")
        else:
            reasons.append(f"L/S {round(long_short_ratio,2)}：中性 (0)")

    # ── CVD ──────────────────────────────────────────────────────
    cvd_map = {"rising": (1, "↑ 買方主導 (+1)"), "falling": (-1, "↓ 賣方主導 (-1)"), "neutral": (0, "中性 (0)")}
    d, label = cvd_map.get(cvd_trend, (0, "—"))
    score += d
    reasons.append(f"CVD {label}")

    if score >= 2:
        chip_bias = "bullish"
    elif score <= -2:
        chip_bias = "bearish"
    else:
        chip_bias = "neutral"

    return {"score": score, "max_score": 6, "bias": chip_bias, "reasons": reasons}


# ─── 對外函式 ─────────────────────────────────────────────────────────────────

async def get_chip_data(
    symbol: str,        # "BTC/USDT"
    symbol_ccxt: str,   # "BTC/USDT:USDT"（保留供未來使用）
    symbol_binance: str # "BTCUSDT"
) -> dict:
    """取全部籌碼資料並計算 Chip Score"""
    funding_rate, oi_change_pct, long_short_ratio, ohlcv_1h, real_cvd = await asyncio.gather(
        _get_funding_rate(symbol_binance),
        _get_oi_change(symbol_binance),
        _get_long_short_ratio(symbol_binance),
        get_ohlcv(symbol, "1h", limit=24),
        _get_real_cvd_trend(symbol_binance),
    )
    # 優先用 Coinalyze 真實 CVD；沒有 API key 就退回 OHLCV 近似
    cvd_trend = real_cvd if real_cvd is not None else _compute_cvd_trend(ohlcv_1h)
    chip      = _score(funding_rate, oi_change_pct, long_short_ratio, cvd_trend)

    return {
        "funding_rate":     funding_rate,
        "oi_change_pct":    round(oi_change_pct, 2) if oi_change_pct is not None else None,
        "long_short_ratio": long_short_ratio,
        "cvd_trend":        cvd_trend,
        "score":            chip["score"],
        "max_score":        chip["max_score"],
        "bias":             chip["bias"],
        "reasons":          chip["reasons"],
    }
