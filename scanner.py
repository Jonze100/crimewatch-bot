import aiohttp, asyncio, logging, json, os, time
from memory import detect_dynamic_signals, load_memory
from alpha_tokens import ALPHA_TOKENS
logger = logging.getLogger(__name__)
load_memory()

SYMBOLS_CACHE_FILE = "binance_symbols.json"
SYMBOLS_CACHE_TTL  = 86400  # 24 hours

ALL_BINANCE_FUTURES = [
    # Mega cap
    "BTCUSDT",  "ETHUSDT",  "BNBUSDT",  "SOLUSDT",   "XRPUSDT",
    "ADAUSDT",  "DOGEUSDT", "AVAXUSDT", "TRXUSDT",   "DOTUSDT",
    "LINKUSDT", "MATICUSDT","LTCUSDT",  "BCHUSDT",   "ATOMUSDT",
    # Large cap
    "UNIUSDT",  "NEARUSDT", "APTUSDT",  "OPUSDT",    "ARBUSDT",
    "SUIUSDT",  "INJUSDT",  "TIAUSDT",  "FILUSDT",   "ICPUSDT",
    "STXUSDT",  "RUNEUSDT", "AAVEUSDT", "MKRUSDT",   "SNXUSDT",
    "LDOUSDT",  "CRVUSDT",  "COMPUSDT", "GRTUSDT",   "IMXUSDT",
    "SEIUSDT",  "MNTUSDT",
    # Established L1 / alt chains
    "KAVAUSDT", "BANDUSDT", "FLOWUSDT", "HBARUSDT",  "VETUSDT",
    "ALGOUSDT", "EGLDUSDT", "THETAUSDT","IOTXUSDT",  "ICXUSDT",
    "ZRXUSDT",  "BATUSDT",  "ZILUSDT",  "ONTUSDT",   "QTUMUSDT",
    "IOTAUSDT", "WAVESUSDT","RVNUSDT",  "SKLUSDT",   "NKNUSDT",
    "COTIUSDT", "SXPUSDT",
    # DeFi protocols
    "DYDXUSDT", "GMXUSDT",  "PENDLEUSDT","RDNTUSDT", "WOOUSDT",
    "1INCHUSDT","CAKEUSDT", "SUSHIUSDT","BALUSDT",   "KNCUSDT",
    "ENAUSDT",  "PERPUSDT",
    # Gaming / metaverse
    "SANDUSDT", "AXSUSDT",  "MANAUSDT", "GALAUSDT",  "CHZUSDT",
    "ENJUSDT",  "YGGUSDT",  "MAGICUSDT","ILVUSDT",   "ALICEUSDT",
    "VOXELUSDT","TLMUSDT",
    # New L2 / ZK / modular chains (2023-2025)
    "STRKUSDT", "ZKUSDT",   "MANTAUSDT","BLASTUSDT", "SCRUSDT",
    "WUSDT",    "ZROUSDT",  "AEVOUSDT", "ETHFIUSDT", "REZUSDT",
    "BBUSDT",   "IOUSDT",   "LISTAUSDT","GLMRUSDT",
    # Solana ecosystem
    "JUPUSDT",  "BONKUSDT", "WIFUSDT",  "BOMEUSDT",  "JITOUSDT",
    "PYTHUSDT", "RAYUSDT",
    # AI / DePIN / compute
    "RENDERUSDT","FETUSDT", "WLDUSDT",  "AGIXUSDT",  "OCEANUSDT",
    "ARKMUSDT", "EIGENUSDT","ALTUSDT",  "GRASSUSDT", "TAOUSDT",
    # TON / messaging ecosystem
    "TONUSDT",  "NOTUSDT",  "DOGSUSDT", "HMSTRUSDT", "CATIUSDT",
    # Mid-cap established
    "APEUSDT",  "GMTUSDT",  "BLURUSDT", "MASKUSDT",  "SUPERUSDT",
    "REEFUSDT", "SFPUSDT",  "DUSKUSDT", "ROSEUSDT",  "KLAYUSDT",
    "CFXUSDT",  "HIGHUSDT", "ACHUSDT",  "JASMYUSDT", "HOOKUSDT",
    "PEOPLEUSDT","LUNCUSDT","CYBERUSDT","ARKUSDT",   "ACEUSDT",
    "NFPUSDT",  "PIXELUSDT","AIUSDT",   "XAIUSDT",   "CVCUSDT",
    "POWRUSDT", "OMUSDT",   "SUNUSDT",
    # BNB chain native
    "BAKEUSDT", "BNXUSDT",  "CTKUSDT",  "ALPHAUSDT", "BETAUSDT",
    "LINAUSDT", "DEGOUSDT",
    # Sports / fan tokens
    "PSGUSDT",  "BARUSDT",  "CITYUSDT", "SANTOSUSDT","LAZIOUSDT",
    "JUVUSDT",  "ACMUSDT",  "OGUSDT",   "PORTOUSDT",
    # Binance Alpha & notable 2024-2025
    "VANAUSDT",     "KAIAUSDT",    "BERAUSDT",    "SONICUSDT",
    "ZETAUSDT",     "SOONUSDT",    "IRYSUSDT",    "PEAQUSDT",
    "SQDUSDT",      "CARVUSDT",    "ZORAUSDT",    "MAGMAUSDT",
    "MERLUSDT",     "MOVEUSDT",    "MEUSDT",      "VIRTUALUSDT",
    "POPCATUSDT",   "MOODENGUSDT", "MOGUSDT",     "MEWUSDT",
    "PLAYERUSDT",   "FARTCOINUSDT","SPXUSDT",     "PIPUSDT",
    "ACTUSDT",      "GRIFFAINUSDT","COOKIEUSDT",  "AI16ZUSDT",
    "AIXBTUSDT",    "TAIUSDT",     "CGPTUSDT",    "GPTUSDT",
    "GOODAIUSDT",   "ARCUSDT",     "PIPPINUSDT",  "ZEREBRUSDT",
    "NOUSDT",       "PROMPTUSDT",  "SENTIENTUSDT","NEIROUSDT",
    "BANANAUSDT",   "B3USDT",      "DOODUSDT",    "ALCHUSDT",
    "SAFEUSDT",     "NAORIUSDT",   "CROSSUSDT",   "MYXUSDT",
    "BIRBUSDT",     "ALEOUSDT",    "VELOUSDT",    "KGENUSDT",
    "COAIUSDT",     "TOSHIUSDT",   "FLUIDUSDT",
]

BINANCE_ENDPOINTS = [
    "https://fapi.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
]
BINANCE_SPOT    = "https://api.binance.com/api/v3"
COINGECKO_PERPS = "https://api.coingecko.com/api/v3/derivatives/exchanges/binance_futures"
BITUNIX = "https://fapi.bitunix.com"

async def safe_get(session, url, retries=1):
    """GET with one retry on transient network errors (3s → 6s backoff).
    Returns None immediately on 4xx/5xx — no point retrying a geo-block."""
    delay = 3
    for attempt in range(retries + 1):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    return await r.json()
                if r.status == 429 and attempt < retries:
                    logger.warning(f"Rate limited {url}, retrying in {delay}s")
                    await asyncio.sleep(delay)
                    delay *= 2
                    continue
                return None
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError,
                aiohttp.ServerDisconnectedError) as e:
            if attempt < retries:
                logger.warning(f"Transient error {url} (attempt {attempt+1}), retrying in {delay}s: {e}")
                await asyncio.sleep(delay)
                delay *= 2
            else:
                logger.warning(f"Request failed {url}: {e}")
        except Exception as e:
            logger.warning(f"Request error {url}: {e}")
            return None
    return None

def _save_cache(symbols):
    try:
        with open(SYMBOLS_CACHE_FILE, "w") as f:
            json.dump({"ts": time.time(), "symbols": symbols}, f)
        logger.info(f"Saved {len(symbols)} symbols to {SYMBOLS_CACHE_FILE}")
    except Exception as e:
        logger.warning(f"Cache write failed: {e}")

async def get_binance_symbols():
    # 1. Cache hit — skip all network calls for 24h
    if os.path.exists(SYMBOLS_CACHE_FILE):
        try:
            with open(SYMBOLS_CACHE_FILE) as f:
                cached = json.load(f)
            if time.time() - cached.get("ts", 0) < SYMBOLS_CACHE_TTL:
                symbols = cached.get("symbols", [])
                if symbols:
                    logger.info(f"Loaded {len(symbols)} symbols from cache")
                    return symbols
        except Exception as e:
            logger.warning(f"Cache read failed: {e}")

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        # 2. Binance fapi — fast, works locally; geo-blocked on some hosting
        for base in BINANCE_ENDPOINTS:
            data = await safe_get(session, f"{base}/fapi/v1/ticker/24hr")
            if data and isinstance(data, list) and len(data) > 50:
                usdt = [t for t in data if t.get("symbol", "").endswith("USDT")]
                usdt.sort(key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
                symbols = [t["symbol"] for t in usdt]
                logger.info(f"Binance fapi ({base}) returned {len(symbols)} symbols")
                _save_cache(symbols)
                return symbols

        # 3. CoinGecko include_tickers=all — bypasses Binance geo-block
        logger.warning("Binance fapi unavailable, trying CoinGecko (include_tickers=all)...")
        data = await safe_get(session, f"{COINGECKO_PERPS}?include_tickers=all")
        if data and isinstance(data, dict):
            tickers = data.get("tickers", [])
            seen, symbols = set(), []
            for t in tickers:
                base_coin = t.get("base", "")
                target    = t.get("target", "")
                if target != "USDT" or not base_coin:
                    continue
                sym = base_coin.upper() + "USDT"
                if sym not in seen:
                    seen.add(sym)
                    symbols.append(sym)
            if symbols:
                logger.info(f"CoinGecko returned {len(symbols)} symbols")
                _save_cache(symbols)
                return symbols
            logger.warning("CoinGecko responded but had 0 USDT tickers")

    # 4. Hardcoded fallback — 200+ known Binance futures tokens, never < 32
    logger.error("All live sources failed — using ALL_BINANCE_FUTURES hardcoded list")
    return list(ALL_BINANCE_FUTURES)

async def fetch_binance(session, symbol):
    for base in BINANCE_ENDPOINTS:
        try:
            ticker = await safe_get(session, f"{base}/fapi/v1/ticker/24hr?symbol={symbol}")
            if not ticker or float(ticker.get("lastPrice",0)) == 0: continue
            fd = await safe_get(session, f"{base}/fapi/v1/fundingRate?symbol={symbol}&limit=1") or []
            oi = await safe_get(session, f"{base}/fapi/v1/openInterest?symbol={symbol}") or {}
            ls = await safe_get(session, f"{base}/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=1") or []
            pm = await safe_get(session, f"{base}/fapi/v1/premiumIndex?symbol={symbol}") or {}
            price = float(ticker.get("lastPrice",0))
            vol   = float(ticker.get("quoteVolume",0))
            oi_val= float(oi.get("openInterest",0)) * price
            fr    = float(fd[0]["fundingRate"]) * 100 if fd else None
            lsr   = float(ls[0]["longShortRatio"]) if ls else None
            mp    = float(pm.get("markPrice", price))
            ip    = float(pm.get("indexPrice", price))
            basis = ((mp - ip) / ip * 100) if ip > 0 else 0
            return {"exchange":"Binance","price":price,"volume_24h":vol,
                    "open_interest":oi_val,"funding_rate":fr,"ls_ratio":lsr,"basis":basis,
                    "price_change_24h":float(ticker.get("priceChangePercent",0)),
                    "high_24h":float(ticker.get("highPrice",0)),
                    "low_24h":float(ticker.get("lowPrice",0)),"found":True}
        except Exception as e:
            logger.warning(f"Binance error {base} {symbol}: {e}")
    # Last resort: spot API — no futures data (funding/OI/LS unavailable)
    try:
        ticker = await safe_get(session, f"{BINANCE_SPOT}/ticker/24hr?symbol={symbol}")
        if ticker and float(ticker.get("lastPrice", 0)) > 0:
            price = float(ticker["lastPrice"])
            logger.warning(f"Using spot API fallback for {symbol} (no futures data)")
            return {"exchange":"Binance-Spot","price":price,
                    "volume_24h":float(ticker.get("quoteVolume",0)),
                    "open_interest":0,"funding_rate":None,"ls_ratio":None,"basis":0,
                    "price_change_24h":float(ticker.get("priceChangePercent",0)),
                    "high_24h":float(ticker.get("highPrice",0)),
                    "low_24h":float(ticker.get("lowPrice",0)),"found":True}
    except Exception as e:
        logger.warning(f"Spot API fallback failed {symbol}: {e}")
    return {"found":False}

async def fetch_bitunix(session, symbol):
    try:
        td = await safe_get(session, f"{BITUNIX}/api/v1/futures/market/tickers?symbols={symbol}")
        if not td: return {"found":False}
        items = td.get("data", [])
        if not items: return {"found":False}
        t = items[0]
        price = float(t.get("lastPrice") or t.get("last") or 0)
        if not price: return {"found":False}
        vol  = float(t.get("quoteVol") or 0)
        hi   = float(t.get("high") or 0)
        lo   = float(t.get("low") or 0)
        op   = float(t.get("open") or price)
        pc   = ((price - op) / op * 100) if op else 0
        mp   = float(t.get("markPrice") or price)
        basis = ((mp - price) / price * 100) if price else 0
        fr, oi_val = None, 0
        try:
            fd = await safe_get(session, f"{BITUNIX}/api/v1/futures/market/funding_rate?symbol={symbol}")
            if fd:
                fdl = fd.get("data", [])
                if fdl: fr = float(fdl[0].get("fundingRate") or 0) * 100
        except: pass
        try:
            oid = await safe_get(session, f"{BITUNIX}/api/v1/futures/market/open-interest?symbol={symbol}")
            if oid: oi_val = float(oid.get("data", {}).get("openInterest") or 0) * price
        except: pass
        return {"exchange":"Bitunix","price":price,"volume_24h":vol,
                "open_interest":oi_val,"funding_rate":fr,"ls_ratio":None,"basis":basis,
                "price_change_24h":pc,"high_24h":hi,"low_24h":lo,"found":True}
    except Exception as e:
        logger.warning(f"Bitunix error {symbol}: {e}")
    return {"found":False}

async def fetch_data(symbol):
    async with aiohttp.ClientSession(
        headers={"User-Agent":"Mozilla/5.0"},
        timeout=aiohttp.ClientTimeout(total=30)
    ) as s:
        d = await fetch_binance(s, symbol)
        if d.get("found"): return d
        d = await fetch_bitunix(s, symbol)
        if d.get("found"): return d
    return {"found":False,"error":f"{symbol} not found on Binance or Bitunix"}

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
        if ratio>3: s+=20;flags.append(f"Thin order book: OI ${om:.1f}M vs vol ${vm:.1f}M — small capital moves price significantly");longs.append("High OI on low volume = smart money positioning quietly");pump_conds.append("high_oi_low_vol")
        elif ratio>2: s+=15;flags.append(f"OI/Volume {ratio:.1f}x — stealth accumulation");longs.append("OI growing while volume stays low");pump_conds.append("oi_building")
        elif ratio>1: s+=8;flags.append(f"OI/Volume {ratio:.1f}x — moderate accumulation")
    if vm>0:
        if vm<3: s+=20;flags.append(f"Low volume coiling: ${vm:.1f}M — extreme dormancy, classic pre-pump dormancy pattern");longs.append("Extreme dormancy = compressed spring");pump_conds.append("extreme_dormancy")
        elif vm<10: s+=15;flags.append(f"Low volume coiling: ${vm:.1f}M — classic pre-pump dormancy");longs.append("Low volume + flat price = you're early");pump_conds.append("low_vol_coil")
        elif vm<30: s+=8;flags.append(f"Below average volume ${vm:.1f}M")
    if hi>0 and lo>0:
        rng=((hi-lo)/lo)*100
        if rng<3 and vm<10: s+=15;flags.append(f"Price coiling: {rng:.1f}% range — tight consolidation");longs.append("Tight range + low volume = pre-breakout coil");pump_conds.append("tight_coil")
        elif rng<5: s+=8;flags.append(f"Moderate coiling: {rng:.1f}% 24h range")
    if abs(bas)>0.05:
        if bas<-0.2: s+=12;flags.append(f"Basis {bas:+.3f}% — futures below spot: shorts overextended");longs.append("Negative basis = shorts overextended");pump_conds.append("neg_basis")
        elif bas>0.5: risks.append(f"Basis {bas:+.3f}% — futures premium: longs overheating")
    if abs(pc)<2 and vm<10: s+=10;flags.append(f"Price flat {pc:+.1f}% on low volume — pump hasn't started");longs.append("Flat price = you're early");pump_conds.append("flat_price")
    elif pc>20: risks.append(f"Price already up {pc:+.1f}% — possible late entry")
    pump=len(pump_conds)>=4
    if pump: s+=15;flags.append(f"ALL SIGNALS ALIGN ({len(pump_conds)}/7): {', '.join(pump_conds)}");longs.append("ENTER LONG NOW: all pre-pump conditions confirmed")
    return min(s,100),flags,longs,risks,pump

async def scan_token(symbol: str):
    symbol = symbol.upper().strip()
    if not symbol.endswith("USDT"):
        symbol += "USDT"

    data = await fetch_data(symbol)
    if not data.get("found"):
        return {"error": data.get("error", f"{symbol} not found"), "symbol": symbol}

    # score_static and detect_dynamic_signals both read from the raw data dict
    static_score, flags, long_signals, risk_signals, pump = score_static(data)
    dyn_flags, dyn_score, is_dynamic = detect_dynamic_signals(symbol, data)

    all_flags   = flags + dyn_flags
    crime_score = min(static_score + dyn_score, 100)

    price = data.get("price", 0)
    vol   = data.get("volume_24h", 0)
    oi    = data.get("open_interest", 0)
    fr    = data.get("funding_rate")
    lsr   = data.get("ls_ratio")
    basis = data.get("basis", 0)
    pc    = data.get("price_change_24h", 0)
    vm    = vol / 1_000_000 if vol else 0
    om    = oi  / 1_000_000 if oi  else 0

    if price <= 0:
        price_str = "N/A"
    elif price >= 1:
        price_str = f"${price:.4f}"
    elif price >= 0.01:
        price_str = f"${price:.6f}"
    else:
        price_str = f"${price:.8f}"

    return {
        "symbol":        symbol,
        "exchange":      data.get("exchange", "Unknown"),
        "price":         price_str,
        "price_change":  f"{pc:+.2f}%",
        "volume_24h":    f"${vm:.2f}M",
        "open_interest": f"${om:.2f}M",
        "funding_rate":  f"{fr:+.4f}%" if fr is not None else "N/A",
        "ls_ratio":      f"{lsr:.2f}"  if lsr is not None else "N/A",
        "basis":         f"{basis:+.3f}%",
        "crime_score":   crime_score,
        "static_score":  static_score,
        "dynamic_score": dyn_score,
        "flags":         all_flags,
        "long_signals":  long_signals,
        "risk_signals":  risk_signals,
        "pump_signal":   pump,
        "dynamic_alert": is_dynamic,
        "is_alpha":      symbol in ALPHA_TOKENS,
        "raw": {
            "funding_rate":     fr,
            "ls_ratio":         lsr,
            "volume_24h":       vol,
            "open_interest":    oi,
            "price_change_24h": pc,
            "price":            price,
        }
    }
