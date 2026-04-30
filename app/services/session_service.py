"""
Session Context Service — Asia / London / NY session detection.

Kill Zones (UTC):
  London KZ : 02:00–05:00
  NY KZ     : 13:00–16:00

Session windows (UTC, approximate):
  Asia      : 00:00–08:00
  London    : 07:00–13:00  (overlaps NY open)
  NY        : 13:00–21:00
  Off-Hours : 21:00–00:00
"""
from datetime import datetime, timezone

KILL_ZONES = [
    {"name": "London KZ", "start": 2,  "end": 5},
    {"name": "NY KZ",     "start": 13, "end": 16},
]

SESSION_BEHAVIOR = {
    "Asia":      "低波動，建立 Range。Asia H/L 是 London 掃單目標，不建議進場",
    "London":    "最高波動，掃 Asia H/L 後建立當日方向。London KZ (02-05 UTC) 最佳入場窗口",
    "NY":        "確認或反轉 London 方向。NY KZ (13-16 UTC) 次佳入場窗口",
    "Off-Hours": "低流動性，避免進場",
}


def get_session_context(now_utc: datetime | None = None) -> dict:
    """Return current session name, Kill Zone status, and behavior note."""
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    h = now_utc.hour

    if 0 <= h < 8:
        session = "Asia"
    elif 7 <= h < 13:
        session = "London"
    elif 13 <= h < 21:
        session = "NY"
    else:
        session = "Off-Hours"

    kz = next((z["name"] for z in KILL_ZONES if z["start"] <= h < z["end"]), None)

    return {
        "session":        session,
        "hour_utc":       h,
        "in_kill_zone":   kz is not None,
        "kill_zone":      kz,
        "behavior_note":  SESSION_BEHAVIOR[session],
    }


def get_asia_sweep_signal(price: float, session: str,
                           asia_high: float | None,
                           asia_low:  float | None) -> dict | None:
    """
    During London / NY: detect whether Asia H or L has been swept
    and price has closed back inside the range (Manipulation signal).

    Swept High + back inside → bearish setup.
    Swept Low  + back inside → bullish setup.
    """
    if session not in ("London", "NY") or not asia_high or not asia_low:
        return None

    swept_h = price > asia_high * 1.001
    swept_l = price < asia_low  * 0.999

    if swept_h and price < asia_high:
        return {
            "sweep":       "Asia High",
            "implication": "bearish",
            "note":        f"掃 Asia High ({round(asia_high,2)}) 後收回 → 留意空方機會",
        }
    if swept_l and price > asia_low:
        return {
            "sweep":       "Asia Low",
            "implication": "bullish",
            "note":        f"掃 Asia Low ({round(asia_low,2)}) 後收回 → 留意多方機會",
        }
    return None
