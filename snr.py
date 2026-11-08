# snr.py
from numbers import Integral
from typing import Any, Dict, List, Optional
import pandas as pd
import numpy as np

from fractals import Fractal, analyze_fractals_v3

SNRReport = Dict[str, Any]


def _safe_int_index(val: Any, length: int) -> Optional[int]:
    """Безопасно преобразует значение в индекс с проверкой границ и типов."""
    if val is None or isinstance(val, bool):
        return None
    try:
        if isinstance(val, Integral):
            i = int(val)
            if 0 <= i < length:
                return i
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _calculate_sl_percent(entry: Any, stop_loss: Any, sl_max: float) -> Optional[float]:
    try:
        entry_price = float(entry)
        stop_loss_price = float(stop_loss)
        max_percent = float(sl_max)
    except (TypeError, ValueError, OverflowError):
        return None

    if (
        not np.isfinite(entry_price)
        or not np.isfinite(stop_loss_price)
        or not np.isfinite(max_percent)
        or entry_price <= 0
        or stop_loss_price <= 0
        or max_percent <= 0
    ):
        return None

    sl_percent = abs(entry_price - stop_loss_price) / entry_price * 100.0
    if not np.isfinite(sl_percent) or sl_percent > max_percent:  # Было >=, стало >
        return None
    return sl_percent


def _get_candle_type(open_p: float, close_p: float) -> str:
    if close_p > open_p:
        return "UP"
    elif close_p < open_p:
        return "DOWN"
    return "FLAT"


def _find_kl_snr(df: pd.DataFrame, fractal_index: int, raid_index: int, f_type: str, 
    snr_candles: int = 5) -> Optional[Dict[str, Any]]:
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()

    max_lookback_index = raid_index - snr_candles
    start_left_limit = max(fractal_index, max_lookback_index)

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
            level_price = l_close
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
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    
    kl_price = kl_info["level_price"]
    kl_right_idx = kl_info["right_index"]
    
    end_idx = min(len(df), raid_index + snr_candles)
    
    formation_idx = None
    for i in range(raid_index, end_idx + 1):
        if i >= len(df):
            break
        c = closes[i]
        
        if f_type == "FH" and c < kl_price:
            formation_idx = i
            break
        elif f_type == "FL" and c > kl_price:
            formation_idx = i
            break
            
    if formation_idx is None:
        return None
        
    sub_highs = highs[kl_right_idx : formation_idx + 1]
    sub_lows = lows[kl_right_idx : formation_idx + 1]
    
    if f_type == "FH":
        stop_loss = float(np.max(sub_highs))
    else:
        stop_loss = float(np.min(sub_lows))
        
    entry = kl_price
    sl_percent = _calculate_sl_percent(entry, stop_loss, sl_max)
    if sl_percent is None:
        return None
        
    candles_ago = len(df) - 1 - formation_idx
    
    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "sl_percent": round(sl_percent, 1),
        "candles_ago": candles_ago,
        "formation_index": formation_idx
    }


def analyze_snr_data(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    fractals: Optional[List[Fractal]] = None,
    snr_candles: int = 5,
    sl_max: float = 5.0,
    SNR_history: int = 10,
    bullish_raids: Optional[List[Dict[str, Any]]] = None,
    bearish_raids: Optional[List[Dict[str, Any]]] = None,
) -> SNRReport:
    verified_fractals = (
        analyze_fractals_v3(df, symbol=symbol)
        if fractals is None
        else fractals
    )
    valid_fh_list: List[Dict[str, Any]] = []
    valid_fl_list: List[Dict[str, Any]] = []
    valid_fvg_snr_long_list: List[Dict[str, Any]] = []
    valid_fvg_snr_short_list: List[Dict[str, Any]] = []

    if df.empty:
        return {
            "symbol": symbol,
            "working_fh": None,
            "working_fl": None,
            "working_fvg_snr_long": None,
            "working_fvg_snr_short": None,
        }

    df_len = len(df)

    for fractal in verified_fractals:
        fractal_type = fractal.get("type")
        fractal_index = fractal.get("index")
        if fractal.get("status") != "Working" or fractal_type not in ["FH", "FL"]:
            continue
        
        fractal_index_int = _safe_int_index(fractal_index, df_len)
        if fractal_index_int is None:
            continue
            
        raid_index = fractal.get("broken_at")
        r_idx_int = _safe_int_index(raid_index, df_len)

        if r_idx_int is not None:
            kl = _find_kl_snr(df, fractal_index_int, r_idx_int, fractal_type, snr_candles)

            if kl:
                formed_snr = _find_formed_snr(df, kl, r_idx_int, fractal_type, snr_candles, sl_max)
                if formed_snr:
                    if formed_snr["candles_ago"] <= SNR_history:
                        signal_data = {
                            "type": fractal_type,
                            "price": fractal["price"],
                            "raid_candles_ago": df_len - 1 - r_idx_int,
                            "kl_snr": kl,
                            "entry": formed_snr["entry"],
                            "stop_loss": formed_snr["stop_loss"],
                            "sl_percent": formed_snr["sl_percent"],
                            "candles_ago": formed_snr["candles_ago"],
                            "formation_index": formed_snr["formation_index"]
                        }
                        if fractal_type == "FH":
                            valid_fh_list.append(signal_data)
                        else:
                            valid_fl_list.append(signal_data)

    best_fh = min(valid_fh_list, key=lambda x: x["candles_ago"]) if valid_fh_list else None
    best_fl = min(valid_fl_list, key=lambda x: x["candles_ago"]) if valid_fl_list else None

    # Bullish FVG SNR (Long)
    if bullish_raids:
        for raid in bullish_raids:
            raid_idx = raid.get('break_idx')
            c1_idx = raid.get('c1_idx')
            
            r_idx_int = _safe_int_index(raid_idx, df_len)
            c1_idx_int = _safe_int_index(c1_idx, df_len)
            
            if r_idx_int is not None and c1_idx_int is not None:
                kl = _find_fvg_kl_snr_long(df, c1_idx_int, r_idx_int, snr_candles)
                if kl:
                    formed = _find_fvg_formed_snr_long(df, kl, r_idx_int, snr_candles, sl_max, SNR_history)
                    if formed:
                        valid_fvg_snr_long_list.append({
                            "type": f"{raid.get('subtype', 'IMB')}_bull",
                            "entry": formed["entry"],
                            "stop_loss": formed["stop_loss"],
                            "sl_percent": formed["sl_percent"],
                            "candles_ago": formed["candles_ago"],
                            "formation_index": formed["formation_index"]
                        })

    best_fvg_snr_long = min(valid_fvg_snr_long_list, key=lambda x: x["candles_ago"]) if valid_fvg_snr_long_list else None

    # Bearish FVG SNR (Short)
    if bearish_raids:
        for raid in bearish_raids:
            raid_idx = raid.get('break_idx')
            c1_idx = raid.get('c1_idx')
            
            r_idx_int = _safe_int_index(raid_idx, df_len)
            c1_idx_int = _safe_int_index(c1_idx, df_len)
            
            if r_idx_int is not None and c1_idx_int is not None:
                kl = _find_fvg_kl_snr_short(df, c1_idx_int, r_idx_int, snr_candles)
                if kl:
                    formed = _find_fvg_formed_snr_short(df, kl, r_idx_int, snr_candles, sl_max, SNR_history)
                    if formed:
                        valid_fvg_snr_short_list.append({
                            "type": f"{raid.get('subtype', 'IMB')}_bear",
                            "entry": formed["entry"],
                            "stop_loss": formed["stop_loss"],
                            "sl_percent": formed["sl_percent"],
                            "candles_ago": formed["candles_ago"],
                            "formation_index": formed["formation_index"]
                        })

    best_fvg_snr_short = min(valid_fvg_snr_short_list, key=lambda x: x["candles_ago"]) if valid_fvg_snr_short_list else None

    return {
        "symbol": symbol,
        "working_fh": best_fh,
        "working_fl": best_fl,
        "working_fvg_snr_long": best_fvg_snr_long,
        "working_fvg_snr_short": best_fvg_snr_short
    }


def _find_fvg_kl_snr_long(df: pd.DataFrame, c1_idx: int, raid_index: int, snr_candles: int = 5) -> Optional[Dict[str, Any]]:
    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()

    left_bound = max(0, raid_index - snr_candles)
    start_left_limit = max(c1_idx, left_bound)

    if raid_index <= start_left_limit:
        return None

    for i in range(raid_index, start_left_limit, -1):
        left_idx = i - 1
        right_idx = i

        if left_idx < 0 or right_idx >= len(df):
            continue

        l_open, l_close = opens[left_idx], closes[left_idx]
        r_open, r_close = opens[right_idx], closes[right_idx]

        l_type = "UP" if l_close > l_open else ("DOWN" if l_close < l_open else "FLAT")
        r_type = "UP" if r_close > r_open else ("DOWN" if r_close < r_open else "FLAT")

        if l_type == "UP" and r_type == "DOWN":
            level_price = l_close
            return {
                "level_price": level_price,
                "left_index": left_idx,
                "right_index": right_idx,
                "candles_ago_left": len(df) - 1 - left_idx,
            }

    return None


def _find_fvg_formed_snr_long(
    df: pd.DataFrame, 
    kl_info: Dict[str, Any], 
    raid_index: int, 
    snr_candles: int = 5,
    sl_max: float = 5.0,
    SNR_history: int = 10
) -> Optional[Dict[str, Any]]:
    closes = df["close"].to_numpy()
    lows = df["low"].to_numpy()
    
    kl_price = kl_info["level_price"]
    kl_right_idx = kl_info["right_index"]
    
    end_idx = min(len(df), raid_index + snr_candles)
    
    formation_idx = None
    for i in range(raid_index, end_idx + 1):
        if i >= len(df):
            break
        if closes[i] > kl_price:
            formation_idx = i
            break
            
    if formation_idx is None:
        return None
        
    sub_lows = lows[kl_right_idx : formation_idx + 1]
    stop_loss = float(np.min(sub_lows))
        
    entry = kl_price
    sl_percent = _calculate_sl_percent(entry, stop_loss, sl_max)
    if sl_percent is None:
        return None

    is_invalidated = False
    for idx in range(formation_idx + 1, len(df)):
        if lows[idx] < stop_loss:
            is_invalidated = True
            break

    if is_invalidated:
        return None  

    candles_ago = len(df) - 1 - formation_idx
    if candles_ago > SNR_history:
        return None

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "sl_percent": round(sl_percent, 1),
        "candles_ago": candles_ago,
        "formation_index": formation_idx
    }


def _find_fvg_kl_snr_short(df: pd.DataFrame, c1_idx: int, raid_index: int, snr_candles: int = 5) -> Optional[Dict[str, Any]]:
    if _safe_int_index(c1_idx, len(df)) is None or _safe_int_index(raid_index, len(df)) is None:
        return None

    c1_int = int(c1_idx)
    r_idx = int(raid_index)

    opens = df["open"].to_numpy()
    closes = df["close"].to_numpy()

    left_bound = max(0, r_idx - snr_candles)
    start_left_limit = max(c1_int, left_bound)

    if r_idx <= start_left_limit:
        return None

    for i in range(r_idx, start_left_limit, -1):
        left_idx = i - 1
        right_idx = i

        if left_idx < 0 or right_idx >= len(df):
            continue

        l_open, l_close = opens[left_idx], closes[left_idx]
        r_open, r_close = opens[right_idx], closes[right_idx]

        l_type = "UP" if l_close > l_open else ("DOWN" if l_close < l_open else "FLAT")
        r_type = "UP" if r_close > r_open else ("DOWN" if r_close < r_open else "FLAT")

        if l_type == "DOWN" and r_type == "UP":
            level_price = l_close
            return {
                "level_price": level_price,
                "left_index": left_idx,
                "right_index": right_idx,
                "candles_ago_left": len(df) - 1 - left_idx,
            }

    return None


def _find_fvg_formed_snr_short(
    df: pd.DataFrame, 
    kl_info: Dict[str, Any], 
    raid_index: int, 
    snr_candles: int = 5,
    sl_max: float = 5.0,
    SNR_history: int = 10
) -> Optional[Dict[str, Any]]:
    if _safe_int_index(raid_index, len(df)) is None:
        return None

    r_idx = int(raid_index)
    closes = df["close"].to_numpy()
    highs = df["high"].to_numpy()
    
    kl_price = kl_info["level_price"]
    kl_right_idx = kl_info["right_index"]
    
    end_idx = min(len(df), r_idx + snr_candles)
    
    formation_idx = None
    for i in range(r_idx, end_idx + 1):
        if i >= len(df):
            break
        # Для шорта формирование происходит, когда цена закрытия падает ниже KL цены
        if closes[i] < kl_price:
            formation_idx = i
            break
            
    if formation_idx is None:
        return None
        
    sub_highs = highs[kl_right_idx : formation_idx + 1]
    stop_loss = float(np.max(sub_highs))
        
    entry = kl_price
    sl_percent = _calculate_sl_percent(entry, stop_loss, sl_max)
    if sl_percent is None:
        return None

    # Проверка на инвалидацию: если цена поднялась выше stop_loss
    is_invalidated = False
    for idx in range(formation_idx + 1, len(df)):
        if highs[idx] > stop_loss:
            is_invalidated = True
            break

    if is_invalidated:
        return None  

    candles_ago = len(df) - 1 - formation_idx
    if candles_ago > SNR_history:
        return None

    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "sl_percent": round(sl_percent, 1),
        "candles_ago": candles_ago,
        "formation_index": formation_idx
    }