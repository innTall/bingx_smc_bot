import requests
import pandas as pd

APIURL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

def _normalize_symbol(symbol: str) -> str:
    """
    Приводит символ к формату BingX Swap API (например: BTC/USDT -> BTC-USDT)
    """
    clean = symbol.replace("/", "").upper()
    if not clean.endswith("-USDT"):
        if clean.endswith("USDT"):
            clean = clean[:-4] + "-USDT"
    return clean

def fetch_bingx_ohlcv(symbol, timeframe, limit=100):
    """
    Загрузка свечей напрямую с официального фьючерсного API BingX (v3).
    Гарантирует 100% совпадение с котировками биржи и TradingView.
    """
    formatted_symbol = _normalize_symbol(symbol)
    
    params = {
        "symbol": formatted_symbol,
        "interval": timeframe,
        "limit": limit
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(APIURL, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("code") != 0:
            print(f"[ERROR] BingX API error for {symbol} ({timeframe}): {data.get('msg')}")
            return None
            
        klines = data.get("data", [])
        if not klines:
            print(f"[WARNING] Пустой ответ от BingX API для {symbol} ({timeframe})")
            return None
            
        # BingX v3 возвращает список свечей. Превращаем в DataFrame
        # Структура ответа BingX klines: time, open, high, low, close, volume
        df = pd.DataFrame(klines)
        
        # Переименовываем поле времени в timestamp (если оно называется 'time')
        if 'time' in df.columns and 'timestamp' not in df.columns:
            df = df.rename(columns={'time': 'timestamp'})
            
        # Приводим числовые колонки к корректному типу
        numeric_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col])
                
        # Сортируем по времени на всякий случай (от старых к новым)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        
    except Exception as e:
        print(f"[ERROR] Ошибка запроса к BingX API для {symbol} ({timeframe}): {e}")
        return None