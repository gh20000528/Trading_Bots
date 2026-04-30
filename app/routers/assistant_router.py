import asyncio
import time
from fastapi import APIRouter, HTTPException, Response
from app.services.assistant_service import build_assistant_report, compute_trade_grade
from app.services.chip_service import get_chip_data

router = APIRouter(prefix="/assistant", tags=["assistant"])

CACHE_TTL = 60  # 秒

SYMBOL_MAP = {
    "BTC":  "BTC/USDT",
    "ETH":  "ETH/USDT",
    "SOL":  "SOL/USDT",
    "BNB":  "BNB/USDT",
    "XRP":  "XRP/USDT",
    "DOGE": "DOGE/USDT",
    "AVAX": "AVAX/USDT",
    "LINK": "LINK/USDT",
    "ADA":  "ADA/USDT",
    "SUI":  "SUI/USDT",
}

DASHBOARD_SYMBOLS = [
    {"key": "BTC",  "symbol": "BTC/USDT",  "symbol_ccxt": "BTC/USDT:USDT",  "symbol_binance": "BTCUSDT"},
    {"key": "ETH",  "symbol": "ETH/USDT",  "symbol_ccxt": "ETH/USDT:USDT",  "symbol_binance": "ETHUSDT"},
    {"key": "SOL",  "symbol": "SOL/USDT",  "symbol_ccxt": "SOL/USDT:USDT",  "symbol_binance": "SOLUSDT"},
    {"key": "BNB",  "symbol": "BNB/USDT",  "symbol_ccxt": "BNB/USDT:USDT",  "symbol_binance": "BNBUSDT"},
    {"key": "XRP",  "symbol": "XRP/USDT",  "symbol_ccxt": "XRP/USDT:USDT",  "symbol_binance": "XRPUSDT"},
    {"key": "DOGE", "symbol": "DOGE/USDT", "symbol_ccxt": "DOGE/USDT:USDT", "symbol_binance": "DOGEUSDT"},
    {"key": "AVAX", "symbol": "AVAX/USDT", "symbol_ccxt": "AVAX/USDT:USDT", "symbol_binance": "AVAXUSDT"},
    {"key": "LINK", "symbol": "LINK/USDT", "symbol_ccxt": "LINK/USDT:USDT", "symbol_binance": "LINKUSDT"},
    {"key": "ADA",  "symbol": "ADA/USDT",  "symbol_ccxt": "ADA/USDT:USDT",  "symbol_binance": "ADAUSDT"},
    {"key": "SUI",  "symbol": "SUI/USDT",  "symbol_ccxt": "SUI/USDT:USDT",  "symbol_binance": "SUIUSDT"},
]

_cache_data: list | None = None
_cache_time: float = 0.0
_cache_lock = asyncio.Lock()
_sem = asyncio.Semaphore(4)   # 最多 4 個幣同時請求，避免打爆 BingX rate limit


async def _build_row(s: dict) -> dict:
    async with _sem:
        report, chip = await asyncio.gather(
            build_assistant_report(s["symbol"]),
            get_chip_data(s["symbol"], s["symbol_ccxt"], s["symbol_binance"]),
        )
    # Recompute grade with chip data now available
    grade_result = compute_trade_grade(
        report["bias"], report["market_state"], report["entry_status"],
        report["po3"], report["retracement"], report["weakness"],
        report["entry_timing"], report["breakout"], report["session"],
        chip=chip,
    )
    return {
        **report, "chip": chip,
        "grade":            grade_result["grade"],
        "signal":           grade_result["signal"],
        "action":           grade_result["action"],
        "no_trade_reasons": grade_result["no_trade_reasons"],
    }


async def _fetch_fresh() -> list:
    tasks = [_build_row(s) for s in DASHBOARD_SYMBOLS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        r if not isinstance(r, Exception) else {"symbol": s["symbol"], "error": str(r)}
        for r, s in zip(results, DASHBOARD_SYMBOLS)
    ]


@router.get("/dashboard")
async def get_dashboard(response: Response, force: bool = False):
    """
    回傳所有 symbol 的完整分析（ICT + 籌碼）。
    結果會 cache 60 秒，重複呼叫立刻回傳。
    force=true 可強制略過 cache 重新取得。
    """
    global _cache_data, _cache_time

    now = time.monotonic()

    # 快取命中
    if not force and _cache_data is not None and (now - _cache_time) < CACHE_TTL:
        age = int(now - _cache_time)
        response.headers["X-Cache"]     = "HIT"
        response.headers["X-Cache-Age"] = str(age)
        return _cache_data

    # 快取過期或 force=true → 重新取得
    # Lock 確保多個同時請求只打一次 API
    async with _cache_lock:
        now = time.monotonic()
        if not force and _cache_data is not None and (now - _cache_time) < CACHE_TTL:
            # 別的請求已在 lock 內更新完畢
            age = int(now - _cache_time)
            response.headers["X-Cache"]     = "HIT"
            response.headers["X-Cache-Age"] = str(age)
            return _cache_data

        _cache_data = await _fetch_fresh()
        _cache_time = time.monotonic()

    response.headers["X-Cache"]     = "MISS"
    response.headers["X-Cache-Age"] = "0"
    return _cache_data


@router.get("/{symbol}")
async def get_assistant(symbol: str):
    key = symbol.upper()
    if key not in SYMBOL_MAP:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not supported")
    try:
        return await build_assistant_report(SYMBOL_MAP[key])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
