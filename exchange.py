import aiohttp
import pandas as pd

APIURL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

def _normalize_symbol(symbol: str) -> str:
    clean = symbol.replace("/", "").upper()
    if not clean.endswith("-USDT"):
        if clean.endswith("USDT"):
            clean = clean[:-4] + "-USDT"
    return clean

async def fetch_bingx_ohlcv_async(session: aiohttp.ClientSession, symbol: str, timeframe: str, limit: int = 100):
    formatted_symbol = _normalize_symbol(symbol)
    
    params = {
        "symbol": formatted_symbol,
        "interval": timeframe,
        "limit": limit
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    # Создаем объект тайм-аута по правилам aiohttp
    timeout = aiohttp.ClientTimeout(total=10)
    
    try:
        async with session.get(APIURL, params=params, headers=headers, timeout=timeout) as response:
            if response.status != 200:
                print(f"[ERROR] HTTP status {response.status} for {symbol} ({timeframe})")
                return None
                
            data = await response.json()
            
            if data.get("code") != 0:
                print(f"[ERROR] BingX API error for {symbol} ({timeframe}): {data.get('msg')}")
                return None
                
            klines = data.get("data", [])
            if not klines:
                return None
                
            df = pd.DataFrame(klines)
            
            if 'time' in df.columns and 'timestamp' not in df.columns:
                df = df.rename(columns={'time': 'timestamp'})
                
            numeric_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col])
                    
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
            
    except Exception as e:
        print(f"[ERROR] Async request failed for {symbol} ({timeframe}): {e}")
        return None