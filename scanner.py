import aiohttp, asyncio, logging
from memory import detect_dynamic_signals, load_memory
logger = logging.getLogger(__name__)
load_memory()

BINANCE_ENDPOINTS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
]

async def safe_get(session, url):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                return await r.json()
    except Exception as e:
        logger.warning(f"Request failed {url}: {e}")
    return None

async def get_binance_symbols(session):
    for base in BINANCE_ENDPOINTS:
        try:
            data = await safe_get(session, f"{base}/fapi/v1/ticker/24hr")
            if data and isinstance(data, list):
                usdt = [t for t in data if t.get("symbol","").endswith("USDT")]
                usdt.sort(key=lambda x: float(x.get("quoteVolume",0)), reverse=True)
                return [t["symbol"] for t in usdt]
        except Exception as e:
            logger.warning(f"Symbol fetch failed {base}: {e}")
    return []

async def fetch_binance(session, symbol):
    for base in BINANCE_ENDPOINTS:
        try:
            ticker = await safe_get(session, f"{base}/fapi/v1/ticker/24hr?symbol={symbol}")
            if not ticker or float(ticker.get("lastPrice",0)) == 0: continue
            fd  = await safe_get(session, f"{base}/fapi/v1/fundingRate?symbol={symbol}&limit=1") or []
            oi  = await safe_get(session, f"{base}/fapi/v1/openInterest?symbol={symbol}") or {}
            ls  = await safe_get(session, f"{base}/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=1") or []
            pm  = await safe_get(session, f"{base}/fapi/v1/premiumIndex?symbol={symbol}") or {}
            # Get klines for better technical analysis (last 24 candles, 1h)
            klines = await safe_get(session, f"{base}/fapi/v1/klines?symbol={symbol}&interval=1h&limit=24") or []
            price = float(ticker.get("lastPrice",0))
            vol   = float(ticker.get("quoteVolume",0))
            oi_val= float(oi.get("openInterest",0)) * price
            fr    = float(fd[0]["fundingRate"]) * 100 if fd else None
            lsr   = float(ls[0]["longShortRatio"]) if ls else None
            mp    = float(pm.get("markPrice", price))
            ip    = float(pm.get("indexPrice", price))
            basis = ((mp - ip) / ip * 100) if ip > 0 else 0

            # Calculate support/resistance from klines
            support    = min(float(k[3]) for k in klines) if klines else float(ticker.get("lowPrice", price))
            resistance = max(float(k[2]) for k in klines) if klines else float(ticker.get("highPrice", price))
            range_h    = resistance - support

            # Volume confirmation — average volume over last 24 candles
            avg_vol = sum(float(k[7]) for k in klines) / len(klines) if klines else vol

            return {
                "exchange":"Binance","price":price,"volume_24h":vol,
                "open_interest":oi_val,"funding_rate":fr,"ls_ratio":lsr,
                "basis":basis,"price_change_24h":float(ticker.get("priceChangePercent",0)),
                "high_24h":float(ticker.get("highPrice",0)),
                "low_24h":float(ticker.get("lowPrice",0)),
                "support":support,"resistance":resistance,
                "range_height":range_h,"avg_vol_1h":avg_vol,
                "found":price>0
            }
        except Exception as e:
            logger.warning(f"Binance error {base} {symbol}: {e}")
    return {"found":False}

async def fetch_data(symbol):
    async with aiohttp.ClientSession(
        headers={"User-Agent":"Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=30)
    ) as s:
        d = await fetch_binance(s, symbol)
        if d.get("found"): return d
    return {"found":False,"error":f"{symbol} not found on Binance futures"}

def score_static(data):
    s,flags,longs,risks,pump_conds = 0,[],[],[],[]
    fr=data.get("funding_rate"); lsr=data.get("ls_ratio")
    vol=data.get("volume_24h",0); oi=data.get("open_interest",0)
    pc=data.get("price_change_24h",0); bas=data.get("basis",0)
    hi=data.get("high_24h",0); lo=data.get("low_24h",0)
    vm=vol/1_000_000 if vol else 0; om=oi/1_000_000 if oi else 0
    if fr is not None:
        if fr<-0.01: s+=25;flags.append(f"Funding {fr:+.4f}% — strongly negative: max squeeze fuel");longs.append("Negative funding = shorts paying longs every 8h");pump_conds.append("neg_funding")
        elif fr<0: s+=20;flags.append(f"Funding {fr:+.4f}% — negative: shorts dominant");longs.append("Negative funding = hold longs cost-free");pump_conds.append("neg_funding")
        elif fr<=0.005: s+=12;flags.append(f"Funding {fr:+.4f}% — neutral: pre-squeeze setup");longs.append("Near-zero funding = cheap to accumulate long");pump_conds.append("neutral_funding")
        elif fr>0.02: risks.append(f"Funding {fr:+.4f}% — elevated longs: late entry risk")
    if lsr is not None:
        if lsr<0.67: s+=25;flags.append(f"L/S ratio {lsr:.2f} — extremely short: max squeeze target");longs.append("Extreme short crowding = liquidation cascade on any push");pump_conds.append("extreme_shorts")
        elif lsr<0.75: s+=20;flags.append(f"L/S ratio {lsr:.2f} — heavily short: prime squeeze target");longs.append("Heavy shorts = forced buying amplifies upward move");pump_conds.append("heavy_shorts")
        elif lsr<0.9: s+=10;flags.append(f"L/S ratio {lsr:.2f} — shorts building");pump_conds.append("shorts_building")
        elif lsr>1.8: risks.append(f"L/S ratio {lsr:.2f} — crowded longs: dump risk")
    if vol>0 and oi>0:
        ratio=oi/vol
        if ratio>3: s+=20;flags.append(f"Thin order book: OI ${om:.1f}M vs vol ${vm:.1f}M");longs.append("High OI on low volume = smart money positioning quietly");pump_conds.append("high_oi_low_vol")
        elif ratio>2: s+=15;flags.append(f"OI/Volume {ratio:.1f}x — stealth accumulation");longs.append("OI growing while volume stays low");pump_conds.append("oi_building")
        elif ratio>1: s+=8;flags.append(f"OI/Volume {ratio:.1f}x — moderate accumulation")
    if vm>0:
        if vm<3: s+=20;flags.append(f"Low volume coiling: ${vm:.1f}M — extreme dormancy, pre-pump pattern");longs.append("Extreme dormancy = compressed spring");pump_conds.append("extreme_dormancy")
        elif vm<10: s+=15;flags.append(f"Low volume coiling: ${vm:.1f}M — classic pre-pump dormancy");longs.append("Low volume + flat price = you're early");pump_conds.append("low_vol_coil")
        elif vm<30: s+=8;flags.append(f"Below average volume ${vm:.1f}M")
    if hi>0 and lo>0:
        rng=((hi-lo)/lo)*100
        if rng<3 and vm<10: s+=15;flags.append(f"Price coiling: {rng:.1f}% range — tight consolidation");longs.append("Tight range + low volume = pre-breakout coil");pump_conds.append("tight_coil")
        elif rng<5: s+=8;flags.append(f"Moderate coiling: {rng:.1f}% 24h range")
    if abs(bas)>0.05:
        if bas<-0.2: s+=12;flags.append(f"Basis {bas:+.3f}% — futures below spot: shorts overextended");longs.append("Negative basis = shorts overextended");pump_conds.append("neg_basis")
        elif bas>0.5: risks.append(f"Basis {bas:+.3f}% — futures premium: longs overheating")
    if abs(pc)<2 and vm<10: s+=10;flags.append(f"Price flat {pc:+.1f}% on low volume — pump hasn't started: early entry window");longs.append("Flat price = you're early, pump hasn't happened yet");pump_conds.append("flat_price")
    elif pc>20: risks.append(f"Price already up {pc:+.1f}% — possible late entry")
    pump=len(pump_conds)>=4
    if pump: s+=15;flags.append(f"ALL SIGNALS ALIGN ({len(pump_conds)}/7): {', '.join(pump_conds)}");longs.append("ENTER LONG NOW: all pre-pump conditions confirmed")
    return min(s,100),flags,longs,risks,pump

def technical_long_setup(data, crime_score):
    """
    Support bounce entry with volume confirmation.
    Enter at support, stop below support, targets at resistance and measured moves.
    """
    price      = data.get("price", 0)
    support    = data.get("support", 0)
    resistance = data.get("resistance", 0)
    range_h    = data.get("range_height", 0)
    avg_vol    = data.get("avg_vol_1h", 0)
    cur_vol    = data.get("volume_24h", 0)
    lo         = data.get("low_24h", 0)

    if not price or not support or not resistance or range_h <= 0:
        return None

    # Entry: bounce off support with 0.5% buffer above support
    entry = support * 1.005

    # If price is already above entry significantly, adjust
    # Don't chase — only enter if price is near support
    distance_from_support = ((price - support) / support * 100) if support > 0 else 0
    if distance_from_support > 5:
        # Price has moved away from support — use current price as entry
        entry = price

    # Stop: 2% below support (below the consolidation floor)
    stop = support * 0.98

    # Targets based on measured move from support to resistance
    t1 = resistance                          # top of range — take 40%
    t2 = resistance + (range_h * 1.0)       # measured move above range — take 40%
    t3 = resistance + (range_h * 2.0)       # extended target — let 20% ride

    # Risk and R:R
    risk_pct = ((entry - stop) / entry * 100) if entry > stop else 0
    rr       = ((t1 - entry) / (entry - stop)) if entry > stop else 0

    # Volume confirmation
    vol_confirm = cur_vol > avg_vol * 0.8  # current volume at least 80% of average

    # Confidence based on crime score and setup quality
    if crime_score >= 80 and rr >= 2:
        conf = "HIGH"
    elif crime_score >= 75 and rr >= 1.5:
        conf = "MODERATE"
    else:
        conf = "LOW"

    return {
        "entry": entry,
        "stop": stop,
        "t1": t1,
        "t2": t2,
        "t3": t3,
        "risk": risk_pct,
        "rr": rr,
        "conf": conf,
        "support": support,
        "resistance": resistance,
        "range_height": range_h,
        "vol_confirm": vol_confirm,
        "distance_from_support": distance_from_support,
    }

async def scan_token(symbol):
    data = await fetch_data(symbol)
    if not data.get("found"):
        return {"symbol":symbol,"error":data.get("error","Could not fetch data"),"crime_score":0,"pump_signal":False,"dynamic_alert":False}
    static_score,flags,longs,risks,pump = score_static(data)
    dynamic_flags,dynamic_score,is_dynamic = detect_dynamic_signals(symbol, data)
    total_score = min(static_score+dynamic_score, 100)
    all_flags   = flags + dynamic_flags
    setup       = technical_long_setup(data, total_score)
    def fm(v): return f"${v/1e6:.1f}M" if v and v>=1e6 else (f"${v/1e3:.1f}K" if v and v>=1e3 else "N/A")
    def fp(v):
        if not v: return "N/A"
        if v<0.0001: return f"${v:.8f}"
        if v<0.01: return f"${v:.6f}"
        return f"${v:.4f}"
    return {
        "symbol":symbol,"exchange":data.get("exchange","Binance"),
        "price":fp(data.get("price")),"price_change":f"{data.get('price_change_24h',0):+.2f}%",
        "volume_24h":fm(data.get("volume_24h")),"open_interest":fm(data.get("open_interest")),
        "funding_rate":f"{data.get('funding_rate',0):+.4f}% per 8h" if data.get("funding_rate") is not None else "N/A",
        "ls_ratio":f"{data.get('ls_ratio',0):.2f}" if data.get("ls_ratio") else "N/A",
        "basis":f"{data.get('basis',0):+.3f}%","crime_score":total_score,
        "static_score":static_score,"dynamic_score":dynamic_score,
        "flags":all_flags,"long_signals":longs,"risk_signals":risks,
        "pump_signal":pump,"dynamic_alert":is_dynamic,"long_setup":setup,"raw":data
    }
