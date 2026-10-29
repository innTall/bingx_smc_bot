# snr.py
from numbers import Integral
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from fractals import Fractal, analyze_fractals_v3

SNRFractal = Dict[str, Any]
SNRReport = Dict[str, Any]


def _get_candle_type(open_p: float, close_p: float) -> str:
    if close_p > open_p:
        return "UP"
    elif close_p < open_p:
        return "DOWN"
    return "FLAT"


def _find_kl_snr(df: pd.DataFrame, fractal_index: int, raid_index: int, f_type: str, 
    snr_candles: int = 5) -> Optional[Dict[str, Any]]:
    """
    Ищет KL SNR между индексом фрактала и индексом рейда, двигаясь от Raid влево (в прошлое).
    Комбинация из 2-х свечей (пара i-1 и i):
    - Для FH (Short): слева DOWN, справа UP.
    - Для FL (Long): слева UP, справа DOWN.
    Значение snr_candles включает в себя саму свечу Raid (правая свеча пары может быть на индексе raid_index).
    """
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()

    # Ограничиваем левую границу поиска: либо фрактал, либо отступ на snr_candles влево от рейда
    max_lookback_index = raid_index - snr_candles
    start_left_limit = max(fractal_index, max_lookback_index)

    # Двигаемся от raid_index влево до start_left_limit
    # Проверяем пару: левая (i - 1), права (i)
    for i in range(raid_index, start_left_limit, -1):
        left_idx = i - 1
        right_idx = i

        if left_idx < 0 or right_idx >= len(df):
            continue

        l_open, l_close = opens[left_idx], closes[left_idx]
        r_open, r_close = opens[right_idx], closes[right_idx]

        l_type = _get_candle_type(l_open, l_close)
        r_type = _get_candle_type(r_open, r_close)

        match_found = False
        if f_type == "FH" and l_type == "DOWN" and r_type == "UP":
            match_found = True
        elif f_type == "FL" and l_type == "UP" and r_type == "DOWN":
            match_found = True

        if match_found:
            level_price = l_close  # Приоритет Close при гэпе
            return {
                "level_price": level_price,
                "left_index": left_idx,
                "right_index": right_idx,
                "candles_ago_left": len(df) - 1 - left_idx,
            }

    return None

def _find_formed_snr(
    df: pd.DataFrame, 
    kl_info: Dict[str, Any], 
    raid_index: int, 
    f_type: str, 
    snr_candles: int = 5,
    sl_max: float = 5.0
) -> Optional[Dict[str, Any]]:
    """
    Проверяет формирование SNR вправо от Raid в пределах snr_candles:
    - Свеча (начиная с Raid candle) должна пробить KL SNR и закрыться (Close) за ним.
    - Entry = цена KL SNR.
    - StopLoss = экстремум (High/Low) между KL SNR и свечой пробоя.
    - Проверяется условие риска: расстояние (Entry до SL) < sl_max (%).
    """
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    
    kl_price = kl_info["level_price"]
    kl_right_idx = kl_info["right_index"]
    
    # Двигаемся вправо от raid_index до raid_index + snr_candles (включая raid_index как возможную свечу формирования)
    end_idx = min(len(df), raid_index + snr_candles)
    
    formation_idx = None
    for i in range(raid_index, end_idx + 1):
        if i >= len(df):
            break
        c = closes[i]
        
        # Проверяем пробой и закрытие за уровнем
        if f_type == "FH" and c < kl_price:  # Short: Close ниже уровня
            formation_idx = i
            break
        elif f_type == "FL" and c > kl_price:  # Long: Close выше уровня
            formation_idx = i
            break
            
    if formation_idx is None:
        return None
        
    # Определяем StopLoss как экстремум в диапазоне от правого края KL SNR до свечи пробоя
    sub_highs = highs[kl_right_idx : formation_idx + 1]
    sub_lows = lows[kl_right_idx : formation_idx + 1]
    
    if f_type == "FH":
        stop_loss = float(np.max(sub_highs))
    else:
        stop_loss = float(np.min(sub_lows))
        
    entry = kl_price
    if entry == 0:
        return None
        
    # Расчет процента риска
    sl_percent = abs(entry - stop_loss) / entry * 100.0
    
    if sl_percent >= sl_max:
        return None  # Стоп-лосс превышает допустимый риск (SL_max)
        
    candles_ago = len(df) - 1 - formation_idx
    
    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "sl_percent": round(sl_percent, 2),
        "candles_ago": candles_ago,
        "formation_index": formation_idx
    }

def analyze_snr_data(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    fractals: Optional[List[Fractal]] = None,
    snr_candles: int = 5,
    sl_max: float = 5.0,
) -> SNRReport:
    """Анализирует фракталы и находит для них KL SNR и сформированные SNR уровни."""
    verified_fractals = (
        analyze_fractals_v3(df, symbol=symbol)
        if fractals is None
        else fractals
    )
    last_candle_index = len(df) - 1
    working: Dict[str, Optional[SNRFractal]] = {"FH": None, "FL": None}

    for fractal in verified_fractals:
        fractal_type = fractal.get("type")
        fractal_index = fractal.get("index")
        if fractal.get("status") != "Working" or fractal_type not in working:
            continue
        
        if fractal_index is None:
            continue
        fractal_index_int = int(fractal_index)
        
        raid_index = fractal.get("broken_at")

        raid_candles_ago = None
        r_idx_int = None
        if raid_index is not None:
            r_idx_int = int(raid_index)
            raid_candles_ago = last_candle_index - r_idx_int

        item_data: SNRFractal = {
            "type": fractal_type,
            "price": fractal["price"],
            "candles_ago": last_candle_index - fractal_index_int,
            "breakout_type": fractal.get("breakout_type", "Unknown"),
            "raid_candles_ago": raid_candles_ago,
            "kl_snr": None,
        }

        if r_idx_int is not None:
            item_data["fh_fl_to_raid_distance"] = r_idx_int - fractal_index_int
            kl = _find_kl_snr(df, fractal_index_int, r_idx_int, fractal_type, snr_candles)
            item_data["kl_snr"] = kl

            if kl:
                # Проверяем формирование SNR вправо от рейда с учетом параметров
                formed_snr = _find_formed_snr(df, kl, r_idx_int, fractal_type, snr_candles, sl_max)
                if formed_snr:
                    item_data["snr_formed"] = formed_snr

        working[fractal_type] = item_data

    return {
        "symbol": symbol,
        "working_fh": working["FH"],
        "working_fl": working["FL"],
    }