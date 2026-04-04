import os
from dotenv import load_dotenv
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ALERT_CHAT_IDS = os.getenv("ALERT_CHAT_IDS", "").split(",") if os.getenv("ALERT_CHAT_IDS") else []
SCAN_INTERVAL_MINUTES = int(os.getenv("SCAN_INTERVAL_MINUTES", "10"))
