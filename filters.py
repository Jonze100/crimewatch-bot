def is_crime_pump_setup(result):
    """
    Exact fingerprint of STO, ARIA, RAVE crime pumps.
    The key signal: HIGH OI on EXTREMELY LOW volume + shorts dominant.
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

    # MUST: extremely low volume — under $5M
    # STO: $2.7M, ARIA: $1.7M, RAVE: $2.6M
    if vm > 5:
        return False, f"Volume ${vm:.1f}M too high — need under $5M"

    # MUST: L/S ratio below 0.75 — shorts dominant
    if lsr is None or lsr > 0.75:
        return False, f"L/S {lsr} not short enough"

    # MUST: OI at least 2x volume — stealth accumulation
    # STO: OI $6.3M on $2.7M vol = 2.3x
    # ARIA: OI $12.6M on $1.7M vol = 7.4x
    # RAVE: OI $9.3M on $2.6M vol = 3.6x
    if vol > 0:
        oi_vol_ratio = oi / vol
        if oi_vol_ratio < 2:
            return False, f"OI/Vol ratio {oi_vol_ratio:.1f}x too low — need 2x+"
    else:
        return False, "No volume data"

    # MUST: price flat — pump hasn't started
    if abs(pc) > 5:
        return False, f"Price moved {pc:.1f}% — too late or wrong direction"

    # MUST: minimum OI — real positions exist
    if om < 3:
        return False, f"OI ${om:.1f}M too low — need $3M+"

    # MUST: funding neutral or negative — not overly long
    if fr is not None and fr > 0.02:
        return False, f"Funding {fr:+.4f}% too positive — longs crowded"

    reason = (f"Vol ${vm:.1f}M | OI ${om:.1f}M | "
              f"OI/Vol {oi/vol:.1f}x | L/S {lsr:.2f} | "
              f"Fr {fr:+.4f}% | Score {sc}")
    return True, reason
