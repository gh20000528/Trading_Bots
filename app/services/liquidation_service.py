"""
Liquidation Level Service

Two modes:
  1. Estimated levels — derived from price × common leverage ratios (no API key needed)
  2. CoinGlass API    — real exchange liquidation heatmap (requires COINGLASS_API_KEY)

Estimated logic:
  At Nx leverage, a long is liquidated when price falls ~(1/N × 90%) from entry.
  e.g. 10x long: liquidated at price × (1 - 0.09) = -9%
  Short liquidated symmetrically above.
"""

import httpx
from app.config import settings

LEVERAGE_LEVELS = [10, 25, 50, 100]


def estimate_liquidation_levels(price: float) -> dict:
    """
    Return estimated long / short liquidation clusters based on common leverage.
    Values show PRICE where leveraged positions would be liquidated.
    """
    long_liq  = {}
    short_liq = {}
    for lev in LEVERAGE_LEVELS:
        drop = 0.9 / lev          # ~90% margin used → liquidated
        long_liq[lev]  = round(price * (1 - drop), 2)
        short_liq[lev] = round(price * (1 + drop), 2)

    return {
        "source":     "estimated",
        "long_liq":   long_liq,    # { 10: price, 25: price, … }
        "short_liq":  short_liq,
    }


async def get_coinglass_liq_levels(symbol_binance: str) -> dict | None:
    """
    Fetch real liquidation clusters from CoinGlass API.
    Requires settings.coinglass_api_key to be set.
    Returns None if key missing or API fails.
    """
    if not settings.coinglass_api_key:
        return None

    coin = symbol_binance.replace("USDT", "")   # "BTCUSDT" → "BTC"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(
                "https://open-api.coinglass.com/public/v2/liquidation_history",
                params={"symbol": coin, "time_type": "h4"},
                headers={"coinglassSecret": settings.coinglass_api_key},
            )
            data = res.json()
            if data.get("code") == "0" and data.get("data"):
                return {"source": "coinglass", "data": data["data"]}
    except Exception:
        pass
    return None


async def get_liquidation_map(price: float, symbol_binance: str) -> dict:
    """
    Returns liquidation map: CoinGlass if key set, otherwise estimated.
    Always includes estimated levels as fallback.
    """
    estimated = estimate_liquidation_levels(price)
    cg = await get_coinglass_liq_levels(symbol_binance)

    return {
        "estimated": estimated,
        "coinglass": cg,           # None if no API key
        "has_real_data": cg is not None,
    }
