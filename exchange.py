# exchange.py
import asyncio
import aiohttp
import pandas as pd

APIURL = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"

def _normalize_symbol(symbol: str) -> str:
    clean = symbol.replace("/", "").upper()
    if not clean.endswith("-USDT"):
        if clean.endswith("USDT"):
            clean = clean[:-4] + "-USDT"
    return clean

async def fetch_bingx_ohlcv_async(
    session: aiohttp.ClientSession, 
    symbol: str, 
    timeframe: str, 
    limit: int = 100,
    max_retries: int = 3,
    retry_delay: float = 1.0
):
    formatted_symbol = _normalize_symbol(symbol)
    
    params = {
        "symbol": formatted_symbol,
        "interval": timeframe,
        "limit": limit
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    timeout = aiohttp.ClientTimeout(total=10)
    delay = retry_delay
    
    for attempt in range(1, max_retries + 1):
        try:
            async with session.get(APIURL, params=params, headers=headers, timeout=timeout) as response:
                if response.status != 200:
                    # Серверные ошибки (5xx) стоит попробовать повторить
                    if response.status >= 500 and attempt < max_retries:
                        print(f"[WARNING] HTTP status {response.status} for {symbol} ({timeframe}). Попытка {attempt}/{max_retries}. Повтор через {delay}с...")
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                        
                    print(f"[ERROR] HTTP status {response.status} for {symbol} ({timeframe})")
                    return None
                    
                data = await response.json()
                
                if data.get("code") != 0:
                    msg = data.get('msg', '')
                    # Проверяем временные ошибки биржи, включая '请稍后重试'
                    if ("请稍后重试" in msg or "system error" in msg.lower() or "busy" in msg.lower()) and attempt < max_retries:
                        print(f"[WARNING] BingX temporary error for {symbol} ({timeframe}): {msg}. Попытка {attempt}/{max_retries}. Повтор через {delay}с...")
                        await asyncio.sleep(delay)
                        delay *= 2
                        continue
                        
                    print(f"[ERROR] BingX API error for {symbol} ({timeframe}): {msg}")
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
                
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < max_retries:
                print(f"[WARNING] Network/Timeout error for {symbol} ({timeframe}): {e}. Попытка {attempt}/{max_retries}. Повтор через {delay}с...")
                await asyncio.sleep(delay)
                delay *= 2
                continue
            print(f"[ERROR] Async request failed for {symbol} ({timeframe}) after {max_retries} attempts: {e}")
            return None
            
        except Exception as e:
            print(f"[ERROR] Unexpected error for {symbol} ({timeframe}): {e}")
            return None
            
    return None