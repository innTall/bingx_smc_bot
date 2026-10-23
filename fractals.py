from datetime import timedelta
from numbers import Integral
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pandas as pd


Fractal = Dict[str, Any]


def _validated_frame(
    df: Optional[pd.DataFrame],
    required_columns: Tuple[str, ...] = ("timestamp", "high", "low"),
) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame(columns=["timestamp", "high", "low"])
    if df.empty:
        return df.reset_index(drop=True)

    missing_columns = set(required_columns).difference(df.columns)
    if missing_columns:
        raise ValueError(
            f"OHLCV data is missing required columns: {', '.join(sorted(missing_columns))}"
        )

    frame = df.reset_index(drop=True)
    if frame.empty:
        return frame

    columns_to_validate = set(required_columns)
    if "timestamp" in frame:
        columns_to_validate.add("timestamp")
    for column in columns_to_validate:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if frame[column].isna().any():
            raise ValueError(f"OHLCV column '{column}' contains missing values")

    if "timestamp" in frame and not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("OHLCV candles must be ordered by ascending timestamp")

    return frame


def analyze_fractals_v3(
    df: Optional[pd.DataFrame],
    tz_offset: float,
    symbol: str = "UNKNOWN",
) -> List[Fractal]:
    frame = _validated_frame(df)
    if len(frame) < 3:
        return []

    try:
        timezone_offset = float(tz_offset)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid timezone offset: {tz_offset!r}") from exc

    highs = frame["high"].to_numpy()
    lows = frame["low"].to_numpy()
    timestamps = frame["timestamp"].to_numpy()
    fractals: List[Fractal] = []

    for index in range(1, len(frame) - 1):
        previous_high, current_high, next_high = (
            highs[index - 1],
            highs[index],
            highs[index + 1],
        )
        previous_low, current_low, next_low = (
            lows[index - 1],
            lows[index],
            lows[index + 1],
        )
        local_datetime = pd.to_datetime(timestamps[index], unit="ms") + timedelta(
            hours=timezone_offset
        )

        if current_high > previous_high and current_high >= next_high:
            fractals.append(
                {
                    "type": "FH",
                    "index": index,
                    "datetime": local_datetime,
                    "price": current_high,
                }
            )
        if current_low < previous_low and current_low <= next_low:
            fractals.append(
                {
                    "type": "FL",
                    "index": index,
                    "datetime": local_datetime,
                    "price": current_low,
                }
            )

    active_fractals: List[Fractal] = []
    broken_fh: List[Fractal] = []
    broken_fl: List[Fractal] = []

    for fractal in fractals:
        first_break_index = _find_raid_index(frame, fractal)
        if first_break_index is None:
            fractal["status"] = "Active"
            active_fractals.append(fractal)
            continue

        fractal["broken_at"] = first_break_index
        if fractal["type"] == "FH":
            broken_fh.append(fractal)
        else:
            broken_fl.append(fractal)

    working_fractals: List[Fractal] = []

    def process_cascade(broken_list: List[Fractal]) -> None:
        if not broken_list:
            return
        latest_break_index = max(item["broken_at"] for item in broken_list)
        cascade_items = [
            item for item in broken_list if item["broken_at"] == latest_break_index
        ]
        oldest_in_cascade = min(cascade_items, key=lambda item: item["index"])
        oldest_in_cascade["status"] = "Working"
        working_fractals.append(oldest_in_cascade)

    process_cascade(broken_fh)
    process_cascade(broken_fl)

    for fractal in working_fractals:
        fractal["breakout_type"] = (
            "Raid" if fractal.get("broken_at") is not None else "Unknown"
        )

    return sorted(active_fractals + working_fractals, key=lambda item: item["index"])


def _find_raid_index(df: pd.DataFrame, fractal: Mapping[str, Any]) -> Optional[int]:
    fractal_type = fractal.get("type")
    fractal_price = fractal.get("price")
    fractal_index = fractal.get("index")
    if fractal_type not in {"FH", "FL"}:
        raise ValueError(f"Invalid fractal type: {fractal_type!r}")
    if not isinstance(fractal_index, Integral) or not 0 <= fractal_index < len(df):
        raise ValueError(f"Invalid fractal index: {fractal_index!r}")
    fractal_index = int(fractal_index)

    values = df["high" if fractal_type == "FH" else "low"].to_numpy()
    for index in range(fractal_index + 2, len(df)):
        if fractal_type == "FH" and values[index] > fractal_price:
            return index
        if fractal_type == "FL" and values[index] < fractal_price:
            return index
    return None


def check_fractal_raid(
    df: Optional[pd.DataFrame], fractal: Mapping[str, Any]
) -> Tuple[str, Optional[int]]:
    frame = _validated_frame(df, required_columns=("high", "low"))
    if frame.empty:
        return "Unknown", None

    raid_index = _find_raid_index(frame, fractal)
    return ("Raid", raid_index) if raid_index is not None else ("Unknown", None)
