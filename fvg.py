# fvg.py
import pandas as pd

def detect_bullish_fvg_and_raids(df: pd.DataFrame, symbol: str, tf: str, fvg_history_limit: int = 25):
    """
    Поиск Bullish FVG и их пробоев (Raid) для oldest-first массивов.
    C1 (i) -> C2 (i+1) -> C3 (i+2).
    Диапазон поиска Raid: от C3 до конца массива (справа налево по времени, т.е. от c3_idx + 1 до n-1).
    """
    fvgs = []
    n = len(df)
    if n < 4:
        return fvgs

    # 1. Поиск Bullish FVG (идем от начала до n - 3, чтобы C3 не вылетел за границы)
    for i in range(n - 2):
        c1 = df.iloc[i]       # C1 (самая старая)
        c2 = df.iloc[i + 1]   # C2 (импульсная)
        c3 = df.iloc[i + 2]   # C3 (момент завершения FVG)
        
        # Защита: C3 не должна быть текущей (самой последней) незакрытой свечой
        if (i + 2) >= n - 1:
            continue

        is_up = c2['close'] > c2['open']
        is_gap = c1['high'] < c3['low']  # Бычий гэп
        
        if is_up and is_gap:
            imb_level = c3['low']   # KL IMB
            ff_level = c1['high']   # KL FF
            
            fvg_item = {
                "type": "BULLISH_FVG",
                "c1_idx": i,
                "c2_idx": i + 1,
                "c3_idx": i + 2,
                "imb_level": imb_level,
                "ff_level": ff_level
            }
            fvgs.append(fvg_item)
            print(f"[{symbol} {tf}] Bullish FVG found -> C3 idx: {i + 2} | IMB: {imb_level} | FF: {ff_level}")

    # 2. Поиск Raid для каждого найденного Bullish FVG
    for fvg in fvgs:
        c3_idx = fvg['c3_idx']
        imb_level = fvg['imb_level']
        ff_level = fvg['ff_level']

        imb_broken = False
        ff_broken = False
        imb_break_idx = None
        ff_break_idx = None

        # Ищем пробой двигаясь вправо (в сторону актуального времени: от c3_idx + 1 до конца n-1)
        start_search = c3_idx + 1
        end_search = n  # не включая n (или ограничено fvg_history_limit)

        for idx in range(start_search, end_search):
            candle = df.iloc[idx]
            
            # Строгий пробой (касания игнорируем)
            if not imb_broken and candle['low'] < imb_level:
                imb_broken = True
                imb_break_idx = idx
            if not ff_broken and candle['low'] < ff_level:
                ff_broken = True
                ff_break_idx = idx

        # Вывод результатов Raid в терминал
        if imb_broken:
            print(f"  [RAID] {symbol} {tf} Bullish IMB broken at {imb_level} (break_idx: {imb_break_idx}, C3 idx: {c3_idx})")
        if ff_broken:
            print(f"  [RAID] {symbol} {tf} Bullish FF broken at {ff_level} (break_idx: {ff_break_idx}, C3 idx: {c3_idx})")

    return fvgs