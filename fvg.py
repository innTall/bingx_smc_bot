# fvg.py
import pandas as pd

def detect_bullish_fvg(df: pd.DataFrame) -> list:
    """Detect bullish FVGs from candles ordered newest-first."""
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
    """Detect bearish FVGs from candles ordered newest-first."""
    fvgs = []
    n = len(df)
    for i in range(n - 2):
        c1 = df.iloc[i]       # правая
        c2 = df.iloc[i + 1]   # средняя импульсная
        c3 = df.iloc[i + 2]   # левая
        
        is_down = c2['close'] < c2['open']
        is_gap = c1['high'] < c3['low']
        
        if is_down and is_gap:
            fvgs.append({
                "type": "BEARISH_FVG",
                "kl_imb": c1['high'],
                "kl_ff": c3['low'],
                "index_c2": i + 1
            })
    return fvgs