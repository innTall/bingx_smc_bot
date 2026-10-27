# main.py
import asyncio
import aiohttp
import logging
import time
import datetime
import numpy as np
import pandas as pd
from typing import Any, Dict, List, Mapping

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
            tf_data_map[tf] = {'fractals': [], 'snr': None, 'df': pd.DataFrame()}
            continue
            
        if isinstance(df_candles, pd.DataFrame) and not df_candles.empty:
            try:
                report_fractals: List[Fractal] = analyze_fractals_v3(
                    df_candles,
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
                tf_data_map[tf] = {'fractals': [], 'snr': None, 'df': df_candles}
                continue

            tf_data_map[tf] = {'fractals': report_fractals, 'snr': snr_report, 'df': df_candles}
        else:
            tf_data_map[tf] = {'fractals': [], 'snr': None, 'df': df_candles}
            
    return tf_data_map


async def run_analysis_cycle(session: aiohttp.ClientSession, config: Mapping[str, Any]) -> None:
    """
    Единый цикл анализа: опрос биржи, группировка по символам и отправка сводного отчета.
    """
    symbols = config.get('symbols', ['BTCUSDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 100)
    
    print(f"\n[INFO] Starting analysis cycle for symbols: {symbols} | Timeframes: {timeframes}")
    start_time = time.time()
    
    symbol_tasks = [process_symbol(session, sym, timeframes, limit, config) for sym in symbols]
    symbol_data_list = await asyncio.gather(*symbol_tasks)
    
    # Собираем словарь формата: { "BTCUSDT": { "1h": {...}, "4h": {...} }, ... }
    symbol_data_map = {
        sym: tf_map 
        for sym, tf_map in zip(symbols, symbol_data_list)
    }

    # Формируем единый сводный отчет с группировкой по символам
    report_text = format_fractal_raid_message(symbol_data_map)
    if report_text:
        success = await send_telegram_message(
            session=session,
            token=config['telegram_token'],
            chat_id=config['telegram_chat_id'],
            text=report_text
        )
        if success:
            print("[INFO] Consolidated Fractal Raid report sent successfully.")
        else:
            logger.error("Failed to send Fractal Raid report.")
            
    elapsed = time.time() - start_time
    print(f"[INFO] Analysis cycle finished in {elapsed:.2f} seconds.")

async def scheduler_loop():
    config = load_settings()
    print(f"[INFO] Scheduler started. Bot will run every hour at minute 03.")
    
    async with aiohttp.ClientSession() as session:
        while True:
            now = datetime.datetime.now()
            
            if now.minute == 5:
                current_config = load_settings()
                await run_analysis_cycle(session, current_config)
                
                print("[INFO] Waiting for the next hour...")
                await asyncio.sleep(60)
            else:
                await asyncio.sleep(15)


if __name__ == "__main__":
    try:
        asyncio.run(scheduler_loop())
    except KeyboardInterrupt:
        print("\n[INFO] Bot stopped by user.")