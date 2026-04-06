import asyncio, logging, datetime, os
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, get_binance_symbols
from whale import scan_whale_activity
from filters import is_crime_pump_setup
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES, MIN_ALERT_SCORE

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted = {}
last_whale_alerted = set()
snoozed = set()
scan_stats = {"last_scan":"Never","tokens_scanned":0,"alerts_sent":0,"last_whale_scan":"Never","whale_contracts_resolved":0}
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY","")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
    await update.message.reply_text(
        "🔮 *Crime Watch*\n\n"
        "Alerts only on genuine crime pump setups.\n\n"
        "*Entry method:* Support bounce with volume confirmation\n"
        "*Stop:* Below consolidation support\n"
        "*Targets:* Resistance + measured moves\n\n"
        "• /scan SYMBOL — Manual scan\n"
        "• /status — Scanner status\n"
        "• /snooze SYMBOL — Mute a token",
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
        f"  • Filter: negative funding + L/S <0.67 + negative basis\n\n"
        f"🐋 *Whale scanner:*\n"
        f"  • Last scan: {scan_stats['last_whale_scan']}\n"
        f"  • Contracts resolved: {scan_stats['whale_contracts_resolved']}\n\n"
        f"  • Total alerts sent: {scan_stats['alerts_sent']}\n"
        f"  • Your chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

def fmt(r):
    if r.get("error"):
        return f"❌ *{r['symbol']}*\n{r['error']}"
    sc  = r["crime_score"]
    lbl = "🚀 EXTREME" if sc>=75 else ("💎 HIGH" if sc>=65 else ("🟠 MODERATE" if sc>=50 else "🟢 CLEAN"))
    pump_line = "🚨 *LIVE PUMP SIGNAL — ENTER LONG NOW*" if r.get("pump_signal") else "⏸ Setup forming — entry at support."
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
    if setup:
        def fp(v):
            if not v: return "N/A"
            if v < 0.0001: return f"${v:.8f}"
            if v < 0.01: return f"${v:.6f}"
            return f"${v:.4f}"
        vol_tag = "✅ Volume confirmed" if setup.get("vol_confirm") else "⚠️ Low volume — wait for confirmation"
        dist    = setup.get("distance_from_support", 0)
        entry_note = "🎯 Price at support — ideal entry zone" if dist <= 3 else f"⚠️ Price {dist:.1f}% above support — wait for pullback to {fp(setup['support'])}"
        lines += [
            f"*📊 Technical Setup ({setup['conf']} confidence):*",
            f"  {entry_note}",
            f"  {vol_tag}", "",
            f"  Support:    {fp(setup['support'])}",
            f"  Resistance: {fp(setup['resistance'])}",
            f"  Range:      {fp(setup['range_height'])}", "",
            f"  🟢 Entry:   {fp(setup['entry'])}  ← bounce off support",
            f"  🔴 Stop:    {fp(setup['stop'])} (-{setup['risk']:.1f}%)  ← below support floor",
            f"  🎯 T1:      {fp(setup['t1'])} → take 40%  ← top of range",
            f"  🎯 T2:      {fp(setup['t2'])} → take 40%  ← measured move",
            f"  🎯 T3:      {fp(setup['t3'])} → let 20% ride  ← extended target",
            f"  R:R = 1:{setup['rr']:.1f}", ""
        ]
    lines.append(f"[Trade on Binance]({trade_url})")
    return "\n".join(lines)

def fmt_whale(alert):
    pct=alert.get("pct_supply",0); amount=alert.get("amount",0)
    symbol=alert.get("symbol","?").replace("USDT","")
    whale=alert.get("whale_address","?"); tx=alert.get("tx_hash","?")
    chain_id=alert.get("chain_id",1)
    explorer="https://etherscan.io" if chain_id==1 else "https://bscscan.com"
    short_whale=f"{whale[:6]}...{whale[-4:]}" if len(whale)>10 else whale
    short_tx=f"{tx[:10]}..." if len(tx)>10 else tx
    urgency="🚨 CRITICAL" if pct>=10 else ("🔴 HIGH" if pct>=5 else "🟠 NOTABLE")
    return "\n".join([
        f"🐋 *WHALE ALERT — ${symbol}* [{urgency}]","",
        f"Large withdrawal just left Binance:",
        f"  • Amount: *{amount:,.0f} {symbol}*",
        f"  • Supply removed: *{pct:.1f}% of circulating supply*",
        f"  • Destination: `{short_whale}`",
        f"  • Tx: [{short_tx}]({explorer}/tx/{tx})","",
        f"*What this means:*",
        f"  • Less {symbol} on exchange = supply shock incoming",
        f"  • If shorts are heavy, squeeze is primed",
        f"  • Negative funding = entry window open","",
        f"*Next step:* /scan {symbol}USDT",
        f"[Trade on Binance](https://www.binance.com/en/futures/{symbol}USDT)"
    ])

async def send_crime_alert(app, result):
    text = f"🚨 *CRIME PUMP SETUP DETECTED — {result['symbol']}*\n\n" + fmt(result)
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
            for symbol in symbols:
                if symbol in snoozed: continue
                try:
                    result = await scan_token(symbol)
                    prev = last_alerted.get(symbol, 0)
                    is_crime, reason = is_crime_pump_setup(result)
                    if is_crime and result["crime_score"] > prev + 8:
                        await send_crime_alert(app, result)
                        last_alerted[symbol] = result["crime_score"]
                        logger.info(f"CRIME ALERT: {symbol} — {reason}")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Scan error {symbol}: {e}")
            logger.info("Market scan complete.")
        except Exception as e:
            logger.error(f"Market cycle error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

async def whale_scan_loop(app):
    import aiohttp
    await asyncio.sleep(120)
    while True:
        if not ETHERSCAN_API_KEY:
            await asyncio.sleep(60 * 60); continue
        try:
            scan_stats["last_whale_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            async with aiohttp.ClientSession(
                headers={"User-Agent":"CrimeWatch/1.0"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                symbols = await get_binance_symbols(session)
            findings = await scan_whale_activity(symbols, ETHERSCAN_API_KEY)
            scan_stats["whale_contracts_resolved"] = len(findings)
            for alert in findings:
                tx_hash = alert.get("tx_hash")
                if tx_hash and tx_hash not in last_whale_alerted:
                    last_whale_alerted.add(tx_hash)
                    await send_whale_alert(app, alert)
        except Exception as e:
            logger.error(f"Whale cycle error: {e}")
        await asyncio.sleep(60 * 60)

async def main():
    req = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30)
    app = Application.builder().token(BOT_TOKEN).request(req).build()
    for cmd, fn in [
        ("start", start), ("scan", scan_cmd),
        ("snooze", snooze_cmd), ("unsnooze", unsnooze_cmd),
        ("status", status_cmd)
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    logger.info("Crime Watch — support bounce entry active")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        asyncio.create_task(market_scan_loop(app))
        asyncio.create_task(whale_scan_loop(app))
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
