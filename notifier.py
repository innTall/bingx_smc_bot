# notifier.py
import aiohttp
import logging
from typing import List, Dict, Any

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

def format_fractal_raid_message(reports: List[Dict[str, Any]], tf: str) -> str:
    """
    Формирует лаконичный отчет по Fractal_H / Fractal_L и Raid для выбранного TF.
    """
    lines = [f"<b>Fractal Raid Report | TF: {tf}</b>\n"]
    
    for rep in reports:
        symbol = rep.get("symbol", "")
        # Очищаем символ от /USDT или USDT (остается чистый тикер, например BTC)
        clean_symbol = symbol.split('/')[0].replace('USDT', '')
        
        fh = rep.get("working_fh")
        fl = rep.get("working_fl")
        
        lines.append(f"<b>{clean_symbol}</b>")
        
        # Fractal_H (зеленый эмодзи)
        if fh:
            fh_dist = fh.get('candles_ago', 0)
            raid_candles = fh.get('raid_candles_ago')
            raid_str = f" | Raid ({raid_candles})" if raid_candles is not None else ""
            lines.append(f"  🟢 Fractal_H: <b>{fh.get('price')}</b> ({fh_dist}){raid_str}")
        else:
            lines.append("  🟢 Fractal_H: нет")
            
        # Fractal_L (красный эмодзи)
        if fl:
            fl_dist = fl.get('candles_ago', 0)
            raid_candles = fl.get('raid_candles_ago')
            raid_str = f" | Raid ({raid_candles})" if raid_candles is not None else ""
            lines.append(f"  🔴 Fractal_L: <b>{fl.get('price')}</b> ({fl_dist}){raid_str}")
        else:
            lines.append("  🔴 Fractal_L: нет")
            
        lines.append("") # пустая строка между символами
        
    return "\n".join(lines)