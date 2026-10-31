# fvg_2.py
import aiohttp
import asyncio
import pandas as pd

def detect_bullish_fvg(df: pd.DataFrame) -> list:
    """Проверенная логика поиска Bullish FVG"""
    fvgs = []
    n = len(df)
    for i in range(n - 2):
        c1 = df.iloc[i]       # правая
        c2 = df.iloc[i + 1]   # средняя импульсная
        c3 = df.iloc[i + 2]   # левая
        
        is_up = c2['close'] > c2['open']
        is_gap = c3['high'] < c1['low']
        
        if is_up and is_gap:
            fvgs.append({
                "type": "BULLISH_FVG",
                "kl_imb": c1['low'],
                "kl_ff": c3['high'],
                "index_c2": i + 1
            })
    return fvgs

def detect_bearish_fvg(df: pd.DataFrame) -> list:
    """Проверенная логика поиска Bearish FVG"""
    fvgs = []
    n = len(df)
    for i in range(n - 2):
        c1 = df.iloc[i]       # правая
        c2 = df.iloc[i + 1]   # средняя импульсная
        c3 = df.iloc[i + 2]   # левая
        
        is_down = c2['close'] < c2['open']
        is_gap = c1['high'] < c3['low']
        
        # Отладочный вывод для каждого среза
        #print(f"[Bearish Check] i={i} | C2 Down={is_down} (O:{c2['open']}, C:{c2['close']}) | C1.High({c1['high']}) < C3.Low({c3['low']}) => {is_gap}")
        
        if is_down and is_gap:
            fvgs.append({
                "type": "BEARISH_FVG",
                "kl_imb": c1['high'],
                "kl_ff": c3['low'],
                "index_c2": i + 1
            })
        #print(f"[Bearish Check] i={i} | C2 Open={c2['open']}, Close={c2['close']} | Down={c2['close'] < c2['open']}")   
    return fvgs

async def fetch_avax_candles(limit: int = 15) -> pd.DataFrame:
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
    params = {"symbol": "AVAX-USDT", "interval": "1h", "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            if data.get("code") == 0 and "data" in data:
                df = pd.DataFrame(data["data"])[
                    ["time", "open", "high", "low", "close", "volume"]
                ]
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(float)
                return df
            return pd.DataFrame()

async def main():
    df = await fetch_avax_candles(15)
    if df.empty:
        print("[ERROR] Не удалось загрузить свечи.")
        return
        
    print(f"\nBULLISH FVG (AVAX 1h, {len(df)} свечей)")
    bullish_results = detect_bullish_fvg(df)
    #print(f"Найдено Bullish FVG: {len(bullish_results)}")
    for fvg in bullish_results:
        print(f" KL IMB (C1.Low): {fvg['kl_imb']} | KL FF (C3.High): {fvg['kl_ff']} (Index C2: {fvg['index_c2']})")

    print(f"\nBEARISH FVG (AVAX 1h, {len(df)} свечей)")
    bearish_results = detect_bearish_fvg(df)
    #print(f"Найдено Bearish FVG: {len(bearish_results)}")
    for fvg in bearish_results:
        print(f" KL IMB (C1.High): {fvg['kl_imb']} | KL FF (C3.Low): {fvg['kl_ff']} (Index C2: {fvg['index_c2']})")

if __name__ == "__main__":
    asyncio.run(main())