def is_crime_pump_setup(result):
    raw = result.get("raw", {})
    fr  = raw.get("funding_rate")
    lsr = raw.get("ls_ratio")
    vol = raw.get("volume_24h", 0)
    oi  = raw.get("open_interest", 0)
    pc  = raw.get("price_change_24h", 0)
    vm  = vol / 1_000_000 if vol else 0
    om  = oi / 1_000_000 if oi else 0

    # MUST: volume under $3M — STO $2.7M, ARIA $1.7M, RAVE $2.6M
    if vm > 3:
        return False, f"Vol ${vm:.1f}M > $3M"

    # MUST: OI at least 3x volume — stealth leverage buildup
    if vol <= 0 or (oi / vol) < 3:
        return False, f"OI/Vol {(oi/vol if vol>0 else 0):.1f}x < 3x"

    # MUST: L/S below 0.70 — very heavily short
    if lsr is None or lsr > 0.70:
        return False, f"L/S {lsr} > 0.70"

    # MUST: price flat under 3%
    if abs(pc) > 3:
        return False, f"Price moved {pc:.1f}%"

    # MUST: OI at least $5M — real money involved
    if om < 5:
        return False, f"OI ${om:.1f}M < $5M"

    # MUST: funding not bullish — no longs crowding in yet
    if fr is not None and fr > 0.01:
        return False, f"Funding {fr:+.4f}% too positive"

    reason = f"Vol ${vm:.1f}M | OI ${om:.1f}M | OI/Vol {oi/vol:.1f}x | L/S {lsr:.2f}"
    return True, reason
