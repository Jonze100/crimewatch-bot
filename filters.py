def is_crime_pump_setup(result):
    raw = result.get("raw", {})
    sc  = result.get("crime_score", 0)
    fr  = raw.get("funding_rate")
    lsr = raw.get("ls_ratio")
    vol = raw.get("volume_24h", 0)
    oi  = raw.get("open_interest", 0)
    pc  = raw.get("price_change_24h", 0)
    vm  = vol / 1_000_000 if vol else 0
    om  = oi / 1_000_000 if oi else 0
    dynamic_score = result.get("dynamic_score", 0)

    if sc < 65 and not result.get("pump_signal") and dynamic_score < 20:
        return False, f"Score {sc} too low"

    if lsr is None or lsr > 0.75:
        return False, f"L/S {lsr} not short enough"

    # LOW VOLUME ONLY — this is key for crime pumps
    if vm > 30:
        return False, f"Volume ${vm:.0f}M too high"

    if pc > 15:
        return False, f"Price already up {pc:.1f}%"

    if om < 1:
        return False, f"OI ${om:.1f}M too low"

    strong = 0
    if lsr is not None and lsr < 0.67: strong += 1
    if fr is not None and fr < 0.005: strong += 1
    if vm < 10: strong += 1
    if dynamic_score >= 15: strong += 1
    if result.get("pump_signal"): strong += 1
    if om > 3 and vm < 15: strong += 1

    if strong < 2:
        return False, f"Only {strong} strong signals"

    reason = f"L/S {lsr:.2f} | Fr {fr:+.4f}% | Vol ${vm:.1f}M | OI ${om:.1f}M | Score {sc}"
    return True, reason
