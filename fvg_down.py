# fvg_down.py
import aiohttp
import asyncio
import pandas as pd

async def fetch_btc_candles(limit: int = 15) -> pd.DataFrame:
    url = "https://open-api.bingx.com/openApi/swap/v3/quote/klines"
    params = {"symbol": "BTC-USDT", "interval": "1h", "limit": limit}
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

def detect_bearish_fvg(df: pd.DataFrame) -> list:
    fvgs = []
    for i in range(len(df) - 2):
        c1 = df.iloc[i]       # C1: правая базовая
        c2 = df.iloc[i + 1]   # C2: средняя импульсная
        c3 = df.iloc[i + 2]   # C3: левая
        
        is_down_candle = c2['close'] < c2['open']
        
        # Условие Bearish FVG: Low C3 > High C1
        if is_down_candle and c3['low'] > c1['high']:
            fvgs.append({
                "type": "BEARISH_FVG",
                "kl_imb": c1['high'],  # High C1
                "kl_ff": c3['low'],    # Low C3
                "index_c1": i
            })
    return fvgs

async def main():
    df = await fetch_btc_candles(15)
    fvgs = detect_bearish_fvg(df)
    print(f"\n--- BEARISH FVG REPORT (BTC 1h, найдено: {len(fvgs)}) ---")
    for idx, fvg in enumerate(fvgs, 1):
        print(f"[{idx}] KL IMB: {fvg['kl_imb']} | KL FF: {fvg['kl_ff']}")

if __name__ == "__main__":
    asyncio.run(main())