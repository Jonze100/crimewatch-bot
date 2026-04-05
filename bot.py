import asyncio, logging, datetime, os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, get_binance_symbols
from whale import scan_whale_activity
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES, MIN_ALERT_SCORE

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted = {}
last_whale_alerted = set()
snoozed = set()
scan_stats = {
    "last_scan": "Never", "tokens_scanned": 0,
    "alerts_sent": 0, "last_whale_scan": "Never",
    "whale_contracts_resolved": 0
}
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
    await update.message.reply_text(
        "🔮 *Crime Watch — Full Pre-Pump Intelligence*\n\n"
        "Two autonomous scanners. Every Binance futures token. No lists.\n\n"
        "📊 *Scanner 1 — Market signals (every 10 mins):*\n"
        "  • Negative funding rate\n"
        "  • Heavy short positioning\n"
        "  • OI building on low volume\n"
        "  • Price coiling + basis spread\n\n"
        "🐋 *Scanner 2 — Whale activity (every 60 mins):*\n"
        "  • Auto-discovers contracts for ALL Binance tokens\n"
        "  • Monitors Binance hot wallets on-chain\n"
        "  • Alerts when >3% of supply leaves in one tx\n\n"
        "*Alert levels:*\n"
        "  💎 65–74 — High conviction\n"
        "  🚀 75+ — Extreme conviction\n"
        "  🚨 Pump signal — All signals aligned\n"
        "  🐋 Whale alert — Supply shock detected\n\n"
        "• /scan SYMBOL — Manual scan\n"
        "• /status — Scanner status\n"
        "• /snooze SYMBOL — Mute a token\n\n"
        "Zero manual work required.",
        parse_mode="Markdown"
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /scan SYMBOL\nExample: /scan BTCUSDT")
        return
    symbol = context.args[0].upper()
    if not symbol.endswith("USDT"): symbol += "USDT"
    msg = await update.message.reply_text(f"🔍 Scanning *{symbol}*...", parse_mode="Markdown")
    result = await scan_token(symbol)
    await msg.edit_text(fmt(result), parse_mode="Markdown", disable_web_page_preview=True)

async def snooze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /snooze SYMBOL"); return
    s = context.args[0].upper()
    if not s.endswith("USDT"): s += "USDT"
    snoozed.add(s)
    await update.message.reply_text(f"🔕 *{s}* muted.", parse_mode="Markdown")

async def unsnooze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unsnooze SYMBOL"); return
    s = context.args[0].upper()
    if not s.endswith("USDT"): s += "USDT"
    snoozed.discard(s)
    await update.message.reply_text(f"🔔 *{s}* unmuted.", parse_mode="Markdown")

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🟢 *Crime Watch — Running*\n\n"
        f"📊 *Market scanner:*\n"
        f"  • Last scan: {scan_stats['last_scan']}\n"
        f"  • Tokens scanned: {scan_stats['tokens_scanned']}\n"
        f"  • Min alert score: {MIN_ALERT_SCORE}/100\n\n"
        f"🐋 *Whale scanner:*\n"
        f"  • Last scan: {scan_stats['last_whale_scan']}\n"
        f"  • Contracts resolved: {scan_stats['whale_contracts_resolved']}\n\n"
        f"  • Total alerts sent: {scan_stats['alerts_sent']}\n"
        f"  • Snoozed: {len(snoozed)} tokens\n"
        f"  • Your chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

def fmt(r):
    if r.get("error"):
        return f"❌ *{r['symbol']}*\n{r['error']}"
    sc = r["crime_score"]
    lbl = "🚀 EXTREME" if sc>=75 else ("💎 HIGH" if sc>=65 else ("🟠 MODERATE" if sc>=50 else "🟢 CLEAN"))
    pump_line = "🚨 *LIVE PUMP SIGNAL — ENTER LONG NOW*" if r.get("pump_signal") else "⏸ Setup forming — not live yet."
    trade_url = f"https://www.binance.com/en/futures/{r['symbol']}"
    lines = [
        f"🔮 *{r['symbol']}* [Binance]  |  *{sc}/100 ({lbl})*", "",
        f"Price: {r.get('price','N/A')} ({r.get('price_change','N/A')})",
        f"24h volume: {r.get('volume_24h','N/A')}",
        f"Open interest: {r.get('open_interest','N/A')}",
        f"Funding rate: {r.get('funding_rate','N/A')}",
        f"L/S ratio: {r.get('ls_ratio','N/A')}",
        f"Basis: {r.get('basis','N/A')}", ""
    ]
    if r.get("flags"):
        lines.append("*🔍 Signals:*")
        [lines.append(f"  • {f}") for f in r["flags"]]
        lines.append("")
    if r.get("long_signals"):
        lines.append("*📈 Why long:*")
        [lines.append(f"  ✅ {s}") for s in r["long_signals"]]
        lines.append("")
    if r.get("risk_signals"):
        lines.append("*⚠️ Risks:*")
        [lines.append(f"  ⚠️ {s}") for s in r["risk_signals"]]
        lines.append("")
    lines.append(pump_line)
    lines.append("")
    setup = r.get("long_setup")
    if setup and sc >= 65:
        def fp(v):
            if v < 0.0001: return f"${v:.8f}"
            if v < 0.01: return f"${v:.6f}"
            return f"${v:.4f}"
        lines += [
            f"*📊 Long Setup ({setup['conf']}):*",
            f"  Entry:  {fp(setup['entry'])}",
            f"  Stop:   {fp(setup['stop'])} (-{setup['risk']:.1f}%)",
            f"  T1: {fp(setup['t1'])} → 40%  |  T2: {fp(setup['t2'])} → 40%  |  T3: {fp(setup['t3'])} → 20%",
            f"  R:R = 1:{setup['rr']:.1f}", ""
        ]
    lines.append(f"[Trade on Binance]({trade_url})")
    return "\n".join(lines)

def fmt_whale(alert):
    pct      = alert.get("pct_supply", 0)
    amount   = alert.get("amount", 0)
    symbol   = alert.get("symbol","?").replace("USDT","")
    whale    = alert.get("whale_address","?")
    tx       = alert.get("tx_hash","?")
    chain_id = alert.get("chain_id", 1)
    explorer = "https://etherscan.io" if chain_id == 1 else "https://bscscan.com"
    short_whale = f"{whale[:6]}...{whale[-4:]}" if len(whale) > 10 else whale
    short_tx    = f"{tx[:10]}..." if len(tx) > 10 else tx
    urgency = "🚨 CRITICAL" if pct >= 10 else ("🔴 HIGH" if pct >= 5 else "🟠 NOTABLE")
    return "\n".join([
        f"🐋 *WHALE ALERT — ${symbol}* [{urgency}]", "",
        f"Large withdrawal just left Binance:",
        f"  • Amount: *{amount:,.0f} {symbol}*",
        f"  • Supply removed: *{pct:.1f}% of circulating supply*",
        f"  • Destination: `{short_whale}`",
        f"  • Tx: [{short_tx}]({explorer}/tx/{tx})", "",
        f"*What this means:*",
        f"  • Less {symbol} on exchange = supply shock incoming",
        f"  • If shorts are heavy, squeeze is primed",
        f"  • Negative funding = entry window open", "",
        f"*Next step:* /scan {symbol}USDT",
        f"[Trade on Binance](https://www.binance.com/en/futures/{symbol}USDT)"
    ])

async def send_market_alert(app, result, level):
    labels = {
        "high":    "💎 HIGH CONVICTION",
        "extreme": "🚀 EXTREME SETUP",
        "pump":    "🚨 LIVE PUMP SIGNAL"
    }
    text = f"{labels.get(level,'🔔')} — *{result['symbol']}*\n\n" + fmt(result)
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Alert failed {cid}: {e}")

async def send_whale_alert(app, alert):
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), fmt_whale(alert), parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Whale alert failed {cid}: {e}")

async def market_scan_loop(app):
    import aiohttp
    while True:
        try:
            scan_stats["last_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            logger.info("Market scan starting...")
            async with aiohttp.ClientSession(
                headers={"User-Agent":"CrimeWatch/1.0"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                symbols = await get_binance_symbols(session)
            scan_stats["tokens_scanned"] = len(symbols)
            logger.info(f"Scanning {len(symbols)} tokens...")
            for symbol in symbols:
                if symbol in snoozed: continue
                try:
                    result = await scan_token(symbol)
                    sc   = result.get("crime_score", 0)
                    pump = result.get("pump_signal", False)
                    prev = last_alerted.get(symbol, 0)
                    if pump and sc >= MIN_ALERT_SCORE:
                        await send_market_alert(app, result, "pump")
                        last_alerted[symbol] = sc
                    elif sc >= 75 and sc > prev + 8:
                        await send_market_alert(app, result, "extreme")
                        last_alerted[symbol] = sc
                    elif sc >= MIN_ALERT_SCORE and sc > prev + 8:
                        await send_market_alert(app, result, "high")
                        last_alerted[symbol] = sc
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Scan error {symbol}: {e}")
            logger.info("Market scan complete.")
        except Exception as e:
            logger.error(f"Market cycle error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

async def whale_scan_loop(app):
    import aiohttp
    await asyncio.sleep(120)  # wait 2 mins after startup
    while True:
        if not ETHERSCAN_API_KEY:
            logger.warning("No ETHERSCAN_API_KEY — skipping whale scan")
            await asyncio.sleep(60 * 60)
            continue
        try:
            scan_stats["last_whale_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            logger.info("Whale scan starting — fetching ALL Binance symbols...")
            async with aiohttp.ClientSession(
                headers={"User-Agent":"CrimeWatch/1.0"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                symbols = await get_binance_symbols(session)
            # ALL symbols — no limit
            logger.info(f"Whale scan: resolving contracts for {len(symbols)} tokens...")
            findings = await scan_whale_activity(symbols, ETHERSCAN_API_KEY)
            scan_stats["whale_contracts_resolved"] = len(findings)
            new_alerts = 0
            for alert in findings:
                tx_hash = alert.get("tx_hash")
                if tx_hash and tx_hash not in last_whale_alerted:
                    last_whale_alerted.add(tx_hash)
                    await send_whale_alert(app, alert)
                    new_alerts += 1
            logger.info(f"Whale scan complete. {new_alerts} new alerts.")
        except Exception as e:
            logger.error(f"Whale cycle error: {e}")
        await asyncio.sleep(60 * 60)  # every 60 mins
