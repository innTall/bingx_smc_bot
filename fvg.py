# fvg.py
import pandas as pd

def detect_bullish_fvg_and_raids(df: pd.DataFrame, symbol: str, tf: str, fvg_history_limit: int = 25):
    """
    Финальная версия для Bullish FVG:
    - Поиск FVG в oldest-first массиве.
    - Поиск пробоев (IMB / FF) с исключением свечей формирования.
    - Выбор ровно ОДНОГО самого свежего (последнего по времени) Raid для символа и TF.
    """
    fvgs = []
    n = len(df)
    if n < 4:
        return []

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()

    # 1. Поиск всех Bullish FVG
    start_index = max(0, n - 3 - fvg_history_limit)
    for i in range(start_index, n - 2):
        # Защита: C3 не должна быть текущей (самой последней) незакрытой свечой
        if (i + 2) >= n - 1:
            continue

        is_up = closes[i + 1] > opens[i + 1]
        is_gap = highs[i] < lows[i + 2]  # Бычий гэп
        
        if is_up and is_gap:
            fvg_item = {
                "type": "BULLISH_FVG",
                "c1_idx": i,
                "c2_idx": i + 1,
                "c3_idx": i + 2,
                "imb_level": lows[i + 2],   # KL IMB
                "ff_level": highs[i]         # KL FF
            }
            fvgs.append(fvg_item)

    if not fvgs:
        return []

    # 2. Поиск пробоев и выбор САМОГО СВЕЖЕГО (последнего) Raid
    latest_bullish_raid = None

    for fvg in fvgs:
        c3_idx = fvg['c3_idx']
        imb_level = fvg['imb_level']
        ff_level = fvg['ff_level']

        imb_break_idx = None
        ff_break_idx = None

        # Диапазон поиска Raid: строго после C3 в сторону текущей цены (от c3_idx + 1 до конца n-1)
        start_search = c3_idx + 1
        end_search = n - 1

        for idx in range(start_search, end_search):
            # Строгий пробой (касания игнорируем)
            if imb_break_idx is None and lows[idx] < imb_level:
                imb_break_idx = idx
            if ff_break_idx is None and lows[idx] < ff_level:
                ff_break_idx = idx

        # Приоритет у FF как у более глубокого уровня, либо фиксируем IMB
        target_subtype = None
        target_level = None
        target_break_idx = None

        if ff_break_idx is not None:
            target_subtype = 'FF_bull'
            target_level = ff_level
            target_break_idx = ff_break_idx
        elif imb_break_idx is not None:
            target_subtype = 'IMB_bull'
            target_level = imb_level
            target_break_idx = imb_break_idx

        # Если для этого FVG зафиксирован пробой, проверяем, является ли он самым свежим (наибольший break_idx)
        if target_break_idx is not None:
            raid_candidate = {
                'symbol': symbol,
                'tf': tf,
                'type': 'BULLISH_FVG',
                'subtype': target_subtype,
                'level': target_level,
                'break_idx': target_break_idx,
                'c3_idx': c3_idx
            }
            
            # Выбираем тот пробой, который ближе к настоящему (максимальный break_idx)
            if latest_bullish_raid is None or raid_candidate['break_idx'] > latest_bullish_raid['break_idx']:
                latest_bullish_raid = raid_candidate

    actual_raids = []
    if latest_bullish_raid:
        actual_raids.append(latest_bullish_raid)

    return actual_raids