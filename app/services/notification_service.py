import httpx

async def send_telegram(token: str, chat_id: str, message: str) -> bool:
    if not token or not chat_id:
        print("[Notify] Telegram token 或 chat_id 未設定，跳過通知")
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
            ok = res.status_code == 200
            if not ok:
                print(f"[Notify] Telegram 回應 {res.status_code}: {res.text}")
            return ok
    except Exception as e:
        print(f"[Notify] 發送失敗: {e}")
        return False
