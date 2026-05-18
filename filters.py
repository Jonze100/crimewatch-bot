from alpha_tokens import ALPHA_TOKENS

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
    is_alpha = result.get("is_alpha", False)
    dynamic_score = result.get("dynamic_score", 0)

    # Volume <= $8M
    if vm > 8:
        return False, f"Vol ${vm:.1f}M > $8M", ""

    # OI/Volume >= 2.5x
    ratio = oi / vol if vol > 0 else 0
    if ratio < 2.5:
        return False, f"OI/Vol {ratio:.1f}x < 2.5x", ""

    # L/S <= 0.75 or missing with high score
    if lsr is not None:
        if lsr > 0.75:
            return False, f"L/S {lsr:.2f} > 0.75", ""
    else:
        if sc < 75:
            return False, f"L/S missing and score {sc} < 75", ""

    # Price change <= 5%
    if abs(pc) > 5:
        return False, f"Price moved {pc:.1f}%", ""

    # OI >= $3M
    if om < 3:
        return False, f"OI ${om:.1f}M < $3M", ""

    # Funding <= +0.015%
    if fr is not None and fr > 0.015:
        return False, f"Funding {fr:+.4f}% > 0.015%", ""

    # Score threshold
    min_score = 60 if is_alpha else 65
    if sc < min_score and dynamic_score < 15:
        return False, f"Score {sc} < {min_score} and no dynamic signal", ""

    # Label
    confirmed = (
        lsr is not None and lsr < 0.67 and
        fr is not None and fr < 0 and
        vm < 3
    )
    label = "CONFIRMED" if confirmed else "POTENTIAL"
    reason = f"{label} | Vol ${vm:.1f}M | OI ${om:.1f}M | ratio {ratio:.1f}x | L/S {lsr} | Score {sc}"
    return True, reason, label
