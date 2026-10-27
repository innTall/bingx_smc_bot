# snr.py
from numbers import Integral
from typing import Any, Dict, List, Optional
import pandas as pd

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
    """
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()

    # Ограничиваем левую границу поиска: либо фрактал, либо отступ на snr_candles влево от рейда,
    # в зависимости от того, что ближе (чтобы не выйти за границы диапазона и не копать слишком глубоко).
    max_lookback_index = raid_index - snr_candles
    start_left_limit = max(fractal_index, max_lookback_index)

    # Двигаемся от raid_index влево до fractal_index + 1
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


def analyze_snr_data(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    fractals: Optional[List[Fractal]] = None,
) -> SNRReport:
    """Анализирует фракталы и находит для них KL SNR уровни."""
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
            item_data["kl_snr"] = _find_kl_snr(df, fractal_index_int, r_idx_int, fractal_type)

        working[fractal_type] = item_data

    return {
        "symbol": symbol,
        "working_fh": working["FH"],
        "working_fl": working["FL"],
    }