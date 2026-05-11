# Binance Alpha program tokens — priority scanned first every cycle.
# Non-futures pairs silently fail at scan time.
ALPHA_TOKENS = {
    # AI agents / inference
    "AIXBTUSDT",    "ACTUSDT",      "COOKIEUSDT",   "VIRTUALUSDT",
    "GRIFFAINUSDT", "GOODAIUSDT",   "TAIUSDT",      "GPTUSDT",
    "CGPTUSDT",     "AI16ZUSDT",    "PROMPTUSDT",   "SENTIENTUSDT",
    "PIPPINUSDT",   "ZEREBRUSDT",   "NOUSDT",       "ARCUSDT",

    # AI infrastructure / data / compute
    "RENDERUSDT",   "FETUSDT",      "AGIXUSDT",     "OCEANUSDT",
    "WLDUSDT",      "ALTUSDT",      "EIGENUSDT",    "GRASSUSDT",
    "ALCHUSDT",     "COAIUSDT",

    # Gaming / social
    "MEUSDT",       "PLAYERUSDT",   "MOVEUSDT",

    # Meme / narrative
    "FARTCOINUSDT", "SPXUSDT",      "PIPUSDT",      "POPCATUSDT",
    "MOODENGUSDT",  "MOGUSDT",      "MEWUSDT",      "TOSHIUSDT",
    "DOODUSDT",     "BIRBUSDT",

    # New L1 / L2 / chain infrastructure
    "VANAUSDT",     "KAIAUSDT",     "BERAUSDT",     "SONICUSDT",
    "ZETAUSDT",     "SOONUSDT",     "IRYSUSDT",     "PEAQUSDT",
    "SQDUSDT",      "CARVUSDT",     "ZORAUSDT",     "MAGMAUSDT",
    "ALEOUSDT",     "MERLUSDT",     "FLUIDUSDT",    "SAFEUSDT",
    "MYXUSDT",      "VELOUSDT",     "NAORIUSDT",    "KGENUSDT",
    "B3USDT",       "CROSSUSDT",
}

# AI/ML narrative tokens — strongest pump catalyst + retail FOMO.
# Gets the most lenient crime pump score threshold (72 vs 75 alpha / 80 non-alpha).
AI_NARRATIVE_TOKENS = {
    "AIXBTUSDT",    "ACTUSDT",      "COOKIEUSDT",   "VIRTUALUSDT",
    "GRIFFAINUSDT", "GOODAIUSDT",   "TAIUSDT",      "GPTUSDT",
    "CGPTUSDT",     "AI16ZUSDT",    "PROMPTUSDT",   "SENTIENTUSDT",
    "PIPPINUSDT",   "ZEREBRUSDT",   "NOUSDT",       "ARCUSDT",
    "RENDERUSDT",   "FETUSDT",      "AGIXUSDT",     "OCEANUSDT",
    "WLDUSDT",      "ALTUSDT",      "EIGENUSDT",    "GRASSUSDT",
    "ALCHUSDT",     "COAIUSDT",
    # AI-adjacent established tokens
    "TAOUSDT",      "ARKMUSDT",     "AIUSDT",       "XAIUSDT",
}
