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

    # MUST: volume ≤ $5M — very dormant, nobody watching
    if vm > 5:
        return False, f"Vol ${vm:.1f}M > $5M", ""

    # MUST: OI ≥ 3x volume — strong stealth accumulation signal
    if oi_vol < 3:
        return False, f"OI/Vol {oi_vol:.1f}x < 3x", ""

    # MUST: OI ≥ $5M — real money is involved
    if om < 5:
        return False, f"OI ${om:.1f}M < $5M", ""

    # MUST: L/S ≤ 0.70 — heavily short, max squeeze potential
    if lsr is not None and lsr > 0.70:
        return False, f"L/S {lsr:.2f} > 0.70", ""
    if lsr is None and crime_score < 80:
        return False, f"L/S unavailable, score {crime_score} < 80", ""

    # MUST: price flat ≤ ±3% — pump hasn't started
    if abs(pc) > 3:
        return False, f"Price moved {pc:.1f}%", ""

    # MUST: funding not yet bullish — longs haven't piled in
    if fr is not None and fr > 0.01:
        return False, f"Funding {fr:+.4f}% too positive", ""

    # CONFIRMED = ultra-tight: extreme shorts, deeply negative funding, very low volume
    if lsr is not None and lsr < 0.60 and fr is not None and fr < -0.005 and vm < 2:
        label = "CONFIRMED"
    else:
        label = "POTENTIAL"

    lsr_str = f"{lsr:.2f}" if lsr is not None else "N/A"
    reason  = f"Vol ${vm:.1f}M | OI ${om:.1f}M | OI/Vol {oi_vol:.1f}x | L/S {lsr_str}"
    return True, reason, label
