def is_crime_pump_setup(result):
    """
    Strict crime pump filter.
    Based on STO and ARIA setups — only fires when ALL conditions match.
    Expect 3-7 alerts per day maximum.
    """
    raw = result.get("raw", {})
    sc  = result.get("crime_score", 0)
    fr  = raw.get("funding_rate")
    lsr = raw.get("ls_ratio")
    vol = raw.get("volume_24h", 0)
    oi  = raw.get("open_interest", 0)
    pc  = raw.get("price_change_24h", 0)
    vm  = vol / 1_000_000 if vol else 0
    om  = oi / 1_000_000 if oi else 0

    # 1. MUST: score 75+ or live pump signal
    if sc < 75 and not result.get("pump_signal"):
        return False, f"Score {sc} too low"

    # 2. MUST: funding neutral or negative — shorts are loading
    if fr is None or fr > 0.008:
        return False, f"Funding {fr} too positive — longs dominant, not a crime setup"

    # 3. MUST: market heavily short — squeeze fuel present
    if lsr is None or lsr > 0.75:
        return False, f"L/S {lsr} not short enough — need below 0.75"

    # 4. MUST: low volume — pump hasn't started yet
    if vm > 30:
        return False, f"Volume ${vm:.0f}M too high — move may already be happening"

    # 5. MUST: price not already moving — you're still early
    if pc > 10:
        return False, f"Price already up {pc:.1f}% — too late to enter"

    # 6. MUST: OI present — leveraged positions building
    if om < 2:
        return False, f"OI ${om:.1f}M too low — no leverage buildup"

    # 7. MUST: at least 2 of the strongest signals
    strong_signals = 0
    if lsr < 0.67: strong_signals += 1   # extremely short
    if fr is not None and fr < 0: strong_signals += 1   # negative funding
    if vm < 5: strong_signals += 1        # extreme low volume
    if result.get("pump_signal"): strong_signals += 1   # all signals aligned
    if om > 5 and vm < 10: strong_signals += 1          # high OI on very low volume

    if strong_signals < 2:
        return False, f"Only {strong_signals} strong signal — need at least 2"

    reason = f"L/S {lsr:.2f} | Funding {fr:+.4f}% | Vol ${vm:.1f}M | OI ${om:.1f}M | Score {sc}"
    return True, reason
