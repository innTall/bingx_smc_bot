import json
import os
import ccxt
import pandas as pd
from datetime import timedelta
from dotenv import load_dotenv
from notifier import send_telegram_message

# Загружаем переменные из файла .env
load_dotenv()

def load_settings():
    """Load general settings from settings.json and secrets from .env"""
    settings_path = 'settings.json'
    config = {
        "symbol": "BTC/USDT:USDT",
        "timeframe": "1h",
        "limit": 100,
        "timezone_offset_hours": 3
    }
    
    # Читаем общие настройки из settings.json, если он есть
    if os.path.exists(settings_path):
        with open(settings_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
            config.update(file_data)
            
    # Загружаем секретные токены исключительно из .env
    config["telegram_token"] = os.getenv("TELEGRAM_TOKEN", "")
    config["telegram_chat_id"] = os.getenv("TELEGRAM_CHAT_ID", "")
    
    return config

def fetch_bingx_ohlcv(symbol, timeframe, limit):
    exchange = ccxt.bingx({'enableRateLimit': True})
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        return df
    except Exception as e:
        print(f"Ошибка при загрузке данных с BingX для {symbol} ({timeframe}): {e}")
        return None

def analyze_fractals_v3(df, tz_offset):
    """
    1. Поиск фракталов с точным определением средней свечи (без ложных EQH на краях).
    2. Проверка луча вправо -> Active.
    3. При пробое проверяется каскад: если пробито несколько активных уровней за раз,
       то Working становится самый дальний слева (самый старый из пробитых в этом импульсе).
    """
    fractals = []
    
    if df is None or len(df) < 3:
        return fractals

    # Шаг 1. Поиск базовых фракталов (средняя свеча - четкий пик)
    for i in range(1, len(df) - 1):
        prev_high = df.loc[i - 1, 'high']
        curr_high = df.loc[i, 'high']
        next_high = df.loc[i + 1, 'high']
        
        prev_low = df.loc[i - 1, 'low']
        curr_low = df.loc[i, 'low']
        next_low = df.loc[i + 1, 'low']
        
        center_timestamp_ms = df.loc[i, 'timestamp']
        dt_local = pd.to_datetime(center_timestamp_ms, unit='ms') + timedelta(hours=tz_offset)
        
        # Условие FH: средняя строго выше левой, и >= правой (исключаем смещение пика влево)
        if curr_high > prev_high and curr_high >= next_high:
            fractals.append({
                'type': 'FH',
                'index': i,
                'datetime': dt_local,
                'price': curr_high
            })
            
        # Условие FL: средняя строго ниже левой, и <= правой
        if curr_low < prev_low and curr_low <= next_low:
            fractals.append({
                'type': 'FL',
                'index': i,
                'datetime': dt_local,
                'price': curr_low
            })

    active_fractals = []
    broken_fh = []
    broken_fl = []

    # Шаг 2. Проверяем луч вправо для каждого фрактала
    for f in fractals:
        i = f['index']
        price = f['price']
        is_broken = False
        broken_at_index = None

        for j in range(i + 2, len(df)):
            if f['type'] == 'FH':
                if df.loc[j, 'high'] > price:
                    is_broken = True
                    broken_at_index = j
                    break
            elif f['type'] == 'FL':
                if df.loc[j, 'low'] < price:
                    is_broken = True
                    broken_at_index = j
                    break

        if not is_broken:
            f['status'] = 'Active'
            active_fractals.append(f)
        else:
            f['broken_at'] = broken_at_index
            if f['type'] == 'FH':
                broken_fh.append(f)
            else:
                broken_fl.append(f)

    # Шаг 3. Обработка каскада для поиска Working фракталов
    working_fractals = []

    def process_cascade(broken_list, f_type):
        if not broken_list:
            return
        # Находим самый свежий пробой (по индексу свечи, которая совершила пробой)
        latest_break_idx = max(item['broken_at'] for item in broken_list)
        
        # Собираем все уровни этого же типа, которые были пробиты в этот же момент (каскад) 
        # или затронуты последним сильным импульсом
        cascade_items = [item for item in broken_list if item['broken_at'] == latest_break_idx]
        
        # Если каскад затронул несколько уровней, Рабочим становится самый старый (минимальный индекс i)
        oldest_in_cascade = min(cascade_items, key=lambda x: x['index'])
        oldest_in_cascade['status'] = 'Working'
        working_fractals.append(oldest_in_cascade)

    process_cascade(broken_fh, 'FH')
    process_cascade(broken_fl, 'FL')

    # Итоговый список: только Active и Working
    result = active_fractals + working_fractals
    result = sorted(result, key=lambda x: x['index'])
    return result

def format_telegram_report(symbol, timeframe, fractals):
    """
    Formats only Working (broken) fractals into a compact Telegram message 
    according to the new requirements.
    """
    # Очищаем символ от хвоста биржи (например, 'BTC/USDT:USDT' превращаем в 'BTC')
    clean_symbol = symbol.split('/')[0]
    
    # Отфильтровываем только Working уровни
    working_fractals = [f for f in fractals if f['status'] == 'Working']
    
    if not working_fractals:
        return None  # Если нет рабочих уровней, сообщение не шлем
        
    message = f"<b>{clean_symbol}</b>\n"
    
    for f in working_fractals:
        # Индикация: FL (Buy setup) - 🟢, FH (Sell setup) - 🔴
        emoji = "🟢" if f['type'] == 'FL' else "🔴"
        time_str = f['datetime'].strftime('%Y-%m-%d %H:%M')
        
        # Формат: Эмодзи Тип [ТФ] Цена: ... | Время: ...
        message += f"{emoji} <b>{f['type']}</b> [{timeframe}] | Price: <code>{f['price']}</code> | Time: {time_str}\n"
        
    return message

if __name__ == "__main__":
    config = load_settings()
    print(f"[INFO] Analyzing fractals for {config['symbol']} ({config['timeframe']})...")
    
    df_candles = fetch_bingx_ohlcv(
        symbol=config['symbol'], 
        timeframe=config['timeframe'], 
        limit=config['limit']
    )
    
    if df_candles is not None:
        report_fractals = analyze_fractals_v3(df_candles, config['timezone_offset_hours'])
        print(f"[INFO] Found relevant levels (Active + Working): {len(report_fractals)}")
        
        # Формируем текст отчета и отправляем в Telegram, если есть Working уровни
        msg_text = format_telegram_report(config['symbol'], config['timeframe'], report_fractals)
        
        if msg_text:
            send_telegram_message(
                token=config['telegram_token'],
                chat_id=config['telegram_chat_id'],
                text=msg_text
            )
        else:
            print("[INFO] No Working fractals found, Telegram message skipped.")