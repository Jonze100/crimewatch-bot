def is_crime_pump_setup(result):
    """
    Real crime pump fingerprint based on STO, ARIA, RAVE.
    Key: silent OI build + shorts dominant + low volume.
    Basis can be positive or negative — doesn't matter.
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
    dynamic_score = result.get("dynamic_score", 0)

    # MUST: score 75+ OR live pump signal OR strong dynamic signal
    if sc < 75 and not result.get("pump_signal") and dynamic_score < 20:
        return False, f"Score {sc} too low"

    # MUST: L/S below 0.75 — shorts dominant
    if lsr is None or lsr > 0.75:
        return False, f"L/S {lsr} not short enough"

    # MUST: low volume — pump hasn't started
    if vm > 50:
        return False, f"Volume ${vm:.0f}M too high — move already happening"

    # MUST: price not already pumping
    if pc > 15:
        return False, f"Price already up {pc:.1f}% — too late"

    # MUST: OI present — leverage building
    if om < 1:
        return False, f"OI ${om:.1f}M too low"

    # COUNT strong signals — need at least 2
    strong = 0
    if lsr is not None and lsr < 0.67: strong += 1       # extremely short
    if fr is not None and fr < 0.005: strong += 1         # funding neutral or negative
    if vm < 10: strong += 1                               # very low volume
    if dynamic_score >= 15: strong += 1                   # OI spike or funding flip detected
    if result.get("pump_signal"): strong += 1             # all signals aligned
    if om > 3 and vm < 15: strong += 1                    # high OI on very low volume

    if strong < 2:
        return False, f"Only {strong} strong signals"

    reason = (f"L/S {lsr:.2f} | Fr {fr:+.4f}% | "
              f"Vol ${vm:.1f}M | OI ${om:.1f}M | "
              f"Dynamic +{dynamic_score} | Score {sc}")
    return True, reason
