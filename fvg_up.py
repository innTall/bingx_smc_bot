# fvg_up.py
import aiohttp
import asyncio
import pandas as pd

async def fetch_aave_candles(limit: int = 20) -> pd.DataFrame:
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
    params = {"symbol": "AAVE-USDT", "interval": "1h", "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()
            if data.get("code") == 0 and "data" in data:
                df = pd.DataFrame(data["data"]).iloc[:, :6]
                df.columns = ["time", "open", "high", "low", "close", "volume"]
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(float)
                return df
            return pd.DataFrame()

def detect_bullish_fvg(df: pd.DataFrame) -> list:
    fvgs = []
    for i in range(len(df) - 2):
        c1 = df.iloc[i]       # C1: правая базовая
        c2 = df.iloc[i + 1]   # C2: средняя импульсная
        c3 = df.iloc[i + 2]   # C3: левая
        
        is_up_candle = c2['close'] > c2['open']
        
        # Условие Bullish FVG: High C3 < Low C1
        if is_up_candle and c3['high'] < c1['low']:
            fvgs.append({
                "type": "BULLISH_FVG",
                "kl_imb": c1['low'],   # Low C1
                "kl_ff": c3['high'],   # High C3
                "index_c1": i
            })
    return fvgs

async def main():
    df = await fetch_aave_candles(20)
    fvgs = detect_bullish_fvg(df)
    print(f"\n--- BULLISH FVG REPORT (AAVE 1h, найдено: {len(fvgs)}) ---")
    for idx, fvg in enumerate(fvgs, 1):
        print(f"[{idx}] KL IMB: {fvg['kl_imb']} | KL FF: {fvg['kl_ff']}")

if __name__ == "__main__":
    asyncio.run(main())