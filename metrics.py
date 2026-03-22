# Performance Score and Percentile curves
# Community-sourced percentile lookup tables based on FortniteTracker tier data
# Format: list of (value, percentile) tuples - interpolated between points
PERCENTILE_CURVES = {
    "K/D": [
        (0, 0), (0.5, 15), (0.8, 30), (1.0, 50), (1.3, 65),
        (1.5, 72), (2.0, 85), (2.5, 90), (3.0, 95), (4.0, 98), (6.0, 100),
    ],
    "Win Rate": [
        (0, 0), (1, 15), (2, 25), (3, 35), (5, 50), (7, 60),
        (10, 72), (15, 82), (20, 90), (30, 95), (50, 99), (100, 100),
    ],
    "Kills/Match": [
        (0, 0), (0.5, 15), (1.0, 30), (1.5, 45), (2.0, 58),
        (2.5, 68), (3.0, 78), (4.0, 88), (5.0, 93), (7.0, 98), (10.0, 100),
    ],
    "Score/Match": [
        (0, 0), (100, 15), (200, 30), (300, 45), (400, 55),
        (500, 65), (700, 78), (900, 85), (1200, 92), (1500, 96), (2000, 100),
    ],
    "Outlived/Match": [
        (0, 0), (10, 10), (20, 25), (30, 35), (40, 45),
        (50, 55), (60, 65), (70, 78), (80, 88), (90, 95), (95, 100),
    ],
}

# Aliases used by perf_score() - reference the same curve data
SCORE_CURVES = {
    "kd": PERCENTILE_CURVES["K/D"],
    "winRate": PERCENTILE_CURVES["Win Rate"],
    "killsPerMatch": PERCENTILE_CURVES["Kills/Match"],
    "wins": [
        (0, 0), (1, 20), (2, 35), (3, 45), (5, 55),
        (7, 65), (10, 75), (15, 85), (20, 90), (30, 95), (50, 100),
    ],
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


def perf_score(stats_dict):
    """Weighted composite: 30% K/D + 25% Win Rate + 25% Kills/Match + 20% Wins."""
    if not stats_dict:
        return None
    o = stats_dict.get("all", {}).get("overall", {})
    if not o or not o.get("matches", 0):
        return None
    kd_pct = value_to_percentile(o.get("kd", 0) or 0, SCORE_CURVES["kd"])
    wr_pct = value_to_percentile(o.get("winRate", 0) or 0, SCORE_CURVES["winRate"])
    kpm_pct = value_to_percentile(o.get("killsPerMatch", 0) or 0, SCORE_CURVES["killsPerMatch"])
    wins_pct = value_to_percentile(o.get("wins", 0) or 0, SCORE_CURVES["wins"])
    return round(0.3 * kd_pct + 0.25 * wr_pct + 0.25 * kpm_pct + 0.2 * wins_pct)


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
