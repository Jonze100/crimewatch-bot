def is_crime_pump_setup(result):
    raw         = result.get("raw", {})
    fr          = raw.get("funding_rate")
    lsr         = raw.get("ls_ratio")
    vol         = raw.get("volume_24h", 0)
    oi          = raw.get("open_interest", 0)
    pc          = raw.get("price_change_24h", 0)
    crime_score = result.get("crime_score", 0)
    vm          = vol / 1_000_000 if vol else 0
    om          = oi  / 1_000_000 if oi  else 0
    oi_vol      = (oi / vol) if vol > 0 else 0

    # MUST: volume at or under $8M
    if vm > 8:
        return False, f"Vol ${vm:.1f}M > $8M", ""

    # MUST: OI at least 2.5x volume
    if oi_vol < 2.5:
        return False, f"OI/Vol {oi_vol:.1f}x < 2.5x", ""

    # MUST: L/S at or below 0.75, or missing only if score is high enough to compensate
    if lsr is not None and lsr > 0.75:
        return False, f"L/S {lsr:.2f} > 0.75", ""
    if lsr is None and crime_score < 75:
        return False, f"L/S unavailable, score {crime_score} < 75", ""

    # MUST: price roughly flat — pump hasn't started
    if abs(pc) > 5:
        return False, f"Price moved {pc:.1f}%", ""

    # MUST: OI at least $3M — real money involved
    if om < 3:
        return False, f"OI ${om:.1f}M < $3M", ""

    # MUST: funding not too bullish — longs haven't crowded in yet
    if fr is not None and fr > 0.015:
        return False, f"Funding {fr:+.4f}% too positive", ""

    # CONFIRMED = tightest pattern: extreme shorts, negative funding, very low volume
    if lsr is not None and lsr < 0.67 and fr is not None and fr < 0 and vm < 3:
        label = "CONFIRMED"
    else:
        label = "POTENTIAL"

    lsr_str = f"{lsr:.2f}" if lsr is not None else "N/A"
    reason  = f"Vol ${vm:.1f}M | OI ${om:.1f}M | OI/Vol {oi_vol:.1f}x | L/S {lsr_str}"
    return True, reason, label


