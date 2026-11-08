# fvg.py
from typing import List, Dict, Any
import pandas as pd

def detect_bullish_fvg_and_raids(df: pd.DataFrame, symbol: str, tf: str, limit: int = 25):
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
    start_index = max(0, n - limit)
    for i in range(start_index, n - 2):
        if (i + 2) >= n - 1:
            continue

        is_up = closes[i + 1] > opens[i + 1]
        is_gap = highs[i] < lows[i + 2]
        
        if is_up and is_gap:
            fvg_item = {
                "type": "BULLISH_FVG",
                "c1_idx": i,
                "c2_idx": i + 1,
                "c3_idx": i + 2,
                "imb_level": lows[i + 2],
                "ff_level": highs[i]
            }
            fvgs.append(fvg_item)

    if not fvgs:
        return []

    latest_bullish_raid = None

    for fvg in fvgs:
        c1_idx = fvg['c1_idx']
        c3_idx = fvg['c3_idx']
        imb_level = fvg['imb_level']
        ff_level = fvg['ff_level']

        imb_break_idx = None
        ff_break_idx = None

        start_search = c3_idx + 1
        end_search = n - 1

        for idx in range(start_search, end_search):
            if imb_break_idx is None and lows[idx] < imb_level:
                imb_break_idx = idx
            if ff_break_idx is None and lows[idx] < ff_level:
                ff_break_idx = idx

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

        if target_break_idx is not None:
            raid_candidate = {
                'symbol': symbol,
                'tf': tf,
                'type': 'BULLISH_FVG',
                'subtype': target_subtype,
                'level': target_level,
                'break_idx': target_break_idx,
                'c1_idx': c1_idx,
                'c3_idx': c3_idx
            }
            
            if latest_bullish_raid is None or raid_candidate['break_idx'] > latest_bullish_raid['break_idx']:
                latest_bullish_raid = raid_candidate

    actual_raids = []
    if latest_bullish_raid:
        actual_raids.append(latest_bullish_raid)

    return actual_raids

def detect_bearish_fvg_and_raids(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    tf: str = "1h",
    limit: int = 25
) -> List[Dict[str, Any]]:
    """
    Детектирует медвежьи FVG (Bearish Fair Value Gap) и их каскадные рейды (пробои снизу вверх).
    Учитывает правило: берется самый свежий по времени пробой (max(break_idx)), 
    который перекрывает предыдущие (с приоритетом FF над IMB при каскаде).
    """
    if df is None or len(df) < 5:
        return []

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()

    fvgs = []
    n = len(df)
    scan_limit = n - 1

    start_idx = max(0, n - limit)
    
    for i in range(start_idx, scan_limit - 2):
        c1_idx = i
        c2_idx = i + 1
        c3_idx = i + 2

        # Условие медвежьего FVG: High 3-й свечи ниже Low 1-й свечи
        if highs[c3_idx] < lows[c1_idx]:
            fvg_top = lows[c1_idx]      # Верхняя граница (Full Fill / FF уровень)
            fvg_bottom = highs[c3_idx]  # Нижняя граница (Imbalance / IMB уровень)
            
            imb_break_idx = None
            ff_break_idx = None
            
            # Сканируем каскад пробоев после формирования FVG
            for j in range(c3_idx + 1, scan_limit + 1):
                # Пробой нижней границы (IMB)
                if imb_break_idx is None and highs[j] >= fvg_bottom:
                    imb_break_idx = j
                
                # Пробой верхней границы (FF)
                if ff_break_idx is None and (closes[j] >= fvg_top or highs[j] >= fvg_top):
                    ff_break_idx = j

            # Определяем финальный актуальный подтип с учетом каскада и приоритета
            target_subtype = None
            target_break_idx = None
            target_level = None

            # Если произошел каскад и пробит FF, смотрим, что произошло позже (максимальный индекс)
            if ff_break_idx is not None:
                target_subtype = "FF_bear"
                target_level = fvg_top
                target_break_idx = ff_break_idx
            elif imb_break_idx is not None:
                target_subtype = "IMB_bear"
                target_level = fvg_bottom
                target_break_idx = imb_break_idx

            if target_break_idx is not None:
                fvgs.append({
                    "symbol": symbol,
                    "tf": tf,
                    "type": "BEARISH_FVG",
                    "subtype": target_subtype,
                    "level": target_level,
                    "c1_idx": c1_idx,
                    "c2_idx": c2_idx,
                    "c3_idx": c3_idx,
                    "break_idx": target_break_idx,
                    "candles_ago": n - 1 - c3_idx
                })

    if not fvgs:
        return []

    # Выбираем строго самый свежий рейд по максимальному break_idx (последний каскадный пробой)
    latest_bearish_raid = max(fvgs, key=lambda x: x["break_idx"])
    return [latest_bearish_raid]