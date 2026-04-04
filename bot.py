import asyncio, logging, datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, get_binance_symbols
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES, MIN_ALERT_SCORE

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted = {}
snoozed = set()
scan_stats = {"last_scan": "Never", "tokens_scanned": 0, "alerts_sent": 0}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
    await update.message.reply_text(
        "🔮 *Crime Watch — Binance Pre-Pump Scanner*\n\n"
        "Scans ALL Binance futures tokens automatically.\n"
        "Only alerts on high-conviction setups.\n\n"
        "*Alert levels:*\n"
        "  💎 Score 65–74 — High conviction\n"
        "  🚀 Score 75+ — Extreme conviction\n"
        "  🚨 Pump signal — ALL signals aligned\n\n"
        "*Commands:*\n"
        "• /scan SYMBOL — Manual scan any token\n"
        "• /status — Bot status\n"
        "• /snooze SYMBOL — Mute a token\n"
        "• /unsnooze SYMBOL — Unmute\n\n"
        f"🔄 Auto-scanning Binance every {SCAN_INTERVAL_MINUTES} mins.",
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
        f"• Exchange: Binance futures only\n"
        f"• Last scan: {scan_stats['last_scan']}\n"
        f"• Tokens scanned: {scan_stats['tokens_scanned']}\n"
        f"• Alerts sent: {scan_stats['alerts_sent']}\n"
        f"• Min alert score: {MIN_ALERT_SCORE}/100\n"
        f"• Scan interval: {SCAN_INTERVAL_MINUTES} mins\n"
        f"• Snoozed: {len(snoozed)} tokens\n"
        f"• Your chat ID: `{update.effective_chat.id}`",
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

async def send_alert(app, result, level):
    labels = {
        "high":   "💎 HIGH CONVICTION",
        "extreme":"🚀 EXTREME SETUP",
        "pump":   "🚨 LIVE PUMP SIGNAL"
    }
    header = f"{labels.get(level,'🔔')} — *{result['symbol']}*\n\n"
    text = header + fmt(result)
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Alert failed {cid}: {e}")

async def auto_scan(app):
    import aiohttp
    while True:
        try:
            scan_stats["last_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            logger.info("Fetching Binance token list...")
            async with aiohttp.ClientSession(
                headers={"User-Agent":"CrimeWatch/1.0"},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as session:
                symbols = await get_binance_symbols(session)

            scan_stats["tokens_scanned"] = len(symbols)
            logger.info(f"Scanning {len(symbols)} Binance tokens...")

            for symbol in symbols:
                if symbol in snoozed:
                    continue
                try:
                    result = await scan_token(symbol)
                    sc   = result.get("crime_score", 0)
                    pump = result.get("pump_signal", False)
                    prev = last_alerted.get(symbol, 0)

                    if pump and sc >= MIN_ALERT_SCORE:
                        await send_alert(app, result, "pump")
                        last_alerted[symbol] = sc
                    elif sc >= 75 and sc > prev + 8:
                        await send_alert(app, result, "extreme")
                        last_alerted[symbol] = sc
                    elif sc >= MIN_ALERT_SCORE and sc > prev + 8:
                        await send_alert(app, result, "high")
                        last_alerted[symbol] = sc

                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Scan error {symbol}: {e}")

            logger.info(f"Scan complete. Next in {SCAN_INTERVAL_MINUTES} mins.")
        except Exception as e:
            logger.error(f"Cycle error: {e}")

        await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

async def main():
    req = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30)
    app = Application.builder().token(BOT_TOKEN).request(req).build()
    for cmd, fn in [
        ("start", start), ("scan", scan_cmd),
        ("snooze", snooze_cmd), ("unsnooze", unsnooze_cmd),
        ("status", status_cmd)
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    logger.info("Crime Watch running — Binance only, score 65+")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        asyncio.create_task(auto_scan(app))
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()

asyncio.run(main())
