import asyncio
from datetime import datetime, timezone, timedelta
from app.services.assistant_service import build_assistant_report
from app.services.notification_service import send_telegram
from app.services.sent_signal_service import save_signal, get_open_signals, update_outcome
from app.database import AsyncSessionLocal
from app.config import settings

SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
    "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT",
    "ADA/USDT", "SUI/USDT",
]
SCAN_INTERVAL        = 60
INTER_SYMBOL_DELAY   = 3   # 每個幣之間暫停幾秒，避免打爆 BingX rate limit

# 冷卻時間（A 級積極，B 級保守）
COOLDOWN = {"A": 30 * 60, "B": 2 * 60 * 60}

# 勝負判斷閾值
WIN_PCT  = 0.020   # 同向漲/跌 2% → win
LOSS_PCT = 0.015   # 反向漲/跌 1.5% → loss
EXPIRE_H = 24      # 24 小時未結果 → expired

_last_notified: dict[str, float] = {}


def _grade_emoji(grade: str) -> str:
    return {"A": "🟢", "B": "🟡", "C": "🔴"}.get(grade, "⬜")


def _format_message(report: dict, now_str: str) -> str:
    name    = report["symbol"].replace("/USDT", "")
    signal  = report["signal"]
    bias    = report["bias"]
    entry   = report["entry_status"]
    liq     = report["liquidity"]
    chip    = report.get("chip", {})
    po3     = report.get("po3", {})
    ret     = report.get("retracement", {})
    wk      = report.get("weakness", {})
    sess    = report.get("session", {})
    brk     = report.get("breakout", {})
    asia_sw = report.get("asia_sweep")
    timing  = report.get("entry_timing", "—")
    price   = report["current_price"]

    grade       = report.get("grade", "C")
    action      = report.get("action", "—")
    sig_emoji   = _grade_emoji(grade)
    bias_emoji  = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}[bias["bias"]]
    bias_label  = {"bullish": "看多", "bearish": "看空", "neutral": "中立"}[bias["bias"]]

    # 進場條件
    met_lines  = [f"✅ {c}" for c in entry["met"]]
    miss_lines = [f"❌ {c}" for c in entry["missing"]]
    conditions = "\n".join(met_lines + miss_lines) or "（無）"

    # 流動性
    liq_parts = []
    if liq.get("asia_high"):     liq_parts.append(f"Asia H:{round(liq['asia_high'],2)}")
    if liq.get("asia_low"):      liq_parts.append(f"Asia L:{round(liq['asia_low'],2)}")
    if liq.get("prev_day_high"): liq_parts.append(f"PDH:{round(liq['prev_day_high'],2)}")
    if liq.get("prev_day_low"):  liq_parts.append(f"PDL:{round(liq['prev_day_low'],2)}")
    liq_str = " | ".join(liq_parts) if liq_parts else "—"

    # Liquidity Targets
    targets = liq.get("targets", [])
    tgt_lines = []
    for t in targets[:4]:
        side_arrow = "↑" if t["side"] == "above" else "↓"
        tgt_lines.append(
            f"  {t['type']} {side_arrow} {t['level']}  ({'+' if t['dist_pct'] >= 0 else ''}{t['dist_pct']}%)"
        )
    tgt_str = "\n".join(tgt_lines) if tgt_lines else "  —"

    # Session
    kz_str   = f"⚡ {sess.get('kill_zone', '')}" if sess.get("in_kill_zone") else "⏸ 非 Kill Zone"
    sess_str = f"\n📅 Session：{sess.get('session','—')}  {kz_str}"
    if asia_sw:
        sess_str += f"\n{asia_sw['note']}"

    # Chip
    chip_str = ""
    if chip:
        ce = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(chip.get("bias", ""), "")
        chip_str = f"\n籌碼：{ce} {chip.get('score', 0)}/{chip.get('max_score', 6)}"

    # PO3
    po3_str = f"\nPO3：{po3.get('state', '—')}" if po3.get("state") else ""

    # Retracement
    ret_str = ""
    if ret.get("available"):
        near = ret["nearest_fib"]
        ret_str = f"\nFib：{ret['pullback_type']}（{near['ratio']*100:.1f}% @ {near['price']}）"
        if ret["in_confluence"]:
            ret_str += " 🔥"

    # Weakness
    wk_str = (f"\nWeakness：{wk.get('score',0)}/{wk.get('max_score',4)}"
              f" {' '.join(wk.get('conditions_met', []))}") if wk else ""

    # Breakout
    brk_parts = []
    if brk.get("fake_breaks"):  brk_parts.append(f"Fake：{', '.join(brk['fake_breaks'])}")
    if brk.get("real_breaks"):  brk_parts.append(f"Real：{', '.join(brk['real_breaks'])}")
    brk_str = f"\nBreakout：{' | '.join(brk_parts)}" if brk_parts else ""

    # Entry timing
    timing_label = {"right_side": "✅ 右側確認", "left_side": "⚠️ 左側（待確認）", "no_setup": "❌ 無進場區"}.get(timing, timing)

    # 升 A 條件（B 級專用）
    missing = report.get("no_trade_reasons", [])
    missing_str = ("\n升 A 需要：\n" + "\n".join(f"・{m}" for m in missing)) if grade == "B" and missing else ""

    return (
        f"\n{sig_emoji} {grade} 級｜{signal}｜{name}/USDT"
        f"\n━━━━━━━━━━━━━━━━"
        f"\n📍 {round(price,2)}"
        f"\n{bias_emoji} Bias：{bias_label} {bias['score']}/{bias['max_score']}"
        f"\n📊 State：{report['market_state']}  🔖 {report['structure']}"
        f"{sess_str}"
        f"{po3_str}"
        f"{ret_str}"
        f"\n⏱ Entry Timing：{timing_label}"
        f"\n⚡ Entry：{entry['status']} {entry['label']}{chip_str}"
        f"{wk_str}"
        f"{brk_str}"
        f"\n━━━━━━━━━━━━━━━━"
        f"\n進場條件："
        f"\n{conditions}"
        f"\n━━━━━━━━━━━━━━━━"
        f"\n流動性目標："
        f"\n{tgt_str}"
        f"\n流動性：{liq_str}"
        f"\n━━━━━━━━━━━━━━━━"
        f"\n👉 {action}"
        f"{missing_str}"
        f"\n時間：{now_str}"
    )


async def _check_outcomes():
    """掃描所有 open 信號，根據當前價格自動判斷勝負"""
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        open_signals = await get_open_signals(db)
        for sig in open_signals:
            try:
                if sig.sent_at and (now - sig.sent_at.replace(tzinfo=timezone.utc)) > timedelta(hours=EXPIRE_H):
                    await update_outcome(db, sig.id, "expired", sig.current_price or 0)
                    print(f"[Scanner] ⏰ {sig.symbol} #{sig.id} 過期 → expired")
                    continue

                report = await build_assistant_report(sig.symbol)
                curr   = report["current_price"]
                entry  = sig.current_price
                if not entry or entry == 0:
                    continue

                change = (curr - entry) / entry

                if sig.bias == "bullish":
                    if change >= WIN_PCT:
                        await update_outcome(db, sig.id, "win", curr)
                        print(f"[Scanner] ✅ {sig.symbol} #{sig.id} → win ({round(change*100,1)}%)")
                    elif change <= -LOSS_PCT:
                        await update_outcome(db, sig.id, "loss", curr)
                        print(f"[Scanner] ❌ {sig.symbol} #{sig.id} → loss ({round(change*100,1)}%)")

                elif sig.bias == "bearish":
                    if change <= -WIN_PCT:
                        await update_outcome(db, sig.id, "win", curr)
                        print(f"[Scanner] ✅ {sig.symbol} #{sig.id} → win ({round(change*100,1)}%)")
                    elif change >= LOSS_PCT:
                        await update_outcome(db, sig.id, "loss", curr)
                        print(f"[Scanner] ❌ {sig.symbol} #{sig.id} → loss ({round(change*100,1)}%)")

            except Exception as e:
                print(f"[Scanner] outcome check 失敗 #{sig.id}: {e}")


async def _scan_once():
    now_ts  = datetime.now(timezone.utc).timestamp()
    now_str = datetime.now(timezone.utc).strftime("%H:%M UTC")

    for i, symbol in enumerate(SYMBOLS):
        try:
            report = await build_assistant_report(symbol)
        except Exception as e:
            print(f"[Scanner] {symbol} 分析失敗: {e}")
            await asyncio.sleep(INTER_SYMBOL_DELAY)
            continue

        grade  = report.get("grade", "C")
        signal = report["signal"]

        # C 級直接跳過
        if grade == "C":
            reasons = report.get("no_trade_reasons", [])
            print(f"[Scanner] {symbol} → C | {reasons[0] if reasons else '—'}")
            await asyncio.sleep(INTER_SYMBOL_DELAY)
            continue

        # 冷卻檢查（A=30分、B=2小時，key 加 grade 以免互相干擾）
        cooldown = COOLDOWN.get(grade, COOLDOWN["B"])
        last     = _last_notified.get(f"{symbol}_{grade}", 0)
        if now_ts - last < cooldown:
            remaining = int((cooldown - (now_ts - last)) / 60)
            print(f"[Scanner] {symbol} {grade} 級冷卻中（{remaining} 分後可再發）")
            await asyncio.sleep(INTER_SYMBOL_DELAY)
            continue

        message = _format_message(report, now_str)
        sent    = await send_telegram(settings.telegram_token, settings.telegram_chat_id, message)

        if sent:
            _last_notified[f"{symbol}_{grade}"] = now_ts
            print(f"[Scanner] {grade} | {signal} {symbol} | {report['bias']['bias']} | {report['market_state']}")

            chip = report.get("chip", {})
            sltp = report.get("sltp") or {}
            async with AsyncSessionLocal() as db:
                await save_signal(db, {
                    "symbol":        symbol,
                    "bias":          report["bias"]["bias"],
                    "bias_score":    report["bias"]["score"],
                    "grade":         grade,
                    "market_state":  report["market_state"],
                    "structure":     report["structure"],
                    "entry_status":  signal,
                    "current_price": report["current_price"],
                    "decision":      report["decision"],
                    "chip_bias":     chip.get("bias"),
                    "chip_score":    chip.get("score"),
                    "session":       report.get("session", {}).get("session"),
                    "sl":            sltp.get("sl"),
                    "tp1":           sltp.get("tp1"),
                    "rr1":           sltp.get("rr1"),
                })
        else:
            print(f"[Scanner] ❌ {symbol} 通知發送失敗")

        await asyncio.sleep(INTER_SYMBOL_DELAY)


async def start_scanner():
    print("[Scanner] 啟動，每 1 分鐘掃描一次")
    while True:
        try:
            await _check_outcomes()
            await _scan_once()
        except Exception as e:
            print(f"[Scanner] 掃描錯誤: {e}")
        await asyncio.sleep(SCAN_INTERVAL)
