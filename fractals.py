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
        "symbol": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "timeframe": ["1h", "4h", "1d"],
        "limit": 100,
        "timezone_offset_hours": 3
    }
    
    # Читаем общие настройки из settings.json, если он есть
    if os.path.exists(settings_path):
        with open(settings_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
            config.update(file_data)

    # Поддерживаем как ключи во множественном числе (symbols/timeframes), так и в единственном (symbol/timeframe)
    raw_symbols = config.get('symbols', config.get('symbol', ['BTC/USDT']))
    if isinstance(raw_symbols, str):
        raw_symbols = [raw_symbols]
        
    formatted_symbols = []
    for s in raw_symbols:
        if '/' not in s:
            if s.endswith('USDT'):
                base = s[:-4]
                formatted_symbols.append(f"{base}/USDT")
            else:
                formatted_symbols.append(s)
        else:
            formatted_symbols.append(s)

    config['symbols'] = formatted_symbols

    # Аналогично для таймфреймов
    raw_tfs = config.get('timeframes', config.get('timeframe', ['1h']))
    if isinstance(raw_tfs, str):
        raw_tfs = [raw_tfs]
    config['timeframes'] = raw_tfs

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

def analyze_fractals_v3(df, tz_offset, symbol="UNKNOWN"):
    """
    1. Поиск фракталов с точным определением средней свечи.
    2. Проверка луча вправо -> Active.
    3. При пробое проверяется каскад -> Working.
    """
    fractals = []
    
    if df is None or len(df) < 3:
        return fractals

    # Шаг 1. Поиск базовых фракталов
    for i in range(1, len(df) - 1):
        prev_high = df.loc[i - 1, 'high']
        curr_high = df.loc[i, 'high']
        next_high = df.loc[i + 1, 'high']
        
        prev_low = df.loc[i - 1, 'low']
        curr_low = df.loc[i, 'low']
        next_low = df.loc[i + 1, 'low']
        
        center_timestamp_ms = df.loc[i, 'timestamp']
        dt_local = pd.to_datetime(center_timestamp_ms, unit='ms') + timedelta(hours=tz_offset)
        
        if curr_high > prev_high and curr_high >= next_high:
            fractals.append({
                'type': 'FH',
                'index': i,
                'datetime': dt_local,
                'price': curr_high
            })
            
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

    # Шаг 2. Проверяем луч вправо
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

    # Шаг 3. Обработка каскада для поиска Working
    working_fractals = []

    def process_cascade(broken_list):
        if not broken_list:
            return
        latest_break_idx = max(item['broken_at'] for item in broken_list)
        cascade_items = [item for item in broken_list if item['broken_at'] == latest_break_idx]
        oldest_in_cascade = min(cascade_items, key=lambda x: x['index'])
        oldest_in_cascade['status'] = 'Working'
        working_fractals.append(oldest_in_cascade)

    process_cascade(broken_fh)
    process_cascade(broken_fl)

    # Классифицируем пробой Working фракталов
    for f in working_fractals:
        b_type, b_idx = check_fractal_raid(df, f, symbol=symbol)
        f['breakout_type'] = b_type
        print(f"[INFO] {symbol} Working {f['type']} at {f['price']} -> Status: {b_type}")

    result = active_fractals + working_fractals
    result = sorted(result, key=lambda x: x['index'])
    return result

def check_fractal_raid(df, fractal, symbol="UNKNOWN"):
    """
    Проверяет, был ли совершен Raid (прокол ключевого уровня) для Working фрактала.
    Условие: цена (high для FH, low для FL) должна пересечь f_price хотя бы на 1 пункт.
    Возвращает: ("Raid", index) если пробит, или ("Unknown", None) если нет.
    """
    f_type = fractal['type']
    f_price = fractal['price']
    f_idx = fractal['index']

    max_search_idx = len(df) - 2
    if f_idx + 1 > max_search_idx:
        return "Unknown", None
        
    # Ищем в хронологическом порядке с момента возможного пробоя
    for j in range(f_idx + 2, max_search_idx + 1):
        if f_type == 'FH':
            # Raid для High: тень свечи пробила FH вверх
            if df.loc[j, 'high'] > f_price:
                return "Raid", j
                
        elif f_type == 'FL':
            # Raid для Low: тень свечи пробила FL вниз
            if df.loc[j, 'low'] < f_price:
                return "Raid", j
                
    return "Unknown", None

def format_multi_tf_report(symbol, tf_data_map):
    """
    Формирует единое сообщение для монеты по всем таймфреймам.
    tf_data_map — словарь вида: {'1d': {'fractals': [...], 'snr': [...], 'fvg': [...]}, '4h': {...}, ...}
    """
    clean_symbol = symbol.split('/')[0]
    
    # Проверяем, есть ли вообще хоть какие-то данные по всем таймфреймам
    has_data = any(
        data.get('fractals') or data.get('snr') or data.get('fvg') 
        for data in tf_data_map.values()
    )
    if not has_data:
        return None

    # Заголовок монеты
    message = f"<b>{clean_symbol}</b>\n"
    
    # ---------------------------------------------------------
    # БЛОК LONG (FL и связанные сущности)
    # ---------------------------------------------------------
    # Собираем FL по таймфреймам (например, из 1d, 4h, 1h)
    fl_parts = []
    for tf in ['1d', '4h', '1h']:
        fractals = tf_data_map.get(tf, {}).get('fractals', [])
        # Фильтруем Working FL с подтвержденным Raid
        working_fl = [f for f in fractals if f['status'] == 'Working' and f['type'] == 'FL' and f.get('breakout_type') == 'Raid']
        for f in working_fl:
            date_str = f['datetime'].strftime('%d%b').lower() # Формат типа 19oct
            fl_parts.append(f"*{tf} {f['price']}/{date_str}")
            
    if fl_parts:
        message += f"FL " + " ".join(fl_parts) + "\n"
        
    # SNR Long (задел на будущее)
    snr_long_parts = []
    for tf in ['1d', '4h', '1h']:
        # логика сбора SNR для Long по таймфреймам
        pass
    # if snr_long_parts: message += f"SNR " + ", ".join(snr_long_parts) + "\n"

    # FVG Long (задел на будущее)
    fvg_long_parts = []
    for tf in ['1d', '4h', '1h']:
        # логика сбора FVG для Long (price/ff_price)
        pass
    # if fvg_long_parts: message += f"FVG " + ", ".join(fvg_long_parts) + "\n"

    # SL Long (задел на будущее)
    
    # ---------------------------------------------------------
    # БЛОК SHORT (FH и связанные сущности)
    # ---------------------------------------------------------
    fh_parts = []
    for tf in ['1d', '4h', '1h']:
        fractals = tf_data_map.get(tf, {}).get('fractals', [])
        working_fh = [f for f in fractals if f['status'] == 'Working' and f['type'] == 'FH' and f.get('breakout_type') == 'Raid']
        for f in working_fh:
            date_str = f['datetime'].strftime('%d%b').lower()
            fh_parts.append(f"*{tf} {f['price']}/{date_str}")
            
    if fh_parts:
        message += f"FH " + " ".join(fh_parts) + "\n"
        
    # SNR Short, FVG Short, SL Short ...
    
    return message

if __name__ == "__main__":
    config = load_settings()
    
    symbols = config.get('symbols', ['BTC/USDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 100)
    
    print(f"[INFO] Analyzing for symbols: {symbols} | Timeframes: {timeframes}")
    
    for formatted_symbol in symbols:
        tf_data_map = {}
        
        # 1. Собираем данные по всем таймфреймам для текущей монеты
        for tf in timeframes:
            df_candles = fetch_bingx_ohlcv(symbol=formatted_symbol, timeframe=tf, limit=limit)
            
            if df_candles is not None and not df_candles.empty:
                report_fractals = analyze_fractals_v3(df_candles, config['timezone_offset_hours'], symbol=formatted_symbol)
                
                # Классифицируем через чистый Raid
                for f in report_fractals:
                    if f['status'] == 'Working':
                        b_type, b_idx = check_fractal_raid(df_candles, f, symbol=formatted_symbol)
                        f['breakout_type'] = b_type
                
                tf_data_map[tf] = {
                    'fractals': report_fractals,
                    'snr': [], # Будет заполнено позже
                    'fvg': []  # Будет заполнено позже
                }
            else:
                tf_data_map[tf] = {'fractals': [], 'snr': [], 'fvg': []}
                
        # 2. Генерируем единое сообщение для монеты
        msg_text = format_multi_tf_report(formatted_symbol, tf_data_map)
        
        if msg_text:
            send_telegram_message(
                token=config['telegram_token'],
                chat_id=config['telegram_chat_id'],
                text=msg_text
            )
            print(f"[INFO] Consolidated Telegram message sent for {formatted_symbol}.")
        else:
            print(f"[INFO] No valid data found for {formatted_symbol}, message skipped.")