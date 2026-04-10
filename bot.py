import asyncio, logging, datetime, os
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, get_binance_symbols
from filters import is_crime_pump_setup
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES, MIN_ALERT_SCORE

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted = {}
snoozed = set()
scan_stats = {"last_scan":"Never","tokens_scanned":0,"alerts_sent":0}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
    await update.message.reply_text(
        "🔮 *Crime Watch*\n\n"
        "Detects crime pump setups before they happen.\n\n"
        "*Exact criteria (STO/ARIA/RAVE pattern):*\n"
        "  • Volume under $5M — nobody watching\n"
        "  • OI at least 2x volume — stealth buildup\n"
        "  • L/S below 0.75 — shorts dominant\n"
        "  • Price flat — pump not started\n\n"
        "• /scan SYMBOL — Manual scan\n"
        "• /status — Bot status\n"
        "• /snooze SYMBOL — Mute a token",
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
        f"  • Last scan: {scan_stats['last_scan']}\n"
        f"  • Tokens scanned: {scan_stats['tokens_scanned']}\n"
        f"  • Alerts sent: {scan_stats['alerts_sent']}\n"
        f"  • Filter: Vol <$5M + OI/Vol 2x+ + L/S <0.75\n"
        f"  • Your chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

def fmt(r):
    if r.get("error"):
        return f"❌ *{r['symbol']}*\n{r['error']}"
    sc  = r["crime_score"]
    lbl = "🚀 EXTREME" if sc>=75 else ("💎 HIGH" if sc>=65 else ("🟠 MODERATE" if sc>=50 else "🟢 CLEAN"))
    pump_line = "🚨 *LIVE PUMP SIGNAL — ENTER LONG NOW*" if r.get("pump_signal") else "⏸ Setup forming — not live yet."
    trade_url = f"https://www.bitunix.com/futures/{r['symbol']}"
    import datetime as dt
    time_now = dt.datetime.utcnow().strftime("%H:%M UTC")
    lines = [
        f"🔮 *{r['symbol']}* Binance  |  *{sc}/100 ({lbl})*", "",
        f"Price:          {r.get('price','N/A')}",
        f"24h volume:     {r.get('volume_24h','N/A')}",
        f"Open interest:  {r.get('open_interest','N/A')}",
        f"Funding rate:   {r.get('funding_rate','N/A')}",
        f"L/S ratio:      {r.get('ls_ratio','N/A')}",
        f"Basis:          {r.get('basis','N/A')}",
        f"Time:           {time_now}", ""
    ]
    if r.get("flags"):
        lines.append("*Why flagged:*")
        [lines.append(f"  • {f}") for f in r["flags"]]
        lines.append("")
    if r.get("long_signals"):
        lines.append("*📈 Why long:*")
        [lines.append(f"  ✅ {s}") for s in r["long_signals"]]
        lines.append("")
    lines.append(pump_line)
    lines.append("")
    lines.append(f"[🔵 Trade on Bitunix]({trade_url})")
    return "\n".join(lines)

async def send_crime_alert(app, result):
    text = f"🚨 *CRIME PUMP SETUP DETECTED — {result['symbol']}*\n\n" + fmt(result)
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown",
                                       disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Alert failed {cid}: {e}")

async def market_scan_loop(app):
    while True:
        try:
            scan_stats["last_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            logger.info("Scanning Binance tokens...")
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
                        logger.info(f"ALERT: {symbol} — {reason}")
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Scan error {symbol}: {e}")
            logger.info(f"Scan complete. {scan_stats['tokens_scanned']} tokens checked.")
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
    logger.info("Crime Watch — STO/ARIA/RAVE pattern detector active")
    async with app:
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        asyncio.create_task(market_scan_loop(app))
        await asyncio.Event().wait()
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
