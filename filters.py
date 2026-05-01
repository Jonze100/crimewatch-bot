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


def is_trend_setup(result):
    raw           = result.get("raw", {})
    fr            = raw.get("funding_rate")
    lsr           = raw.get("ls_ratio")
    vol           = raw.get("volume_24h", 0)
    oi            = raw.get("open_interest", 0)
    pc            = raw.get("price_change_24h", 0)
    dynamic_score = result.get("dynamic_score", 0)
    trend_score   = result.get("trend_score", 0)
    vm            = vol / 1_000_000 if vol else 0
    om            = oi  / 1_000_000 if oi  else 0

    # MUST: funding in the sweet spot — longs in control, not yet crowded
    if fr is None or not (0.005 <= fr <= 0.025):
        fr_str = f"{fr:+.4f}%" if fr is not None else "N/A"
        return False, f"Funding {fr_str} outside 0.005–0.025%"

    # MUST: strong long dominance
    if lsr is None or lsr < 1.35:
        lsr_str = f"{lsr:.2f}" if lsr is not None else "N/A"
        return False, f"L/S {lsr_str} < 1.35"

    # MUST: early trend only — no exceptions for later-stage moves
    if not (3.0 <= pc <= 7.0):
        return False, f"Price change {pc:.1f}% outside 3.0–7.0%"

    # MUST: real volume conviction
    if vm < 15:
        return False, f"Vol ${vm:.1f}M < $15M"

    # MUST: substantial open interest (raw dollar value, not ratio)
    if oi < 6_000_000:
        return False, f"OI ${om:.1f}M < $6M"

    # MUST: active momentum right now — the most important gate
    if dynamic_score < 15:
        return False, f"Dynamic score {dynamic_score} < 15"

    # MUST: high conviction composite score
    if trend_score < 88:
        return False, f"Trend score {trend_score} < 88"

    reason = (f"Vol ${vm:.1f}M | OI ${om:.1f}M | L/S {lsr:.2f} | "
              f"Price +{pc:.1f}% | Dynamic {dynamic_score} | Score {trend_score}")
    return True, reason
