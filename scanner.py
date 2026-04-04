import aiohttp, logging
logger = logging.getLogger(__name__)
BINANCE = "https://fapi.binance.com"
BITUNIX = "https://fapi.bitunix.com"

async def get_binance_symbols(session):
    try:
        async with session.get(f"{BINANCE}/fapi/v1/ticker/24hr") as r:
            data = await r.json() if r.status == 200 else []
        usdt = [t for t in data if t.get("symbol","").endswith("USDT")]
        usdt.sort(key=lambda x: float(x.get("quoteVolume",0)), reverse=True)
        return [t["symbol"] for t in usdt[:60]]
    except Exception as e:
        logger.warning(f"Binance symbol fetch error: {e}"); return []

async def get_bitunix_symbols(session):
    try:
        async with session.get(f"{BITUNIX}/api/v1/futures/market/tickers") as r:
            data = await r.json() if r.status == 200 else {}
        items = data.get("data", [])
        usdt = [t for t in items if t.get("symbol","").endswith("USDT")]
        usdt.sort(key=lambda x: float(x.get("quoteVol") or 0), reverse=True)
        return [("bitunix", t) for t in usdt[:60]]
    except Exception as e:
        logger.warning(f"Bitunix symbol fetch error: {e}"); return []

async def fetch_binance(session, symbol):
    try:
        async with session.get(f"{BINANCE}/fapi/v1/ticker/24hr?symbol={symbol}") as r:
            ticker = await r.json() if r.status == 200 else {}
        if not ticker or float(ticker.get("lastPrice", 0)) == 0:
            return {"found": False}
        async with session.get(f"{BINANCE}/fapi/v1/fundingRate?symbol={symbol}&limit=1") as r:
            fd = await r.json() if r.status == 200 else []
        async with session.get(f"{BINANCE}/fapi/v1/openInterest?symbol={symbol}") as r:
            oi = await r.json() if r.status == 200 else {}
        async with session.get(f"{BINANCE}/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=1h&limit=1") as r:
            ls = await r.json() if r.status == 200 else []
        async with session.get(f"{BINANCE}/fapi/v1/premiumIndex?symbol={symbol}") as r:
            pm = await r.json() if r.status == 200 else {}
        price = float(ticker.get("lastPrice", 0))
        vol   = float(ticker.get("quoteVolume", 0))
        oi_val= float(oi.get("openInterest", 0)) * price
        fr    = float(fd[0]["fundingRate"]) * 100 if fd else None
        lsr   = float(ls[0]["longShortRatio"]) if ls else None
        mp    = float(pm.get("markPrice", price))
        ip    = float(pm.get("indexPrice", price))
        basis = ((mp - ip) / ip * 100) if ip > 0 else 0
        return {"exchange":"Binance","price":price,"volume_24h":vol,"open_interest":oi_val,
                "funding_rate":fr,"ls_ratio":lsr,"basis":basis,
                "price_change_24h":float(ticker.get("priceChangePercent",0)),
                "high_24h":float(ticker.get("highPrice",0)),
                "low_24h":float(ticker.get("lowPrice",0)),"found":price>0}
    except Exception as e:
        logger.warning(f"Binance error {symbol}: {e}"); return {"found":False}

async def fetch_bitunix_ticker(session, ticker_data):
    try:
        symbol = ticker_data.get("symbol")
        price  = float(ticker_data.get("lastPrice") or ticker_data.get("last") or 0)
        if not price: return {"found": False}
        vol  = float(ticker_data.get("quoteVol") or 0)
        hi   = float(ticker_data.get("high") or 0)
        lo   = float(ticker_data.get("low") or 0)
        op   = float(ticker_data.get("open") or price)
        pc   = ((price - op) / op * 100) if op else 0
        mp   = float(ticker_data.get("markPrice") or price)
        basis = ((mp - price) / price * 100) if price else 0
        fr = None
        try:
            async with session.get(f"{BITUNIX}/api/v1/futures/market/funding_rate?symbol={symbol}") as r:
                fd = await r.json() if r.status == 200 else {}
            fd_list = fd.get("data", [])
            if fd_list: fr = float(fd_list[0].get("fundingRate") or 0) * 100
        except: pass
        return {"exchange":"Bitunix","price":price,"volume_24h":vol,"open_interest":0,
                "funding_rate":fr,"ls_ratio":None,"basis":basis,
                "price_change_24h":pc,"high_24h":hi,"low_24h":lo,"found":True}
    except Exception as e:
        logger.warning(f"Bitunix ticker error: {e}"); return {"found":False}

async def fetch_data(symbol):
    async with aiohttp.ClientSession(
        headers={"User-Agent":"CrimeWatch/1.0"},
        timeout=aiohttp.ClientTimeout(total=15)
    ) as s:
        d = await fetch_binance(s, symbol)
        if d.get("found"): return d
        try:
            async with s.get(f"{BITUNIX}/api/v1/futures/market/tickers?symbols={symbol}") as r:
                td = await r.json() if r.status == 200 else {}
            items = td.get("data", [])
            if items:
                d = await fetch_bitunix_ticker(s, items[0])
                if d.get("found"): return d
        except: pass
    return {"found":False,"error":f"{symbol} not found on Binance or Bitunix futures"}

async def discover_all_tokens():
    results = []
    async with aiohttp.ClientSession(
        headers={"User-Agent":"CrimeWatch/1.0"},
        timeout=aiohttp.ClientTimeout(total=20)
    ) as session:
        binance_symbols = await get_binance_symbols(session)
        for sym in binance_symbols:
            results.append(("binance", sym))
        bitunix_tickers = await get_bitunix_symbols(session)
        seen = set(s for _, s in results)
        for _, t in bitunix_tickers:
            sym = t.get("symbol","")
            if sym and sym not in seen:
                results.append(("bitunix_prefetched", t))
    return results

def score(data):
    s, flags, longs, risks, pump_conds = 0, [], [], [], []
    fr  = data.get("funding_rate")
    lsr = data.get("ls_ratio")
    vol = data.get("volume_24h", 0)
    oi  = data.get("open_interest", 0)
    pc  = data.get("price_change_24h", 0)
    bas = data.get("basis", 0)
    hi  = data.get("high_24h", 0)
    lo  = data.get("low_24h", 0)
    vm  = vol / 1_000_000 if vol else 0
    om  = oi / 1_000_000 if oi else 0

    if fr is not None:
        if fr < -0.01:
            s+=25; flags.append(f"Funding {fr:+.4f}% — strongly negative: max squeeze fuel")
            longs.append("Negative funding = shorts paying longs every 8h"); pump_conds.append("neg_funding")
        elif fr < 0:
            s+=20; flags.append(f"Funding {fr:+.4f}% — negative: shorts dominant")
            longs.append("Negative funding = hold longs cost-free"); pump_conds.append("neg_funding")
        elif fr <= 0.005:
            s+=12; flags.append(f"Funding {fr:+.4f}% — neutral: pre-squeeze setup")
            longs.append("Near-zero funding = cheap to accumulate long"); pump_conds.append("neutral_funding")
        elif fr > 0.02:
            risks.append(f"Funding {fr:+.4f}% — elevated longs: late entry risk")

    if lsr is not None:
        if lsr < 0.67:
            s+=25; flags.append(f"L/S ratio {lsr:.2f} — extremely short: max squeeze target")
            longs.append("Extreme short crowding = liquidation cascade on any push"); pump_conds.append("extreme_shorts")
        elif lsr < 0.75:
            s+=20; flags.append(f"L/S ratio {lsr:.2f} — heavily short: prime squeeze target")
            longs.append("Heavy shorts = forced buying amplifies upward move"); pump_conds.append("heavy_shorts")
        elif lsr < 0.9:
            s+=10; flags.append(f"L/S ratio {lsr:.2f} — shorts building"); pump_conds.append("shorts_building")
        elif lsr > 1.8:
            risks.append(f"L/S ratio {lsr:.2f} — crowded longs: dump risk")

    if vol > 0 and oi > 0:
        ratio = oi / vol
        if ratio > 3:
            s+=20; flags.append(f"Thin order book: OI ${om:.1f}M vs vol ${vm:.1f}M")
            longs.append("High OI on low volume = smart money positioning quietly"); pump_conds.append("high_oi_low_vol")
        elif ratio > 2:
            s+=15; flags.append(f"OI/Volume {ratio:.1f}x — stealth accumulation")
            longs.append("OI growing while volume stays low"); pump_conds.append("oi_building")
        elif ratio > 1:
            s+=8; flags.append(f"OI/Volume {ratio:.1f}x — moderate accumulation")

    if vm > 0:
        if vm < 3:
            s+=20; flags.append(f"Low volume coiling: ${vm:.1f}M — extreme dormancy, pre-pump pattern")
            longs.append("Extreme dormancy = compressed spring"); pump_conds.append("extreme_dormancy")
        elif vm < 10:
            s+=15; flags.append(f"Low volume coiling: ${vm:.1f}M — classic pre-pump dormancy")
            longs.append("Low volume + flat price = you're early"); pump_conds.append("low_vol_coil")
        elif vm < 30:
            s+=8; flags.append(f"Below average volume ${vm:.1f}M")

    if hi > 0 and lo > 0:
        rng = ((hi - lo) / lo) * 100
        if rng < 3 and vm < 10:
            s+=15; flags.append(f"Price coiling: {rng:.1f}% range — tight consolidation")
            longs.append("Tight range + low volume = pre-breakout coil"); pump_conds.append("tight_coil")
        elif rng < 5:
            s+=8; flags.append(f"Moderate coiling: {rng:.1f}% 24h range")

    if abs(bas) > 0.05:
        if bas < -0.2:
            s+=12; flags.append(f"Basis {bas:+.3f}% — futures below spot: shorts overextended")
            longs.append("Negative basis = shorts overextended"); pump_conds.append("neg_basis")
        elif bas > 0.5:
            risks.append(f"Basis {bas:+.3f}% — futures premium: longs overheating")

    if abs(pc) < 2 and vm < 10:
        s+=10; flags.append(f"Price flat {pc:+.1f}% on low volume — pump hasn't started: early entry window")
        longs.append("Flat price = you're early, pump hasn't happened yet"); pump_conds.append("flat_price")
    elif pc > 20:
        risks.append(f"Price already up {pc:+.1f}% — possible late entry")

    pump = len(pump_conds) >= 4
    if pump:
        s+=15
        flags.append(f"ALL SIGNALS ALIGN ({len(pump_conds)}/7): {', '.join(pump_conds)}")
        longs.append("ENTER LONG NOW: all pre-pump conditions confirmed")

    return min(s, 100), flags, longs, risks, pump

def long_setup(data, crime_score):
    p  = data.get("price", 0)
    lo = data.get("low_24h", 0)
    if not p: return None
    stop = lo * 0.98
    if crime_score >= 75:   t1,t2,t3,conf = p*1.08,p*1.15,p*1.30,"HIGH"
    elif crime_score >= 50: t1,t2,t3,conf = p*1.05,p*1.10,p*1.20,"MODERATE"
    else:                   t1,t2,t3,conf = p*1.03,p*1.06,p*1.12,"LOW"
    risk = ((p - stop) / p) * 100
    rr   = (t1 - p) / (p - stop) if p > stop else 0
    return {"entry":p,"stop":stop,"t1":t1,"t2":t2,"t3":t3,"risk":risk,"rr":rr,"conf":conf}

async def scan_token(symbol, prefetched_data=None):
    if prefetched_data:
        async with aiohttp.ClientSession(
            headers={"User-Agent":"CrimeWatch/1.0"},
            timeout=aiohttp.ClientTimeout(total=15)
        ) as session:
            data = await fetch_bitunix_ticker(session, prefetched_data)
    else:
        data = await fetch_data(symbol)
    if not data.get("found"):
        return {"symbol":symbol,"error":data.get("error","Could not fetch data"),"crime_score":0,"pump_signal":False}
    cs, flags, longs, risks, pump = score(data)
    setup = long_setup(data, cs)
    def fm(v): return f"${v/1e6:.1f}M" if v and v>=1e6 else (f"${v/1e3:.1f}K" if v and v>=1e3 else "N/A")
    def fp(v):
        if not v: return "N/A"
        if v<0.0001: return f"${v:.8f}"
        if v<0.01: return f"${v:.6f}"
        return f"${v:.4f}"
    return {"symbol":symbol,"exchange":data.get("exchange","?"),
            "price":fp(data.get("price")),
            "price_change":f"{data.get('price_change_24h',0):+.2f}%",
            "volume_24h":fm(data.get("volume_24h")),
            "open_interest":fm(data.get("open_interest")),
            "funding_rate":f"{data.get('funding_rate',0):+.4f}% per 8h" if data.get("funding_rate") is not None else "N/A",
            "ls_ratio":f"{data.get('ls_ratio',0):.2f}" if data.get("ls_ratio") else "N/A",
            "basis":f"{data.get('basis',0):+.3f}%",
            "crime_score":cs,"flags":flags,"long_signals":longs,
            "risk_signals":risks,"pump_signal":pump,"long_setup":setup,"raw":data}
