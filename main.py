# main.py (или main_2.py)
import asyncio
import aiohttp
import logging
import time
import datetime
import pandas as pd
from typing import Any, Dict, List, Mapping, Optional

from config import load_settings
from exchange import fetch_bingx_ohlcv_async
from fractals import analyze_fractals_v3, Fractal
from snr import analyze_snr_data
from notifier import format_snr_debug_message, send_telegram_message

logger = logging.getLogger(__name__)


def format_multi_tf_report(
    symbol: str, tf_data_map: Mapping[str, Mapping[str, Any]]
) -> Optional[str]:
    clean_symbol = symbol.split('/')[0]
    
    has_data = any(
        data.get('fractals') 
        for data in tf_data_map.values()
    )
    if not has_data:
        return None

    message = f"<b>{clean_symbol}</b>\n"
    priority_tfs = ['1h', '4h', '1d']
    
    # LONG BLOCK (FL)
    fl_parts = []
    for tf in priority_tfs:
        tf_info = tf_data_map.get(tf, {})
        fractals = tf_info.get('fractals', [])
        working_fl = [
            f for f in fractals 
            if f['status'] == 'Working' and f['type'] == 'FL' and f.get('breakout_type') == 'Raid'
        ]
        
        for f in working_fl:
            date_str = f['datetime'].strftime('%d%b').lower()
            fl_parts.append(f"*{tf} {f['price']}/{date_str}")

    if fl_parts:
        message += f"FL " + " ".join(fl_parts) + "\n"

    # SHORT BLOCK (FH)
    fh_parts = []
    for tf in priority_tfs:
        tf_info = tf_data_map.get(tf, {})
        fractals = tf_info.get('fractals', [])
        working_fh = [
            f for f in fractals 
            if f['status'] == 'Working' and f['type'] == 'FH' and f.get('breakout_type') == 'Raid'
        ]
        
        for f in working_fh:
            date_str = f['datetime'].strftime('%d%b').lower()
            fh_parts.append(f"*{tf} {f['price']}/{date_str}")
            
    if fh_parts:
        message += f"FH " + " ".join(fh_parts) + "\n"
        
    return message

async def process_symbol(
    session: aiohttp.ClientSession,
    formatted_symbol: str,
    timeframes: List[str],
    limit: int,
    config: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    tf_data_map = {}
    
    # Создаем задачи для одновременного запроса всех таймфреймов по текущей монете
    tasks = [fetch_bingx_ohlcv_async(session, formatted_symbol, tf, limit) for tf in timeframes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for tf, df_candles in zip(timeframes, results):
        # Безопасная проверка на исключение или то, что это не DataFrame
        if isinstance(df_candles, BaseException):
            logger.error(
                "Unable to fetch candles for %s (%s): %s",
                formatted_symbol,
                tf,
                df_candles,
            )
            tf_data_map[tf] = {'fractals': [], 'snr': None}
            continue
            
        if isinstance(df_candles, pd.DataFrame) and not df_candles.empty:
            try:
                report_fractals: List[Fractal] = analyze_fractals_v3(
                    df_candles,
                    config.get('timezone_offset_hours', 0),
                    symbol=formatted_symbol,
                )
                snr_report = analyze_snr_data(
                    df_candles,
                    config.get('timezone_offset_hours', 0),
                    symbol=formatted_symbol,
                    fractals=report_fractals,
                )
            except (KeyError, TypeError, ValueError, OverflowError):
                logger.exception(
                    "Unable to analyze candles for %s (%s)",
                    formatted_symbol,
                    tf,
                )
                tf_data_map[tf] = {'fractals': [], 'snr': None}
                continue

            tf_data_map[tf] = {'fractals': report_fractals, 'snr': snr_report}
        else:
            tf_data_map[tf] = {'fractals': [], 'snr': None}
            
    msg_text = format_multi_tf_report(formatted_symbol, tf_data_map)
    
    if msg_text:
        await send_telegram_message(
            session=session,
            token=config['telegram_token'],
            chat_id=config['telegram_chat_id'],
            text=msg_text
        )
        print(f"[INFO] Consolidated Telegram message sent for {formatted_symbol}.")
    else:
        print(f"[INFO] No valid data found for {formatted_symbol}, message skipped.")
    return tf_data_map

async def main():
    config = load_settings()
    
    symbols = config.get('symbols', ['BTC/USDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 100)
    
    print(f"[INFO] Starting async analysis for symbols: {symbols} | Timeframes: {timeframes}")
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        symbol_tasks = [process_symbol(session, sym, timeframes, limit, config) for sym in symbols]
        await asyncio.gather(*symbol_tasks)
        
    elapsed = time.time() - start_time
    print(f"[INFO] All symbols processed in {elapsed:.2f} seconds.")

async def scheduler_loop():
    config = load_settings()
    symbols = config.get('symbols', ['BTC/USDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 100)
    
    print(f"[INFO] Scheduler started. Bot will run every hour at xx:03.")
    
    async with aiohttp.ClientSession() as session:
        while True:
            now = datetime.datetime.now()
            
            if now.minute == 3:
                print(f"\n[INFO] Starting scheduled analysis at {now.strftime('%Y-%m-%d %H:%M:%S')}")
                start_time = time.time()
                
                symbol_tasks = [process_symbol(session, sym, timeframes, limit, config) for sym in symbols]
                symbol_data = await asyncio.gather(*symbol_tasks)
                
                for tf in timeframes:
                    snr_reports = []
                    for tf_data_map in symbol_data:
                        snr_data = tf_data_map.get(tf, {}).get('snr')
                        if snr_data is not None:
                            snr_reports.append(snr_data)
                    
                    if snr_reports:
                        debug_msg = format_snr_debug_message(snr_reports, tf)
                        await send_telegram_message(
                            session=session,
                            token=config['telegram_token'],
                            chat_id=config['telegram_chat_id'],
                            text=debug_msg
                        )
                        print(f"[INFO] SNR Debug report sent for TF {tf}.")
                
                elapsed = time.time() - start_time
                print(f"[INFO] Cycle finished in {elapsed:.2f} seconds. Waiting for the next hour...")
                
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(15)

if __name__ == "__main__":
    try:
        asyncio.run(scheduler_loop())
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")