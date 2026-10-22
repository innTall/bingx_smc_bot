from config import load_settings
from exchange import fetch_bingx_ohlcv
from fractals import analyze_fractals_v3, check_fractal_raid
from notifier import send_telegram_message

def format_multi_tf_report(symbol, tf_data_map):
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
        working_fl = [f for f in fractals if f['status'] == 'Working' and f['type'] == 'FL' and f.get('breakout_type') == 'Raid']
        
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
        working_fh = [f for f in fractals if f['status'] == 'Working' and f['type'] == 'FH' and f.get('breakout_type') == 'Raid']
        
        for f in working_fh:
            date_str = f['datetime'].strftime('%d%b').lower()
            fh_parts.append(f"*{tf} {f['price']}/{date_str}")
            
    if fh_parts:
        message += f"FH " + " ".join(fh_parts) + "\n"
        
    return message

if __name__ == "__main__":
    config = load_settings()
    
    symbols = config.get('symbols', ['BTC/USDT'])
    timeframes = config.get('timeframes', ['1h', '4h', '1d'])
    limit = config.get('limit', 100)
    
    print(f"[INFO] Analyzing for symbols: {symbols} | Timeframes: {timeframes}")
    
    for formatted_symbol in symbols:
        tf_data_map = {}
        
        for tf in timeframes:
            df_candles = fetch_bingx_ohlcv(symbol=formatted_symbol, timeframe=tf, limit=limit)
            
            if df_candles is not None and not df_candles.empty:
                report_fractals = analyze_fractals_v3(df_candles, config['timezone_offset_hours'], symbol=formatted_symbol)
                
                for f in report_fractals:
                    if f['status'] == 'Working':
                        b_type, b_idx = check_fractal_raid(df_candles, f)
                        f['breakout_type'] = b_type
                
                tf_data_map[tf] = {
                    'fractals': report_fractals
                }
            else:
                tf_data_map[tf] = {'fractals': []}
                
        msg_text = format_multi_tf_report(formatted_symbol, tf_data_map)
        
        if msg_text:
            send_telegram_message(
                token=config['telegram_token'],
                chat_id=config['telegram_chat_id'],
                text=msg_text
            )
            print(f"[INFO] Consolidated Telegram message sent for {formatted_symbol}.")
        else:
            print(f"[INFO] No valid data found for {formatted_symbol}, message skipped.")