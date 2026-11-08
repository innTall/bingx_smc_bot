# main.py
import asyncio
import aiohttp
import logging
import time
import datetime
import pandas as pd
from typing import Any, Dict, List, Mapping, Coroutine

from config import load_settings
from exchange import fetch_bingx_ohlcv_async
from fractals import analyze_fractals_v3, Fractal
from snr import analyze_snr_data, _find_fvg_kl_snr_short
from notifier import format_fractal_raid_message, send_telegram_message, format_kl_snr_message, format_trading_levels_message, format_single_symbol_report
from fvg import detect_bullish_fvg_and_raids, detect_bearish_fvg_and_raids

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
    
    fvg_history_limit = config.get('limit', 25)

    for tf, df_candles in zip(timeframes, results):
        if isinstance(df_candles, BaseException):
            logger.error(
                "Unable to fetch candles for %s (%s): %s",
                formatted_symbol,
                tf,
                df_candles,
            )
            tf_data_map[tf] = {'fractals': [], 'snr': None, 'fvgs': [], 'df': pd.DataFrame()}
            continue
            
        if isinstance(df_candles, pd.DataFrame) and not df_candles.empty:
            try:
                # 1. Анализ фракталов
                report_fractals: List[Fractal] = analyze_fractals_v3(
                    df_candles,
                    symbol=formatted_symbol,
                )

                # 2. Анализ Bullish FVG и их Raid
                bullish_fvgs = detect_bullish_fvg_and_raids(
                    df=df_candles,
                    symbol=formatted_symbol,
                    tf=tf,
                    limit=fvg_history_limit
                )

                # Анализ Bearish FVG и их Raid
                bearish_fvgs = detect_bearish_fvg_and_raids(
                    df=df_candles,
                    symbol=formatted_symbol,
                    tf=tf,
                    limit=fvg_history_limit
                )

                # ТЕСТ ШАГ 1: Проверяем поиск ПОСЛЕДНЕГО KL SNR для Bearish FVG рейдов
                if bearish_fvgs:
                    latest_raid = bearish_fvgs[0]  # Берем единственный самый свежий рейд
                    raid_idx = latest_raid.get('break_idx')
                    c1_idx = latest_raid.get('c1_idx')
                    
                    if raid_idx is not None and c1_idx is not None:
                        kl_short = _find_fvg_kl_snr_short(
                            df=df_candles,
                            c1_idx=int(c1_idx),
                            raid_index=int(raid_idx),
                            snr_candles=config.get('SNR_candles', 10)
                        )
                        
                # 3. Анализ SNR
                snr_report = analyze_snr_data(
                    df_candles,
                    symbol=formatted_symbol,
                    fractals=report_fractals,
                    snr_candles=config.get('SNR_candles', 5),
                    sl_max=config.get('SL_max', 5),
                    SNR_history=config.get('SNR_history', 10),
                    bullish_raids=bullish_fvgs,
                    bearish_raids=bearish_fvgs,
                )

            except (KeyError, TypeError, ValueError, OverflowError):
                logger.exception(
                    "Unable to analyze candles for %s (%s)",
                    formatted_symbol,
                    tf,
                )
                tf_data_map[tf] = {'fractals': [], 'snr': None, 'fvgs': [], 'df': df_candles}
                continue

            tf_data_map[tf] = {
                'fractals': report_fractals,
                'snr': snr_report,
                'fvgs': bullish_fvgs,
                'df': df_candles
            }
        else:
            tf_data_map[tf] = {'fractals': [], 'snr': None, 'fvgs': [], 'df': df_candles}
            
    return tf_data_map


async def run_analysis_cycle(session: aiohttp.ClientSession, config: Mapping[str, Any]) -> None:
    symbols = config.get('symbols', ['BTCUSDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 25)
    
    print(f"\n[INFO] Starting analysis cycle for symbols: {symbols} | Timeframes: {timeframes}")
    start_time = time.time()
    
    symbol_tasks: List[Coroutine[Any, Any, Dict[str, Dict[str, Any]]]] = [
        process_symbol(session, sym, timeframes, limit, config) for sym in symbols
    ]
    symbol_data_list = await asyncio.gather(*symbol_tasks)
    
    symbol_data_map = {
        sym: tf_map 
        for sym, tf_map in zip(symbols, symbol_data_list)
    }
    '''
    # --- БЛОК 1: Fractal Raid Report ---
    if config.get('send_fractal_raid_report', True):
        raid_report_text = format_fractal_raid_message(symbol_data_map)
        if raid_report_text:
            await send_telegram_message(
                session=session,
                token=config['telegram_token'],
                chat_id=config['telegram_chat_id'],
                text=raid_report_text
            )

    # --- БЛОК 2: KL SNR Report ---
    if config.get('send_kl_snr_report', False):
        snr_report_text = format_kl_snr_message(symbol_data_map)
        if snr_report_text:
            await send_telegram_message(
                session=session,
                token=config['telegram_token'],
                chat_id=config['telegram_chat_id'],
                text=snr_report_text
            )
    
    # --- БЛОК 3: Trading Levels Report ---
    if config.get('send_trading_levels_report', True):
        trading_levels_text = format_trading_levels_message(symbol_data_map)
        if trading_levels_text:
            await send_telegram_message(
                session=session,
                token=config['telegram_token'],
                chat_id=config['telegram_chat_id'],
                text=trading_levels_text
            )
    '''

    # --- БЛОК: Безопасная отправка раздельных отчетов по символам через Producer-Consumer очередь ---
    queue = asyncio.Queue()
    
    # Сначала собираем сообщения в очередь (Producer)
    for symbol in sorted(symbol_data_map.keys()):
        msg = format_single_symbol_report(symbol, symbol_data_map[symbol])
        if msg:
            await queue.put(msg)

    total_signals = queue.qsize()
    print(f"[INFO] Total symbol signals queued for Telegram: {total_signals}")

    # Запускаем воркер (Consumer) с лимитом макс. 20 сообщений и паузой 3.5с
    if total_signals > 0:
        await telegram_worker(
            session=session,
            token=config['telegram_token'],
            chat_id=config['telegram_chat_id'],
            queue=queue,
            max_messages=20
        )

    elapsed = time.time() - start_time
    print(f"[INFO] Analysis cycle finished in {elapsed:.2f} seconds.")

async def telegram_worker(session: aiohttp.ClientSession, token: str, chat_id: str, queue: asyncio.Queue, max_messages: int = 20):
    """
    Consumer: достает сообщения из очереди, отправляет с задержкой и ограничивает лимит до max_messages.
    """
    sent_count = 0
    while not queue.empty():
        if sent_count >= max_messages:
            logger.warning("[WARNING] Reached max telegram messages limit (%d) for this cycle. Skipping remaining.", max_messages)
            print(f"[INFO] Reached max telegram messages limit ({max_messages}).")
            # Очищаем оставшееся в очереди
            while not queue.empty():
                queue.get_nowait()
                queue.task_done()
            break

        message_text = await queue.get()
        try:
            await send_telegram_message(session=session, token=token, chat_id=chat_id, text=message_text)
            sent_count += 1
        except Exception as e:
            logger.error("Failed to send queued message: %s", e)
        finally:
            queue.task_done()
            
        # Пауза между сообщениями (3.5 секунды) для защиты от лимитов Telegram
        if not queue.empty():
            await asyncio.sleep(3.5)

async def scheduler_loop():
    print(f"[INFO] Scheduler started. Bot will run every hour.")
    
    async with aiohttp.ClientSession() as session:
        while True:
            now = datetime.datetime.now()
            if now.minute == 10:
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