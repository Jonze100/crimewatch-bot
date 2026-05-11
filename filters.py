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

    # MUST: volume ≤ $2.5M — complete ghost town, zero attention
    if vm > 2.5:
        return False, f"Vol ${vm:.1f}M > $2.5M", ""

    # MUST: OI ≥ 4.5x volume — ultra-stealth whale accumulation
    if oi_vol < 4.5:
        return False, f"OI/Vol {oi_vol:.1f}x < 4.5x", ""

    # MUST: OI ≥ $6M — serious money committed
    if om < 6:
        return False, f"OI ${om:.1f}M < $6M", ""

    # MUST: L/S ≤ 0.63 — extreme short crowding, max liquidation cascade potential
    if lsr is not None and lsr > 0.63:
        return False, f"L/S {lsr:.2f} > 0.63", ""
    if lsr is None and crime_score < 92:
        return False, f"L/S unavailable, score {crime_score} < 92", ""

    # MUST: price truly flat ≤ ±2% — pump absolutely hasn't started
    if abs(pc) > 2:
        return False, f"Price moved {pc:.1f}%", ""

    # MUST: funding nearly neutral or negative — no long crowding at all
    if fr is not None and fr > 0.005:
        return False, f"Funding {fr:+.4f}% too positive", ""

    # CONFIRMED = ultra-tight: extreme shorts, deeply negative funding, very low volume
    if lsr is not None and lsr < 0.53 and fr is not None and fr < -0.01 and vm < 1.5:
        label = "CONFIRMED"
    else:
        label = "POTENTIAL"

    lsr_str = f"{lsr:.2f}" if lsr is not None else "N/A"
    reason  = f"Vol ${vm:.1f}M | OI ${om:.1f}M | OI/Vol {oi_vol:.1f}x | L/S {lsr_str}"
    return True, reason, label
