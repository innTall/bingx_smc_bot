# notifier.py
import aiohttp
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

async def send_telegram_message(session: aiohttp.ClientSession, token: str, chat_id: str, text: str) -> bool:
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


def format_fractal_raid_message(symbol_data_map: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """
    Форматирует Fractal Raid Report:
    - Группировка по символам.
    - Для каждого таймфрейма (TF) ищем самый свежий Raid (минимальный raid_candles_ago) 
      среди FH и FL, и выводим его в виде отдельной строки.
    """
    lines = ["<b>Fractal Raid Report</b>\n"]
    has_any_content = False
    timeframes = ['1h', '4h', '1d']  # Или в том порядке, в котором вам привычнее

    for symbol in sorted(symbol_data_map.keys()):
        clean_symbol = symbol.split('/')[0].replace('USDT', '')
        tf_map = symbol_data_map[symbol]

        symbol_lines = []

        for tf in timeframes:
            tf_data = tf_map.get(tf)
            if not tf_data:
                continue
            
            snr_data = tf_data.get('snr')
            if not snr_data:
                continue

            fh = snr_data.get('working_fh')
            fl = snr_data.get('working_fl')

            candidates = []
            
            # Проверяем FH на наличие Raid
            if fh and fh.get('raid_candles_ago') is not None:
                candidates.append({
                    'type': 'Fractal_H',
                    'emoji': '🔴',
                    'price': fh.get('price'),
                    'candles_ago': fh.get('candles_ago', 0),
                    'raid_candles': fh.get('raid_candles_ago')
                })
                
            # Проверяем FL на наличие Raid
            if fl and fl.get('raid_candles_ago') is not None:
                candidates.append({
                    'type': 'Fractal_L',
                    'emoji': '🟢',
                    'price': fl.get('price'),
                    'candles_ago': fl.get('candles_ago', 0),
                    'raid_candles': fl.get('raid_candles_ago')
                })

            if not candidates:
                continue

            # Выбираем кандидат с МЕНЬШИМ значением raid_candles (самый свежий Raid)
            best_raid = min(candidates, key=lambda x: x['raid_candles'])

            # Формируем строчку для данного таймфрейма
            symbol_lines.append(
                f"  {best_raid['emoji']} <b>{tf.upper()}</b> | {best_raid['type']}: "
                f"<b>{best_raid['price']}</b> ({best_raid['candles_ago']}) | Raid ({best_raid['raid_candles']})"
            )

        if symbol_lines:
            has_any_content = True
            lines.append(f"<b>{clean_symbol}</b>")
            lines.extend(symbol_lines)
            lines.append("")  # пустая строка между символами

    if not has_any_content:
        return "<b>Fractal Raid Report</b>\n\nℹ️ Активных Raid не найдено."

    return "\n".join(lines)

def format_kl_snr_message(symbol_data_map: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """
    Форматирует KL SNR Report:
    - Группировка по символам.
    - Для каждого таймфрейма (1h, 4h, 1d) определяется самый последний Raid (минимальный raid_candles_ago) 
      между FH и FL.
    - Если у этого последнего Raid нет KL SNR, выводится прочерк (-), без подтягивания старых данных.
    - Полностью на английском языке, компактный формат.
    """
    lines = ["<b>KL SNR Report</b>\n"]
    has_content = False
    timeframes = ['1h', '4h', '1d']

    for symbol in sorted(symbol_data_map.keys()):
        clean_symbol = symbol.split('/')[0].replace('USDT', '')
        tf_map = symbol_data_map[symbol]
        
        symbol_lines = []
        for tf in timeframes:
            tf_data = tf_map.get(tf)
            if not tf_data:
                continue
            
            snr_data = tf_data.get('snr')
            if not snr_data:
                continue

            fh = snr_data.get('working_fh')
            fl = snr_data.get('working_fl')

            raid_candidates = []

            # Собираем данные по пробитым фракталам для текущего таймфрейма
            if fh and fh.get('raid_candles_ago') is not None:
                raid_candidates.append({
                    'type': 'FH',
                    'emoji': '🔴',
                    'item': fh,
                    'raid_candles': fh.get('raid_candles_ago')
                })

            if fl and fl.get('raid_candles_ago') is not None:
                raid_candidates.append({
                    'type': 'FL',
                    'emoji': '🟢',
                    'item': fl,
                    'raid_candles': fl.get('raid_candles_ago')
                })

            if not raid_candidates:
                continue

            # Строго выбираем САМЫЙ ПОСЛЕДНИЙ Raid (с минимальным raid_candles_ago)
            latest_raid = min(raid_candidates, key=lambda x: x['raid_candles'])
            
            item = latest_raid['item']
            kl = item.get('kl_snr')
            emoji = latest_raid['emoji']
            l_type = latest_raid['type']

            if kl:
                symbol_lines.append(
                    f"  {emoji} <b>{tf.upper()}</b> | {l_type} SNR: "
                    f"<b>{kl['level_price']}</b> ({kl['candles_ago_left']})"
                )
            else:
                # Если у самого свежего рейда нет KL SNR — ставим прочерк, никаких старых данных
                symbol_lines.append(
                    f"  {emoji} <b>{tf.upper()}</b> | {l_type} SNR: -"
                )

        if symbol_lines:
            has_content = True
            lines.append(f"<b>{clean_symbol}</b>")
            lines.extend(symbol_lines)
            lines.append("")

    if not has_content:
        return "<b>KL SNR Report</b>\n\nℹ️ No active KL SNR found."

    return "\n".join(lines)

def format_trading_levels_message(symbol_data_map: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """
    Форматирует отчет Trading Levels:
    - Группировка по символам.
    - Для каждого таймфрейма выводит актуальные сформированные SNR (и Long, и Short), 
      попавшие в окно last_candles_snr.
    """
    lines = ["<b>Trading Levels Report</b>\n"]
    has_content = False
    timeframes = ['1h', '4h', '1d']

    for symbol in sorted(symbol_data_map.keys()):
        clean_symbol = symbol.split('/')[0].replace('USDT', '')
        tf_map = symbol_data_map[symbol]
        
        symbol_lines = []
        for tf in timeframes:
            tf_data = tf_map.get(tf)
            if not tf_data:
                continue
            
            snr_data = tf_data.get('snr')
            if not snr_data:
                continue

            fh = snr_data.get('working_fh')  # Здесь теперь хранится лучший Short в окне
            fl = snr_data.get('working_fl')  # Здесь теперь хранится лучший Long в окне

            tf_signals = []

            # Добавляем Short (FH), если он есть в пределах окна
            if fh:
                tf_signals.append(
                    f"  🔴 <b>{tf.lower()}</b>_FH"
                    f"=> <b>{fh['entry']}</b>_SL <b>{fh['stop_loss']}</b> ({fh['sl_percent']}%)"
                )

            # Добавляем Long (FL), если он есть в пределах окна
            if fl:
                tf_signals.append(
                    f"  🟢 <b>{tf.lower()}</b>_FL"
                    f"=> <b>{fl['entry']}</b>_SL <b>{fl['stop_loss']}</b> ({fl['sl_percent']}%)"
                )

            if tf_signals:
                symbol_lines.extend(tf_signals)

        if symbol_lines:
            has_content = True
            lines.append(f"<b>{clean_symbol}</b>")
            lines.extend(symbol_lines)
            lines.append("")

    if not has_content:
        return None

    return "\n".join(lines)