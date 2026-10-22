import pandas as pd
from datetime import timedelta

def analyze_fractals_v3(df, tz_offset, symbol="UNKNOWN"):
    fractals = []
    if df is None or len(df) < 3:
        return fractals

    for i in range(1, len(df) - 1):
        prev_high, curr_high, next_high = df.loc[i - 1, 'high'], df.loc[i, 'high'], df.loc[i + 1, 'high']
        prev_low, curr_low, next_low = df.loc[i - 1, 'low'], df.loc[i, 'low'], df.loc[i + 1, 'low']
        
        center_timestamp_ms = df.loc[i, 'timestamp']
        dt_local = pd.to_datetime(center_timestamp_ms, unit='ms') + timedelta(hours=tz_offset)
        
        if curr_high > prev_high and curr_high >= next_high:
            fractals.append({'type': 'FH', 'index': i, 'datetime': dt_local, 'price': curr_high})
        if curr_low < prev_low and curr_low <= next_low:
            fractals.append({'type': 'FL', 'index': i, 'datetime': dt_local, 'price': curr_low})

    active_fractals, broken_fh, broken_fl = [], [], []

    for f in fractals:
        i, price = f['index'], f['price']
        is_broken, broken_at_index = False, None

        for j in range(i + 2, len(df)):
            if f['type'] == 'FH' and df.loc[j, 'high'] > price:
                is_broken, broken_at_index = True, j
                break
            elif f['type'] == 'FL' and df.loc[j, 'low'] < price:
                is_broken, broken_at_index = True, j
                break

        if not is_broken:
            f['status'] = 'Active'
            active_fractals.append(f)
        else:
            f['broken_at'] = broken_at_index
            if f['type'] == 'FH': broken_fh.append(f)
            else: broken_fl.append(f)

    working_fractals = []
    def process_cascade(broken_list):
        if not broken_list: return
        latest_break_idx = max(item['broken_at'] for item in broken_list)
        cascade_items = [item for item in broken_list if item['broken_at'] == latest_break_idx]
        oldest_in_cascade = min(cascade_items, key=lambda x: x['index'])
        oldest_in_cascade['status'] = 'Working'
        working_fractals.append(oldest_in_cascade)

    process_cascade(broken_fh)
    process_cascade(broken_fl)

    for f in working_fractals:
        b_type, b_idx = check_fractal_raid(df, f)
        f['breakout_type'] = b_type

    return sorted(active_fractals + working_fractals, key=lambda x: x['index'])

def check_fractal_raid(df, fractal):
    f_type, f_price, f_idx = fractal['type'], fractal['price'], fractal['index']
    max_search_idx = len(df) - 2
    if f_idx + 1 > max_search_idx:
        return "Unknown", None
        
    for j in range(f_idx + 2, max_search_idx + 1):
        if f_type == 'FH' and df.loc[j, 'high'] > f_price:
            return "Raid", j
        elif f_type == 'FL' and df.loc[j, 'low'] < f_price:
            return "Raid", j
    return "Unknown", None
