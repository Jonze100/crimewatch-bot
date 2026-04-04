import json, os
WATCHLIST_FILE = "watchlist.json"
DEFAULT = [
    "STOUSDT", "ARIAUSDT", "BTCUSDT", "ETHUSDT",
    "SOLUSDT", "DOGEUSDT", "PEPEUSDT", "WIFUSDT",
    "ONDOUSDT", "MOODENGUSDT"
]
def load_watchlist():
    if not os.path.exists(WATCHLIST_FILE):
        save_watchlist(DEFAULT); return DEFAULT
    with open(WATCHLIST_FILE) as f: return json.load(f)
def save_watchlist(wl):
    with open(WATCHLIST_FILE, "w") as f: json.dump(wl, f, indent=2)
def add_to_watchlist(s):
    wl = load_watchlist()
    if s in wl: return False
    wl.append(s); save_watchlist(wl); return True
def remove_from_watchlist(s):
    wl = load_watchlist()
    if s not in wl: return False
    wl.remove(s); save_watchlist(wl); return True
