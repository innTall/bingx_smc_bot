import requests

def send_telegram_message(token, chat_id, text):
    """
    Sends a text message to a Telegram channel using Telegram Bot API.
    All prints and logs are in English.
    """
    if not token or token == "YOUR_BOT_TOKEN_HERE":
        print("[WARNING] Telegram token is not set in settings.json!")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML" # Allows bold, italic, etc.
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        if data.get("ok"):
            print("[INFO] Telegram message sent successfully.")
            return True
        else:
            print(f"[ERROR] Failed to send Telegram message: {data.get('description')}")
            return False
    except Exception as e:
        print(f"[ERROR] Network error while sending Telegram message: {e}")
        return False