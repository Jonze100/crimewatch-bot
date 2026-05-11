import asyncio, logging, datetime, os, json, signal
import aiohttp
from aiohttp import web
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, get_binance_symbols
from filters import is_crime_pump_setup
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES, MIN_ALERT_SCORE
from alpha_tokens import ALPHA_TOKENS, AI_NARRATIVE_TOKENS

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted = {}   # symbol → last crime_score that triggered an alert
snoozed = set()
scan_stats = {"last_scan":"Never","tokens_scanned":0,"alerts_sent":0}

CHAT_IDS_FILE = "chat_ids.json"

def load_chat_ids():
    """Load persisted chat IDs from disk and merge with env-var ones."""
    try:
        if os.path.exists(CHAT_IDS_FILE):
            stored = json.load(open(CHAT_IDS_FILE))
            for cid in stored:
                if cid not in ALERT_CHAT_IDS:
                    ALERT_CHAT_IDS.append(cid)
    except Exception as e:
        logger.warning(f"Could not load chat IDs: {e}")

def save_chat_ids():
    try:
        with open(CHAT_IDS_FILE, "w") as f:
            json.dump(ALERT_CHAT_IDS, f)
    except Exception as e:
        logger.warning(f"Could not save chat IDs: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
        save_chat_ids()
    await update.message.reply_text(
        "🔮 *Crime Watch — Ultra Strict Mode*\n\n"
        "*🚨 CRIME PUMP filters (ultra strict):*\n"
        "  • Volume ≤ $2.5M — complete ghost town\n"
        "  • OI ≥ 4.5x volume — ultra-stealth whale accumulation\n"
        "  • OI ≥ $6M — serious money committed\n"
        "  • L/S ≤ 0.63 — extreme short crowding\n"
        "  • Price flat ≤ ±2% — pump absolutely not started\n"
        "  • Funding ≤ +0.005% — zero long crowding\n\n"
        "  ✅ *CONFIRMED* — L/S < 0.53, funding < −0.01%, vol < $1.5M\n"
        "  ⚠️ *POTENTIAL* — passes all filters, less extreme\n\n"
        "*Score thresholds:*\n"
        "  🤖 AI narrative tokens — score ≥ 80\n"
        "  🔥 Alpha tokens — score ≥ 83\n"
        "  🚨 All others — score ≥ 87\n\n"
        "• /scan SYMBOL — Manual scan\n"
        "• /status — Bot status\n"
        "• /snooze SYMBOL — Mute a token\n"
        "• /unsnooze SYMBOL — Unmute a token",
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
    if not result.get("error"):
        _, _, label = is_crime_pump_setup(result)
        result["label"] = label
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
        f"  • Alerts sent: {scan_stats['alerts_sent']}\n\n"
        f"*Filters:* Vol ≤$2.5M | OI/Vol ≥4.5x | L/S ≤0.63 | OI ≥$6M | Price ≤±2%\n"
        f"  Score: AI ≥80 | Alpha ≥83 | Others ≥87\n\n"
        f"  • Your chat ID: `{update.effective_chat.id}`",
        parse_mode="Markdown"
    )

def fmt(r):
    if r.get("error"):
        return f"❌ *{r['symbol']}*\n{r['error']}"

    sc       = r["crime_score"]
    stat_sc  = r.get("static_score", sc)
    dyn_sc   = r.get("dynamic_score", 0)
    lbl      = ("🚀 EXTREME" if sc >= 75 else
                "💎 HIGH"    if sc >= 65 else
                "🟠 MODERATE" if sc >= 50 else
                "🟢 CLEAN")

    setup_label = r.get("label", "")
    if setup_label == "CONFIRMED":
        label_str = " | ✅ *CONFIRMED*"
    elif setup_label == "POTENTIAL":
        label_str = " | ⚠️ *POTENTIAL*"
    else:
        label_str = ""

    pump_line = ("🚨 *LIVE PUMP SIGNAL — ENTER LONG NOW*"
                 if r.get("pump_signal") else
                 "⏸ Setup forming — not live yet.")
    trade_url = f"https://www.bitunix.com/futures/{r['symbol']}"
    time_now  = datetime.datetime.utcnow().strftime("%H:%M UTC")

    if r.get("is_ai"):
        lines = [f"🤖 *AI NARRATIVE — CRIME PUMP SETUP — {r['symbol']}*",
                 f"_({r.get('exchange','Binance')} | {sc}/100 {lbl}{label_str})_",
                 "⚡ AI narrative token — highest retail FOMO + pump catalyst potential"]
    elif r.get("is_alpha"):
        lines = [f"🔥 *ALPHA TOKEN — CRIME PUMP SETUP DETECTED — {r['symbol']}*",
                 f"_({r.get('exchange','Binance')} | {sc}/100 {lbl}{label_str})_",
                 "⚡ Binance Alpha token — higher retail attention + narrative fuel"]
    else:
        lines = [f"🚨 *CRIME PUMP SETUP DETECTED — {r['symbol']}*",
                 f"_({r.get('exchange','Binance')} | {sc}/100 {lbl}{label_str})_"]
    if dyn_sc > 0:
        lines.append(f"_Score: Static {stat_sc} + Dynamic +{dyn_sc}_")
    lines += [
        "",
        f"Price:          {r.get('price','N/A')}  ({r.get('price_change','N/A')})",
        f"24h volume:     {r.get('volume_24h','N/A')}",
        f"Open interest:  {r.get('open_interest','N/A')}",
        f"Funding rate:   {r.get('funding_rate','N/A')}",
        f"L/S ratio:      {r.get('ls_ratio','N/A')}",
        f"Basis:          {r.get('basis','N/A')}",
        f"Time:           {time_now}",
        ""
    ]
    if r.get("flags"):
        lines.append("*Why flagged:*")
        for f in r["flags"]:
            lines.append(f"  • {f}")
        lines.append("")
    if r.get("long_signals"):
        lines.append("*📈 Why long:*")
        for s in r["long_signals"]:
            lines.append(f"  ✅ {s}")
        lines.append("")
    if r.get("risk_signals"):
        lines.append("*⚠️ Risks:*")
        for s in r["risk_signals"]:
            lines.append(f"  ⚠️ {s}")
        lines.append("")
    lines.append(pump_line)
    lines.append("")
    lines.append(f"[🔵 Trade on Bitunix]({trade_url})")
    return "\n".join(lines)

async def send_crime_alert(app, result):
    label  = result.get("label", "SETUP")
    if result.get("is_ai"):
        header = "🤖 AI NARRATIVE — CRIME PUMP SETUP"
    elif result.get("is_alpha"):
        header = "🔥 ALPHA TOKEN — CRIME PUMP SETUP DETECTED"
    elif label == "CONFIRMED":
        header = "✅ CONFIRMED CRIME PUMP"
    else:
        header = "⚠️ POTENTIAL CRIME PUMP"
    text = f"🚨 *{header} — {result['symbol']}*\n\n" + fmt(result)
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown",
                                       disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Crime alert failed {cid}: {e}")

async def market_scan_loop(app):
    while True:
        try:
            scan_stats["last_scan"] = datetime.datetime.now().strftime("%H:%M:%S")
            logger.info("Starting scan cycle...")

            symbols = await get_binance_symbols()
            logger.info(f"get_binance_symbols returned {len(symbols)} symbols")

            if not symbols:
                logger.error("0 symbols returned — skipping cycle")
                scan_stats["tokens_scanned"] = 0
            else:
                # Alpha tokens scanned FIRST every cycle — highest priority, most likely pumps
                alpha  = [s for s in symbols if s in ALPHA_TOKENS]
                others = [s for s in symbols if s not in ALPHA_TOKENS]
                logger.info(f"Priority split: {len(alpha)} alpha + {len(others)} others")
                scan_stats["tokens_scanned"] = len(symbols)

                for symbol in alpha + others:
                    if symbol in snoozed:
                        continue
                    try:
                        result = await scan_token(symbol)
                        if result.get("error"):
                            continue

                        prev_crime = last_alerted.get(symbol, 0)
                        is_crime, crime_reason, label = is_crime_pump_setup(result)
                        result["label"] = label
                        # Tiered thresholds: AI narrative most lenient, others strictest
                        if result.get("is_ai"):
                            threshold = 80
                        elif result.get("is_alpha"):
                            threshold = 83
                        else:
                            threshold = 87
                        crime_fires = (is_crime
                                       and result["crime_score"] >= threshold
                                       and result["crime_score"] > prev_crime + 15)

                        if crime_fires:
                            await send_crime_alert(app, result)
                            last_alerted[symbol] = result["crime_score"]
                            logger.info(f"CRIME ALERT: {symbol} [{label}] score={result['crime_score']} — {crime_reason}")

                        await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.error(f"Scan error {symbol}: {e}")

                logger.info(f"Scan complete. {scan_stats['tokens_scanned']} tokens checked.")
        except Exception as e:
            logger.error(f"Cycle error: {e}")
        await asyncio.sleep(SCAN_INTERVAL_MINUTES * 60)

async def health_server():
    port = int(os.environ.get("PORT", 8080))
    async def handle(request):
        logger.debug(f"Health check: {request.method} {request.path} from {request.remote}")
        return web.Response(text="OK", content_type="text/plain")
    srv = web.Application()
    srv.router.add_get("/", handle)
    srv.router.add_get("/health", handle)
    runner = web.AppRunner(srv)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port, shutdown_timeout=2.0)
    await site.start()
    logger.info(f"Health server listening on 0.0.0.0:{port}")

async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is empty — exiting")
        return

    load_chat_ids()
    logger.info(f"Loaded {len(ALERT_CHAT_IDS)} alert chat ID(s)")

    req = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30)
    application = Application.builder().token(BOT_TOKEN).request(req).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_cmd))
    application.add_handler(CommandHandler("snooze", snooze_cmd))
    application.add_handler(CommandHandler("unsnooze", unsnooze_cmd))
    application.add_handler(CommandHandler("status", status_cmd))

    stop_event = asyncio.Event()

    def handle_signal():
        logger.info("Shutdown signal received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            pass

    await application.initialize()
    await application.start()
    await application.updater.start_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True
    )

    asyncio.create_task(market_scan_loop(application))
    asyncio.create_task(health_server())

    logger.info("Crime Watch — fully operational")
    await stop_event.wait()

    logger.info("Shutting down gracefully...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
