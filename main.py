# main.py
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
from notifier import format_fractal_raid_message, send_telegram_message

logger = logging.getLogger(__name__)
		
async def process_symbol(
    session: aiohttp.ClientSession,
    formatted_symbol: str,
    timeframes: List[str],
    limit: int,
    config: Mapping[str, Any],
) -> Dict[str, Dict[str, Any]]:
    tf_data_map = {}
    
    tasks = [fetch_bingx_ohlcv_async(session, formatted_symbol, tf, limit) for tf in timeframes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for tf, df_candles in zip(timeframes, results):
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
            
    # Убрали отправку multi_tf сообщений по каждому символу отдельно.
    # Теперь отправка происходит строго по таймфреймам в scheduler_loop.
    return tf_data_map

async def main():
    config = load_settings()
    
    symbols = config.get('symbols', ['BTCUSDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 100)
    
    print(f"[INFO] Starting async analysis for symbols: {symbols} | Timeframes: {timeframes}")
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        symbol_tasks = [process_symbol(session, sym, timeframes, limit, config) for sym in symbols]
        symbol_data = await asyncio.gather(*symbol_tasks)
        
        # Ручной тестовый запуск отправки Fractal Raid Report сразу при старте (для проверки)
        for tf in timeframes:
            snr_reports = []
            for tf_data_map in symbol_data:
                snr_data = tf_data_map.get(tf, {}).get('snr')
                if snr_data is not None:
                    snr_reports.append(snr_data)
            
            if snr_reports:
                debug_msg = format_fractal_raid_message(snr_reports, tf)
                await send_telegram_message(
                    session=session,
                    token=config['telegram_token'],
                    chat_id=config['telegram_chat_id'],
                    text=debug_msg
                )
                print(f"[INFO] Fractal Raid report sent for TF {tf}.")
        
    elapsed = time.time() - start_time
    print(f"[INFO] All symbols processed in {elapsed:.2f} seconds.")

async def scheduler_loop():
    config = load_settings()
    symbols = config.get('symbols', ['BTCUSDT'])
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
                        debug_msg = format_fractal_raid_message(snr_reports, tf)
                        await send_telegram_message(
                            session=session,
                            token=config['telegram_token'],
                            chat_id=config['telegram_chat_id'],
                            text=debug_msg
                        )
                        print(f"[INFO] Fractal Raid report sent for TF {tf}.")
                
                elapsed = time.time() - start_time
                print(f"[INFO] Cycle finished in {elapsed:.2f} seconds. Waiting for the next hour...")
                
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(15)

if __name__ == "__main__":
    try:
        asyncio.run(scheduler_loop())
    except KeyboardInterrupt:
        print("\n[INFO] Stopped by user.")