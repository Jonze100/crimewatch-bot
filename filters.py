def is_crime_pump_setup(result):
    """
    Returns True only if this looks like a real crime pump setup.
    Requires ALL core conditions to be present simultaneously.
    """
    raw = result.get("raw", {})
    sc  = result.get("crime_score", 0)
    
    # Must hit score threshold
    if sc < 75 and not result.get("pump_signal"):
        return False, "Score too low"

    fr  = raw.get("funding_rate")
    lsr = raw.get("ls_ratio")
    vol = raw.get("volume_24h", 0)
    pc  = raw.get("price_change_24h", 0)
    oi  = raw.get("open_interest", 0)
    vm  = vol / 1_000_000 if vol else 0
    om  = oi / 1_000_000 if oi else 0

    reasons = []

    # MUST: funding neutral or negative (shorts loaded)
    if fr is None or fr > 0.01:
        return False, f"Funding too positive ({fr}) — longs already dominant"

    # MUST: L/S ratio below 0.80 (market short)
    if lsr is None or lsr > 0.80:
        return False, f"L/S ratio {lsr} — not heavily short enough"

    # MUST: low volume (pump hasn't started)
    if vm > 50:
        return False, f"Volume too high (${vm:.0f}M) — pump may already be happening"

    # MUST: price not already pumping (you're early)
    if pc > 15:
        return False, f"Price already up {pc:.1f}% — too late"

    # MUST: open interest present (leveraged positions building)
    if om < 1:
        return False, f"OI too low (${om:.1f}M) — no leverage buildup"

    # BONUS: extra conviction signals
    if lsr < 0.67: reasons.append("extreme shorts")
    if fr < 0: reasons.append("negative funding")
    if vm < 5: reasons.append("extreme low volume")
    if result.get("pump_signal"): reasons.append("all signals aligned")

    # Need at least 2 bonus signals for high conviction
    if len(reasons) < 2:
        return False, f"Only {len(reasons)} conviction signal — not enough"

    return True, f"CRIME SETUP: {', '.join(reasons)}"
