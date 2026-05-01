import asyncio, logging, datetime, time, os
import aiohttp
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest
from scanner import scan_token, get_binance_symbols
from filters import is_crime_pump_setup, is_trend_setup
from config import BOT_TOKEN, ALERT_CHAT_IDS, SCAN_INTERVAL_MINUTES, MIN_ALERT_SCORE

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)
last_alerted       = {}   # symbol → last crime_score that triggered an alert
last_trend_alerted = {}   # symbol → unix timestamp of last trend alert (4h cooldown)
snoozed = set()
scan_stats = {"last_scan":"Never","tokens_scanned":0,"alerts_sent":0}

TREND_COOLDOWN_SECONDS = 4 * 3600   # 4 hours between trend alerts per symbol

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALERT_CHAT_IDS:
        ALERT_CHAT_IDS.append(chat_id)
    await update.message.reply_text(
        "🔮 *Crime Watch*\n\n"
        "Detects two types of setups:\n\n"
        "*🚨 CRIME PUMP (STO/ARIA/RAVE pattern):*\n"
        "  • Volume ≤ $8M — nobody watching\n"
        "  • OI ≥ 2.5x volume — stealth buildup\n"
        "  • OI ≥ $3M — real money involved\n"
        "  • L/S ≤ 0.75 — shorts dominant\n"
        "  • Price flat ≤ ±5% — pump not started\n"
        "  • Funding ≤ +0.015% — no long crowding yet\n\n"
        "  ✅ *CONFIRMED* — L/S < 0.67, funding negative, vol < $3M\n"
        "  ⚠️ *POTENTIAL* — passes all filters, less extreme\n\n"
        "*📈 TREND SETUP (top 3 per cycle only):*\n"
        "  • Funding 0.005–0.025% — longs in control\n"
        "  • L/S ≥ 1.35 — strong long dominance\n"
        "  • Price +3% to +7% — early trend only\n"
        "  • Volume ≥ $15M — real conviction\n"
        "  • OI ≥ $6M — real positions\n"
        "  • Dynamic score ≥ 15 — momentum now\n"
        "  • Trend score ≥ 88 — max conviction only\n"
        "  • 4-hour cooldown per token\n\n"
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
        f"*Crime pump:* Vol ≤$8M | OI/Vol ≥2.5x | L/S ≤0.75 | OI ≥$3M\n"
        f"  Min score: {MIN_ALERT_SCORE} | Fires on dynamic signal or score ≥90\n\n"
        f"*Trend setup:* Funding 0.005–0.025% | L/S ≥1.35 | Price +3–7%\n"
        f"  Vol ≥$15M | OI ≥$6M | Dynamic ≥15 | Score ≥88\n"
        f"  Top 3 per cycle | 4h cooldown per token\n\n"
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

    lines = [f"🔮 *{r['symbol']}* {r.get('exchange','Binance')}  |  *{sc}/100 ({lbl})*{label_str}"]
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

def fmt_trend(r):
    ts        = r.get("trend_score", 0)
    dyn_sc    = r.get("dynamic_score", 0)
    trade_url = f"https://www.bitunix.com/futures/{r['symbol']}"
    time_now  = datetime.datetime.utcnow().strftime("%H:%M UTC")

    lines = [
        f"🔮 *{r['symbol']}* {r.get('exchange','Binance')}  |  *{ts}/100*  |  Dynamic +{dyn_sc}",
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
    if r.get("trend_signals"):
        lines.append("*Why trending:*")
        for sig in r["trend_signals"]:
            lines.append(f"  • {sig}")
        lines.append("")
    lines.append("⚡ Trend confirmed — ride the momentum.")
    lines.append("")
    lines.append(f"[🔵 Trade on Bitunix]({trade_url})")
    return "\n".join(lines)

async def send_crime_alert(app, result):
    label  = result.get("label", "SETUP")
    header = ("✅ CONFIRMED CRIME PUMP" if label == "CONFIRMED"
              else "⚠️ POTENTIAL CRIME PUMP")
    text = f"🚨 *{header} — {result['symbol']}*\n\n" + fmt(result)
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown",
                                       disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Crime alert failed {cid}: {e}")

async def send_trend_alert(app, result, rank, total):
    text = (f"📈 *TREND SETUP — {result['symbol']}* (#{rank} of {total} this cycle)\n\n"
            + fmt_trend(result))
    scan_stats["alerts_sent"] += 1
    for cid in ALERT_CHAT_IDS:
        try:
            await app.bot.send_message(int(cid), text, parse_mode="Markdown",
                                       disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Trend alert failed {cid}: {e}")

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

            trend_candidates = []   # (trend_score, symbol, result, reason) — filled during pass

            for symbol in symbols:
                if symbol in snoozed: continue
                try:
                    result = await scan_token(symbol)
                    if result.get("error"):
                        continue

                    # --- Crime pump: evaluate and fire immediately if triggered ---
                    prev_crime = last_alerted.get(symbol, 0)
                    is_crime, crime_reason, label = is_crime_pump_setup(result)
                    result["label"] = label
                    crime_fires = (is_crime
                                   and result["crime_score"] >= MIN_ALERT_SCORE
                                   and (result.get("dynamic_alert") or result["crime_score"] >= 90)
                                   and result["crime_score"] > prev_crime + 8)

                    if crime_fires:
                        await send_crime_alert(app, result)
                        last_alerted[symbol] = result["crime_score"]
                        logger.info(f"CRIME ALERT: {symbol} [{label}] score={result['crime_score']} — {crime_reason}")
                    else:
                        # --- Trend setup: collect candidates for end-of-cycle ranking ---
                        is_trend, trend_reason = is_trend_setup(result)
                        if is_trend:
                            last_trend_time = last_trend_alerted.get(symbol, 0)
                            if time.time() - last_trend_time >= TREND_COOLDOWN_SECONDS:
                                trend_candidates.append(
                                    (result["trend_score"], symbol, result, trend_reason)
                                )

                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Scan error {symbol}: {e}")

            # --- After full pass: send top 3 trend setups ranked by score ---
            trend_candidates.sort(key=lambda x: x[0], reverse=True)
            top3 = trend_candidates[:3]
            total = len(top3)
            for rank, (ts, sym, res, reason) in enumerate(top3, 1):
                await send_trend_alert(app, res, rank=rank, total=total)
                last_trend_alerted[sym] = time.time()
                logger.info(f"TREND ALERT #{rank}/{total}: {sym} score={ts} — {reason}")

            logger.info(f"Scan complete. {scan_stats['tokens_scanned']} tokens checked, "
                        f"{total} trend alert(s) sent.")
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
