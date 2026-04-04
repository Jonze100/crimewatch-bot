import asyncio, logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, discover_all_tokens
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
    await update.message.reply_text(
        "🔮 *Crime Watch — Autonomous Pre-Pump Scanner*\n\n"
        "I scan *ALL* tokens on Binance + Bitunix futures automatically.\n"
        "You don't need to do anything — I alert you the moment I spot a setup.\n\n"
        "*Alert levels:*\n"
        "  ⚡️ Score 35+ — Early warning, setup forming\n"
        "  🔥 Score 50+ — Strong setup, get ready\n"
        "  💎 Score 75+ — High conviction, act now\n"
        "  🚨 Pump signal — ALL signals aligned, enter long\n\n"
        "*Commands:*\n"
        "• /scan SYMBOL — Manual scan of any token\n"
        "• /status — See bot status + last scan info\n"
        "• /snooze SYMBOL — Mute alerts for a token\n"
        "• /unsnooze SYMBOL — Unmute\n\n"
        f"🔄 Auto-scanning every {SCAN_INTERVAL_MINUTES} mins. Sit back.",
        parse_mode="Markdown"
    )

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /scan SYMBOL\nExample: /scan STOUSDT")
        return
    symbol = context.args[0].upper()
    if not symbol.endswith("USDT"): symbol += "USDT"
    msg = await update.message.reply_text(f"🔍 Scanning *{symbol}*...", parse_mode="Markdown")
    result = await scan_token(symbol)
    await msg.edit_text(fmt(result), parse_mode="Markdown", disable_web_page_preview=True)

snoozed = set()

async def snooze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /snooze SYMBOL")
        return
    s = context.args[0].upper()
    if not s.endswith("USDT"): s += "USDT"
    snoozed.add(s)
    await update.message.reply_text(f"🔕 *{s}* alerts muted. Use /unsnooze {s} to unmute.", parse_mode="Markdown")

async def unsnooze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /unsnooze SYMBOL")
        return
    s = context.args[0].upper()
    if not s.endswith("USDT"): s += "USDT"
    snoozed.discard(s)
    await update.message.reply_text(f"🔔 *{s}* alerts back on.", parse_mode="Markdown")

scan_stats = {"last_scan": "Never", "tokens_scanned": 0, "alerts_sent": 0}

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🟢 *Crime Watch — Running*\n\n"
        f"• Last scan: {scan_stats['last_scan']}\n"
        f"• Tokens scanned: {scan_stats['tokens_scanned']}\n"
        f"• Total alerts sent: {scan_stats['alerts_sent']}\n"
        f"• Snoozed tokens: {len(snoozed)}\n"
        f"• Scan interval: {SCAN_INTERVAL_MINUTES} mins\n"
        f"• Exchanges: Binance + Bitunix\n"
        f"• Your chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

def fmt(r):
    if r.get("error"):
        return f"❌ *{r['symbol']}*\n{r['error']}"
    sc = r["crime_score"]
    lbl = "🔴 HIGH" if sc>=75 else ("🟠 MODERATE" if sc>=50 else ("🟡 EARLY" if sc>=35 else "🟢 CLEAN"))
    pump_line = "🚨 *LIVE PUMP SIGNAL — ENTER LONG NOW*" if r.get("pump_signal") else "⏸ No live signal yet."
    exch = r.get("exchange", "?")
    trade_url = (f"https://www.binance.com/en/futures/{r['symbol']}"
                 if exch == "Binance" else f"https://www.bitunix.com/futures/{r['symbol']}")
    lines = [
        f"🔮 *{r['symbol']}* [{exch}]  |  Crime score: *{sc}/100 ({lbl})*", "",
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
    if setup and sc >= 35:
        def fp(v):
            if v < 0.0001: return f"${v:.8f}"
            if v < 0.01: return f"${v:.6f}"
            return f"${v:.4f}"
        lines += [
            f"*📊 Long Setup ({setup['conf']}):*",
            f"  Entry:    {fp(setup['entry'])}",
            f"  Stop:     {fp(setup['stop'])} (-{setup['risk']:.1f}%)",
            f"  T1: {fp(setup['t1'])} → 40%  |  T2: {fp(setup['t2'])} → 40%  |  T3: {fp(setup['t3'])} → 20%",
            f"  R:R = 1:{setup['rr']:.1f}", ""
        ]
    lines.append(f"[Trade on {exch}]({trade_url})")
    return "\n".join(lines)

async def send_alert(app, result, level):
    labels = {
        "early":  "⚡️ EARLY WARNING",
        "strong": "🔥 STRONG SETUP",
        "high":   "💎 HIGH CONVICTION",
        "pump":   "🚨 LIVE PUMP SIGNAL"
    }
    header = f"{labels[level]} — *{result['symbol']}* [{result.get('exchange','?')}]\n\n"
    text = header + fmt(result)
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown", disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Alert failed {cid}: {e}")

async def auto_scan(app):
    while True:
        try:
            import datetime
            scan_stats["last_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            logger.info("Starting auto-discovery scan...")
            tokens = await discover_all_tokens()
            scan_stats["tokens_scanned"] = len(tokens)
            logger.info(f"Scanning {len(tokens)} tokens...")

            for entry in tokens:
                source, payload = entry
                try:
                    if source == "binance":
                        symbol = payload
                        if symbol in snoozed: continue
                        result = await scan_token(symbol)
                    elif source == "bitunix_prefetched":
                        symbol = payload.get("symbol", "")
                        if symbol in snoozed: continue
                        result = await scan_token(symbol, prefetched_data=payload)
                    else:
                        continue

                    sc   = result.get("crime_score", 0)
                    pump = result.get("pump_signal", False)
                    prev = last_alerted.get(symbol, 0)

                    if pump:
                        await send_alert(app, result, "pump")
                        last_alerted[symbol] = sc
                    elif sc >= 75 and sc > prev + 8:
                        await send_alert(app, result, "high")
                        last_alerted[symbol] = sc
                    elif sc >= 50 and sc > prev + 8:
                        await send_alert(app, result, "strong")
                        last_alerted[symbol] = sc
                    elif sc >= 35 and prev < 35:
                        await send_alert(app, result, "early")
                        last_alerted[symbol] = sc

                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Scan error {entry}: {e}")

            logger.info(f"Scan complete. {len(tokens)} tokens checked.")
        except Exception as e:
            logger.error(f"Auto-scan cycle error: {e}")

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
    logger.info("Crime Watch autonomous mode running...")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        asyncio.create_task(auto_scan(app))
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()

asyncio.run(main())
