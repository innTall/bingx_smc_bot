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

def format_snr_debug_message(reports: List[Dict[str, Any]], tf: str) -> str:
    """
    Формирует простой черновой отчет по Working FH/FL и Raid для проверки логики.
    """
    lines = [f"<b>🔍 SNR Debug Report | TF: {tf}</b>\n"]
    
    for rep in reports:
        symbol = rep.get("symbol")
        fh = rep.get("working_fh")
        fl = rep.get("working_fl")
        
        lines.append(f"<b>🔹 {symbol}</b>")
        
        # Working FH
        if fh:
            fh_dist = fh.get('candles_ago', 0)
            raid_candles = fh.get('raid_candles_ago')
            raid_str = f" | Raid (назад: {raid_candles} св.)" if raid_candles is not None else ""
            
            dist_val = fh.get('fh_fl_to_raid_distance')
            dist_str = f" | Дист. до Raid: {dist_val} св." if dist_val is not None else ""
            
            lines.append(f"  • Working FH: <b>{fh.get('price')}</b> ({fh_dist} св. назад){raid_str}{dist_str}")
        else:
            lines.append("  • Working FH: нет")
            
        # Working FL
        if fl:
            fl_dist = fl.get('candles_ago', 0)
            raid_candles = fl.get('raid_candles_ago')
            raid_str = f" | Raid (назад: {raid_candles} св.)" if raid_candles is not None else ""
            
            dist_val = fl.get('fh_fl_to_raid_distance')
            dist_str = f" | Дист. до Raid: {dist_val} св." if dist_val is not None else ""
            
            lines.append(f"  • Working FL: <b>{fl.get('price')}</b> ({fl_dist} св. назад){raid_str}{dist_str}")
        else:
            lines.append("  • Working FL: нет")
            
        lines.append("") # пустая строка между символами
        
    return "\n".join(lines)