import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
_ids = os.getenv("ALERT_CHAT_IDS", "")
ALERT_CHAT_IDS = [i.strip() for i in _ids.split(",") if i.strip()] if _ids else []
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "10"))
MIN_ALERT_SCORE = int(os.getenv("MIN_ALERT_SCORE", "65"))
