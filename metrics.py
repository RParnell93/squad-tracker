# Performance Score and Percentile curves
# Calibrated for casual-competitive friend groups (K/D 1-7, Win% 3-25)

PERCENTILE_CURVES = {
    "K/D": [
        (0, 0), (0.3, 5), (0.5, 10), (0.8, 20), (1.0, 30),
        (1.3, 40), (1.5, 48), (2.0, 58), (2.5, 66), (3.0, 74),
        (4.0, 84), (5.0, 90), (6.0, 95), (8.0, 99), (10.0, 100),
    ],
    "Win Rate": [
        (0, 0), (1, 8), (2, 15), (3, 22), (5, 35), (7, 45),
        (10, 58), (13, 68), (16, 76), (20, 84), (25, 90),
        (30, 94), (40, 97), (50, 99), (100, 100),
    ],
    "Kills/Match": [
        (0, 0), (0.5, 10), (1.0, 22), (1.5, 35), (2.0, 46),
        (2.5, 55), (3.0, 64), (4.0, 76), (5.0, 85), (6.0, 91),
        (8.0, 96), (10.0, 100),
    ],
    "Score/Match": [
        (0, 0), (100, 10), (200, 22), (300, 35), (400, 45),
        (500, 55), (700, 68), (900, 78), (1200, 88), (1500, 94), (2000, 100),
    ],
    "Outlived/Match": [
        (0, 0), (10, 5), (20, 14), (30, 24), (40, 35),
        (50, 46), (60, 58), (70, 70), (75, 78), (80, 84),
        (85, 90), (90, 95), (95, 100),
    ],
}

# Curves used by perf_score()
SCORE_CURVES = {
    "kd": PERCENTILE_CURVES["K/D"],
    "winRate": PERCENTILE_CURVES["Win Rate"],
    "killsPerMatch": PERCENTILE_CURVES["Kills/Match"],
    "outlivedPerMatch": PERCENTILE_CURVES["Outlived/Match"],
}


def value_to_percentile(value, curve):
    """Interpolate a stat value to an estimated percentile."""
    if value <= curve[0][0]:
        return curve[0][1]
    if value >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        v0, p0 = curve[i]
        v1, p1 = curve[i + 1]
        if v0 <= value <= v1:
            t = (value - v0) / (v1 - v0)
            return p0 + t * (p1 - p0)
    return 50


def pct_color(pct):
    """Return color matching Statcast blue-to-red gradient."""
    if pct >= 90:
        return "#c8102e"  # dark red / elite
    if pct >= 75:
        return "#ef5350"  # light red / great
    if pct >= 50:
        return "#b0bec5"  # gray / average
    if pct >= 25:
        return "#64b5f6"  # light blue / below avg
    return "#1565c0"  # dark blue / poor


def _activity_multiplier(matches, window_days=7):
    """Confidence/activity scaling factor.

    Ramps from 0.5 (1 match) to 1.0 at the full confidence threshold,
    then gives a mild bonus up to 1.08 for heavy volume.
    """
    if matches <= 0:
        return 0
    full_conf = 15 if window_days <= 7 else 40
    max_bonus_at = full_conf * 3

    if matches < full_conf:
        t = matches / full_conf
        return 0.5 + 0.5 * (t ** 0.5)
    else:
        overage = (matches - full_conf) / (max_bonus_at - full_conf)
        overage = min(overage, 1.0)
        return 1.0 + 0.08 * overage


def perf_score(stats_dict, window_days=7):
    """Dub Score: 0-100 composite performance rating.

    Components (percentile-based):
        45% Win Rate       - winning is the point
        30% K/D            - combat effectiveness
        25% Outlived/Match - survival / game sense

    Scaled by activity multiplier based on match count.
    """
    if not stats_dict:
        return None
    o = stats_dict.get("all", {}).get("overall", {})
    if not o or not o.get("matches", 0):
        return None

    matches = o.get("matches", 0) or 0

    wr_pct = value_to_percentile(o.get("winRate", 0) or 0, SCORE_CURVES["winRate"])
    kd_pct = value_to_percentile(o.get("kd", 0) or 0, SCORE_CURVES["kd"])

    outlived = o.get("playersOutlived", 0) or 0
    opm = outlived / max(matches, 1)
    opm_pct = value_to_percentile(opm, SCORE_CURVES["outlivedPerMatch"])

    raw = 0.45 * wr_pct + 0.30 * kd_pct + 0.25 * opm_pct
    mult = _activity_multiplier(matches, window_days)
    scaled = raw * mult

    return min(round(scaled), 100)


def score_color(s):
    if s is None:
        return "#444"
    if s >= 75:
        return "#00c853"  # green
    if s >= 50:
        return "#ffc107"  # yellow
    return "#ef5350"  # red


def score_circle_html(score, label):
    """CSS donut circle like WHOOP recovery scores."""
    if score is None:
        score_text = "--"
        deg = 0
    else:
        score_text = str(score)
        deg = round(score * 3.6)
    color = score_color(score)
    return f'''<div style="display:flex;flex-direction:column;align-items:center;">
        <div style="width:clamp(56px,18vw,72px);height:clamp(56px,18vw,72px);border-radius:50%;background:conic-gradient({color} {deg}deg, #1a1a2e {deg}deg);display:flex;align-items:center;justify-content:center;">
            <div style="width:clamp(44px,14vw,58px);height:clamp(44px,14vw,58px);border-radius:50%;background:#16213e;display:flex;flex-direction:column;align-items:center;justify-content:center;">
                <span style="color:white;font-size:clamp(14px,4vw,18px);font-weight:800;line-height:1;">{score_text}</span>
            </div>
        </div>
        <span style="color:#a8a8b3;font-size:clamp(7px,2vw,9px);font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-top:4px;text-align:center;line-height:1.4;">{label}</span>
    </div>'''
