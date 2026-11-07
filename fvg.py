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

    # 1. Поиск всех Bullish FVG
    start_index = max(0, n - 3 - fvg_history_limit)
    for i in range(start_index, n - 2):
        c1 = df.iloc[i]       # C1 (самая старая)
        c2 = df.iloc[i + 1]   # C2 (импульсная)
        c3 = df.iloc[i + 2]   # C3 (момент завершения FVG)
        
        # Защита: C3 не должна быть текущей (самой последней) незакрытой свечой
        if (i + 2) >= n - 1:
            continue

        is_up = c2['close'] > c2['open']
        is_gap = c1['high'] < c3['low']  # Бычий гэп
        
        if is_up and is_gap:
            fvg_item = {
                "type": "BULLISH_FVG",
                "c1_idx": i,
                "c2_idx": i + 1,
                "c3_idx": i + 2,
                "imb_level": c3['low'],   # KL IMB
                "ff_level": c1['high']    # KL FF
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
        end_search = n

        for idx in range(start_search, end_search):
            candle = df.iloc[idx]
            
            # Строгий пробой (касания игнорируем)
            if imb_break_idx is None and candle['low'] < imb_level:
                imb_break_idx = idx
            if ff_break_idx is None and candle['low'] < ff_level:
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

    # 3. Финальный вывод в консоль для Bullish
    # Очищаем символ для красивого вывода (например, 'BTC/USDT' -> 'BTC')
    clean_symbol = symbol.split('/')[0] if '/' in symbol else symbol.replace('USDT', '')
    actual_raids = []
    if latest_bullish_raid:
        actual_raids.append(latest_bullish_raid)
        r = latest_bullish_raid
        print(f"🟢 {clean_symbol} {r['tf']} -> {r['subtype']} {r['level']} (Break: {r['break_idx']})")

    return actual_raids