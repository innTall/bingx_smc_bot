# notifier.py
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def send_telegram_message(session: aiohttp.ClientSession, token: str, chat_id: str, text: str) -> bool:
    """
    Асинхронная отправка текстового сообщения в Telegram.
    """
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("[WARNING] Telegram token is not set in settings.json!")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    # Исправлено: передаем корректный объект ClientTimeout вместо простого числа
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with session.post(url, json=payload, timeout=timeout) as response:
            data = await response.json()
            if data.get("ok"):
                print("[INFO] Telegram message sent successfully.")
                return True
            else:
                print(f"[ERROR] Failed to send Telegram message: {data.get('description')}")
                return False
    except Exception as e:
        print(f"[ERROR] Network error while sending Telegram message: {e}")
        return False