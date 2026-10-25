from numbers import Integral
from typing import Any, Dict, List, Optional

import pandas as pd

from fractals import Fractal, analyze_fractals_v3


SNRFractal = Dict[str, Any]
SNRReport = Dict[str, Any]


def analyze_snr_data(
    df: pd.DataFrame,
    tz_offset: float,
    symbol: str = "UNKNOWN",
    fractals: Optional[List[Fractal]] = None,
) -> SNRReport:
    """Build a debug summary from the analyzer's already verified fractals."""
    verified_fractals = (
        analyze_fractals_v3(df, tz_offset, symbol)
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
        if not isinstance(fractal_index, Integral) or not 0 <= int(fractal_index) <= last_candle_index:
            raise ValueError(f"Invalid fractal index in analysis result: {fractal_index!r}")
        fractal_index = int(fractal_index)

        raid_index = fractal.get("broken_at")
        if raid_index is not None and (
            not isinstance(raid_index, Integral)
            or not int(fractal_index) + 2 <= int(raid_index) <= last_candle_index
        ):
            raise ValueError(f"Invalid raid index in analysis result: {raid_index!r}")
        if raid_index is not None:
            raid_index = int(raid_index)

        item_data: SNRFractal = {
            "type": fractal_type,
            "price": fractal["price"],
            "candles_ago": last_candle_index - fractal_index,
            "breakout_type": fractal.get("breakout_type", "Unknown"),
            "raid_candles_ago": (
                last_candle_index - raid_index if raid_index is not None else None
            ),
            "fractal_index": fractal_index,
            "raid_index": raid_index,
        }
        if raid_index is not None:
            item_data["fh_fl_to_raid_distance"] = raid_index - fractal_index
        working[fractal_type] = item_data

    return {
        "symbol": symbol,
        "working_fh": working["FH"],
        "working_fl": working["FL"],
    }
