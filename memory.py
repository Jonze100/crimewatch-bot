import json, os, time, logging
logger = logging.getLogger(__name__)
MEMORY_FILE = "scan_memory.json"
_memory = {}

def load_memory():
    global _memory
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE) as f: _memory = json.load(f)
        except Exception as e: logger.warning(f"Memory load error: {e}"); _memory = {}
    return _memory

def save_memory():
    try:
        with open(MEMORY_FILE, "w") as f: json.dump(_memory, f)
    except Exception as e: logger.warning(f"Memory save error: {e}")

def get_previous(symbol): return _memory.get(symbol)

def store_snapshot(symbol, data):
    _memory[symbol] = {"timestamp": time.time(), "price": data.get("price",0),
        "volume_24h": data.get("volume_24h",0), "open_interest": data.get("open_interest",0),
        "funding_rate": data.get("funding_rate"), "ls_ratio": data.get("ls_ratio"),
        "price_change_24h": data.get("price_change_24h",0)}
    save_memory()

def detect_dynamic_signals(symbol, current_data):
    prev = get_previous(symbol)
    flags, score, is_dynamic = [], 0, False
    if not prev:
        store_snapshot(symbol, current_data); return flags, score, is_dynamic
    minutes = (time.time() - prev.get("timestamp",0)) / 60
    cur_oi=current_data.get("open_interest",0); prev_oi=prev.get("open_interest",0)
    cur_vol=current_data.get("volume_24h",0); prev_vol=prev.get("volume_24h",0)
    cur_fr=current_data.get("funding_rate"); prev_fr=prev.get("funding_rate")
    cur_lsr=current_data.get("ls_ratio"); prev_lsr=prev.get("ls_ratio")
    cur_price=current_data.get("price",0); prev_price=prev.get("price",0)

    if prev_oi > 0 and cur_oi > 0:
        oi_chg = ((cur_oi - prev_oi) / prev_oi) * 100
        if oi_chg >= 30:
            score+=25; flags.append(f"🔺 OI SPIKE: +{oi_chg:.1f}% in {minutes:.0f} mins — massive position building RIGHT NOW"); is_dynamic=True
        elif oi_chg >= 20:
            score+=18; flags.append(f"🔺 OI spike: +{oi_chg:.1f}% in {minutes:.0f} mins — large position building quietly"); is_dynamic=True
        elif oi_chg >= 10:
            score+=10; flags.append(f"OI increasing: +{oi_chg:.1f}% since last scan")

    if cur_fr is not None and prev_fr is not None:
        if prev_fr > 0.005 and cur_fr <= 0:
            score+=30; flags.append(f"🔄 FUNDING FLIP: +{prev_fr:.4f}% → {cur_fr:.4f}% — shorts just took over, squeeze fuel loading"); is_dynamic=True
        elif prev_fr >= 0 and cur_fr < -0.005:
            score+=25; flags.append(f"🔄 FUNDING FLIP: rate went negative ({cur_fr:.4f}%) — shorts dominant"); is_dynamic=True
        elif cur_fr < prev_fr - 0.005:
            score+=15; flags.append(f"📉 Funding dropping: {prev_fr:.4f}% → {cur_fr:.4f}% — shorts increasing pressure")

    if prev_vol > 0 and cur_vol > 0:
        vol_chg = ((cur_vol - prev_vol) / prev_vol) * 100
        if vol_chg >= 500:
            score+=25; flags.append(f"🔥 VOLUME EXPLOSION: +{vol_chg:.0f}% — something happening RIGHT NOW"); is_dynamic=True
        elif vol_chg >= 200:
            score+=18; flags.append(f"🔥 Volume spike: +{vol_chg:.0f}% — sudden surge, watch closely"); is_dynamic=True
        elif vol_chg >= 100:
            score+=10; flags.append(f"Volume surging: +{vol_chg:.0f}% since last scan")

    if cur_lsr is not None and prev_lsr is not None:
        lsr_drop = prev_lsr - cur_lsr
        if lsr_drop >= 0.15:
            score+=20; flags.append(f"📉 SHORTS PILING IN: L/S {prev_lsr:.2f} → {cur_lsr:.2f} — rapid short accumulation, squeeze building fast"); is_dynamic=True
        elif lsr_drop >= 0.08:
            score+=12; flags.append(f"L/S dropping fast: {prev_lsr:.2f} → {cur_lsr:.2f} — shorts accelerating")
        elif lsr_drop >= 0.04:
            score+=6; flags.append(f"L/S declining: {prev_lsr:.2f} → {cur_lsr:.2f}")

    if prev_price > 0 and cur_price > 0:
        price_chg = abs((cur_price - prev_price) / prev_price) * 100
        oi_up  = cur_oi > prev_oi * 1.1 if prev_oi > 0 else False
        vol_up = cur_vol > prev_vol * 1.5 if prev_vol > 0 else False
        if price_chg < 1 and oi_up and vol_up:
            score+=20; flags.append(f"⚡ PERFECT COIL: price flat ({price_chg:.2f}%) but OI + volume both spiking — spring loading"); is_dynamic=True

    store_snapshot(symbol, current_data)
    return flags, score, is_dynamic
