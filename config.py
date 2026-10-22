import json
import os
from dotenv import load_dotenv

load_dotenv()

def load_settings():
    settings_path = 'settings.json'
    config = {
        "symbol": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
        "timeframe": ["1h", "4h", "1d"],
        "limit": 100,
        "timezone_offset_hours": 3
    }
    
    if os.path.exists(settings_path):
        with open(settings_path, 'r', encoding='utf-8') as f:
            file_data = json.load(f)
            config.update(file_data)

    raw_symbols = config.get('symbols', config.get('symbol', ['BTC/USDT']))
    if isinstance(raw_symbols, str):
        raw_symbols = [raw_symbols]
        
    formatted_symbols = []
    for s in raw_symbols:
        if '/' not in s:
            if s.endswith('USDT'):
                formatted_symbols.append(f"{s[:-4]}/USDT")
            else:
                formatted_symbols.append(s)
        else:
            formatted_symbols.append(s)

    config['symbols'] = formatted_symbols

    raw_tfs = config.get('timeframes', config.get('timeframe', ['1h']))
    if isinstance(raw_tfs, str):
        raw_tfs = [raw_tfs]
    config['timeframes'] = raw_tfs

    config["telegram_token"] = os.getenv("TELEGRAM_TOKEN", "")
    config["telegram_chat_id"] = os.getenv("TELEGRAM_CHAT_ID", "")
    
    return config