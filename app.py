import os
import random
import streamlit as st
import time
from datetime import date, datetime, timedelta
import plotly.graph_objects as go

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
from epic_auth import (
    load_tokens, load_device_auth, get_valid_token, lookup_account_by_name,
    stats_for_window, fetch_stats_epic, parse_raw_stats,
)

from config import DEFAULT_FORTNITE_PLAYERS, DEFAULT_OW2_PLAYERS, CSS, card_css
from api import (
    fetch_fortnite_stats, epic_parsed_to_mode_stats, fetch_epic_account_ids,
    search_ow2_player, fetch_ow2_stats,
)
from metrics import (
    SCORE_CURVES, PERCENTILE_CURVES, OW2_CURVES, value_to_percentile, pct_color,
    perf_score, ow2_perf_score, score_color, score_circle_html,
)
from helpers import get_fortnite_api_key, load_squad, save_squad
from db import fetch_weekly_trends, fetch_player_cache, fetch_ow2_cache, get_all_week_ranges, get_ytd_week_ranges, HAS_DUCKDB

st.set_page_config(page_title="Squad Stats", page_icon="🎮", layout="wide")

PLOTLY_CONFIG = {
    "displayModeBar": False,
    "scrollZoom": False,
    "doubleClick": False,          # disable double-click to zoom/reset
    "showTips": False,
    "staticPlot": True,            # nuclear option: disables ALL interaction including zoom/pan/select
}

def _lock_axes(fig):
    """Disable all zoom/pan on a Plotly figure by locking every axis."""
    fig.update_xaxes(fixedrange=True)
    fig.update_yaxes(fixedrange=True)
    return fig

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown(CSS, unsafe_allow_html=True)

# ── Anthropic API key (shared by Fortnite + OW2 AI summaries) ──────────────
_anthropic_key = ""
if HAS_ANTHROPIC:
    _anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not _anthropic_key:
        try:
            _anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
        except (KeyError, FileNotFoundError):
            _anthropic_key = ""

# ── State / Persistence ─────────────────────────────────────────────────────
# Build lookup dicts for restoring full player objects from names
_fn_lookup = {p["name"].lower(): p for p in DEFAULT_FORTNITE_PLAYERS}
_ow2_lookup = {p["name"].lower(): p for p in DEFAULT_OW2_PLAYERS}


def _resolve_fn_player(name):
    """Resolve a Fortnite player name to a full player dict."""
    match = _fn_lookup.get(name.lower())
    if match:
        return dict(match)
    return {"name": name, "type": "epic", "platform": "Epic (PC)"}


def _resolve_ow2_player(name):
    """Resolve an OW2 player name to a full player dict."""
    match = _ow2_lookup.get(name.lower())
    if match:
        return dict(match)
    return {"name": name}


def _sync_squad_to_url():
    """Write current squad to URL query params (enables bookmarking + sharing)."""
    fn_names = [p["name"] for p in st.session_state.squad.get("fortnite_players", [])]
    ow2_names = [p["name"] for p in st.session_state.squad.get("ow2_players", [])]
    st.query_params["fn"] = ",".join(fn_names) if fn_names else ""
    st.query_params["ow2"] = ",".join(ow2_names) if ow2_names else ""


def _save_and_sync(squad_data):
    """Save squad to file + sync to URL params + push to localStorage."""
    save_squad(squad_data)
    _sync_squad_to_url()


# localStorage bridge - reads on first load, writes on every sync
_LS_BRIDGE = """
<script>
(function() {
    const params = new URLSearchParams(window.location.search);
    const hasFn = params.has('fn') && params.get('fn').length > 0;
    const hasOw2 = params.has('ow2') && params.get('ow2').length > 0;

    if (hasFn || hasOw2) {
        // URL has squad params - save to localStorage
        if (hasFn) localStorage.setItem('squad_fn', params.get('fn'));
        if (hasOw2) localStorage.setItem('squad_ow2', params.get('ow2'));
    } else if (params.has('fn') || params.has('ow2')) {
        // URL has empty params - user cleared their squad, clear localStorage too
        localStorage.removeItem('squad_fn');
        localStorage.removeItem('squad_ow2');
    } else {
        // No URL params - check localStorage and redirect if found
        const savedFn = localStorage.getItem('squad_fn');
        const savedOw2 = localStorage.getItem('squad_ow2');
        if (savedFn || savedOw2) {
            const newParams = new URLSearchParams();
            if (savedFn) newParams.set('fn', savedFn);
            if (savedOw2) newParams.set('ow2', savedOw2);
            const newUrl = window.location.pathname + '?' + newParams.toString();
            window.location.replace(newUrl);
        }
    }
})();
</script>
"""
st.components.v1.html(_LS_BRIDGE, height=0)

if "squad" not in st.session_state:
    params = st.query_params
    fn_param = params.get("fn", "")
    ow2_param = params.get("ow2", "")

    if fn_param or ow2_param:
        # Restore squad from URL params
        fn_players = [_resolve_fn_player(n.strip()) for n in fn_param.split(",") if n.strip()] if fn_param else []
        ow2_players = [_resolve_ow2_player(n.strip()) for n in ow2_param.split(",") if n.strip()] if ow2_param else []
        st.session_state.squad = {
            "fortnite_players": fn_players,
            "ow2_players": ow2_players,
        }
    else:
        # First visit with no params - load defaults
        st.session_state.squad = {
            "fortnite_players": list(DEFAULT_FORTNITE_PLAYERS),
            "ow2_players": list(DEFAULT_OW2_PLAYERS),
        }
        _sync_squad_to_url()

if "ow2_cache" not in st.session_state:
    st.session_state.ow2_cache = {}


# ── Main Area ────────────────────────────────────────────────────────────────
_logo_svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40" width="36" height="36" style="vertical-align:middle;margin-right:10px;">
  <circle cx="20" cy="20" r="16" fill="none" stroke="#e94560" stroke-width="2.5" opacity="0.9"/>
  <circle cx="20" cy="20" r="8" fill="none" stroke="#e94560" stroke-width="1.5" opacity="0.6"/>
  <circle cx="20" cy="20" r="2.5" fill="#e94560"/>
  <line x1="20" y1="1" x2="20" y2="10" stroke="#e94560" stroke-width="2" stroke-linecap="round" opacity="0.7"/>
  <line x1="20" y1="30" x2="20" y2="39" stroke="#e94560" stroke-width="2" stroke-linecap="round" opacity="0.7"/>
  <line x1="1" y1="20" x2="10" y2="20" stroke="#e94560" stroke-width="2" stroke-linecap="round" opacity="0.7"/>
  <line x1="30" y1="20" x2="39" y2="20" stroke="#e94560" stroke-width="2" stroke-linecap="round" opacity="0.7"/>
</svg>'''
st.markdown(
    f'<h1 style="display:flex;align-items:center;margin-bottom:0;">{_logo_svg}<span>SQUAD STATS</span></h1>',
    unsafe_allow_html=True,
)

active_game = st.segmented_control(
    "Game", ["Fortnite", "Overwatch 2"], default="Fortnite",
    key="active_game", label_visibility="collapsed",
)
if not active_game:
    active_game = "Fortnite"

# ── Sidebar (driven by active game) ─────────────────────────────────────────
with st.sidebar:
    # Sidebar styling
    _sb_accent = "#e94560" if active_game == "Fortnite" else "#f99e1a"
    st.markdown(f"""<style>
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, #0d1117 0%, #161b22 40%, #1a1a2e 100%);
    }}
    [data-testid="stSidebar"] .stMarkdown hr {{
        border-color: rgba(255,255,255,0.06);
        margin: 0.8rem 0;
    }}
    .sidebar-header {{
        display: flex; align-items: center; gap: 10px;
        padding: 8px 12px; margin-bottom: 4px;
        background: linear-gradient(135deg, {_sb_accent}18, {_sb_accent}08);
        border-left: 3px solid {_sb_accent};
        border-radius: 0 8px 8px 0;
    }}
    .sidebar-header .icon {{ font-size: 1.3em; }}
    .sidebar-header .title {{
        font-size: 1.05em; font-weight: 700; color: #e6e6e6;
        letter-spacing: 0.5px; text-transform: uppercase;
    }}
    .sidebar-section {{
        font-size: 0.65em; font-weight: 600; color: {_sb_accent};
        text-transform: uppercase; letter-spacing: 0.5px;
        margin: 4px 0 6px 0; opacity: 0.8;
    }}
    .player-row {{
        display: flex; align-items: center; justify-content: space-between;
        padding: 6px 10px; margin: 3px 0;
        background: rgba(255,255,255,0.03);
        border-radius: 6px;
        transition: background 0.2s;
    }}
    .player-row:hover {{ background: rgba(255,255,255,0.06); }}
    .player-name {{
        font-weight: 600; font-size: 0.72em; color: #e6e6e6;
        white-space: nowrap;
    }}
    .player-tag-row {{
        display: flex; align-items: center; gap: 8px;
        white-space: nowrap;
    }}
    .plat-tag {{
        padding: 1px 5px; border-radius: 4px;
        font-size: 0.55em; font-weight: 700; letter-spacing: 0.5px;
        color: white; flex-shrink: 0;
    }}
    .sidebar-share {{
        padding: 8px 12px; margin-top: 4px;
        background: rgba(255,255,255,0.02);
        border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);
    }}
    .sidebar-share p {{
        font-size: 0.72em; color: #6e7681; line-height: 1.4; margin: 0;
    }}
    </style>""", unsafe_allow_html=True)

    _fn_icon_svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="22" height="22" style="vertical-align:middle;"><path fill="#e94560" d="M17.5 1h-11A3.5 3.5 0 0 0 3 4.5v15A3.5 3.5 0 0 0 6.5 23h11a3.5 3.5 0 0 0 3.5-3.5v-15A3.5 3.5 0 0 0 17.5 1zM12 4l2 4H10l2-4zm-3.5 7a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zm7 0a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3zM12 20a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"/></svg>'
    _game_icon = _fn_icon_svg if active_game == "Fortnite" else "🛡️"
    _game_label = "Fortnite" if active_game == "Fortnite" else "Overwatch 2"
    st.markdown(f'<div class="sidebar-header"><span class="icon">{_game_icon}</span><span class="title">{_game_label} Squad</span></div>', unsafe_allow_html=True)

    if active_game == "Fortnite":
        platform_map = {"Xbox": "xbl", "PlayStation": "psn", "Epic (PC)": "epic", "Nintendo Switch": "epic"}

        st.markdown("---")
        _platform_colors = {"Xbox": "#2d9f2d", "PlayStation": "#006fcd", "Epic (PC)": "#6b6b7b", "Nintendo Switch": "#e4000f"}
        _plat_short = {"Xbox": "XBOX", "PlayStation": "PSN", "Epic (PC)": "PC", "Nintendo Switch": "NSW"}
        fn_list = st.session_state.squad.get("fortnite_players", [])
        if fn_list:
            st.markdown(f'<div class="sidebar-section">Your Squad ({len(fn_list)})</div>', unsafe_allow_html=True)
        to_remove = None
        for i, p in enumerate(fn_list):
            col_name, col_btn = st.columns([3, 1])
            _pc = _platform_colors.get(p['platform'], '#a8a8b3')
            _ps = _plat_short.get(p['platform'], p['platform'].upper())
            col_name.markdown(
                f'<div class="player-tag-row"><span class="player-name">{p["name"]}</span><span class="plat-tag" style="background:{_pc};">{_ps}</span></div>',
                unsafe_allow_html=True,
            )
            if col_btn.button("✕", key=f"fn_rm_{i}"):
                to_remove = i
        if to_remove is not None:
            st.session_state.squad["fortnite_players"].pop(to_remove)
            _save_and_sync(st.session_state.squad)
            st.rerun()

        with st.expander("Search For Player", expanded=False):
            new_name = st.text_input("Gamertag", key="fn_new_name", label_visibility="collapsed", placeholder="Gamertag / Epic Name")
            new_platform = st.selectbox("Platform", list(platform_map.keys()), key="fn_platform")
            if st.button("Add Player", key="fn_add", width="stretch"):
                if new_name.strip():
                    _api_key = get_fortnite_api_key()
                    if _api_key:
                        with st.spinner(f"Looking up {new_name.strip()}..."):
                            _test = fetch_fortnite_stats(new_name.strip(), platform_map[new_platform], _api_key)
                        if _test:
                            st.session_state.squad["fortnite_players"].append({
                                "name": new_name.strip(),
                                "type": platform_map[new_platform],
                                "platform": new_platform,
                            })
                            _save_and_sync(st.session_state.squad)
                            st.rerun()
                        else:
                            st.error(f"Player \"{new_name.strip()}\" not found on {new_platform}. Check the name and platform.")
                    else:
                        st.session_state.squad["fortnite_players"].append({
                            "name": new_name.strip(),
                            "type": platform_map[new_platform],
                            "platform": new_platform,
                        })
                        _save_and_sync(st.session_state.squad)
                        st.rerun()

    else:  # OW2
        ow2_preset_players = list(DEFAULT_OW2_PLAYERS)
        ow2_current = {p["name"] for p in st.session_state.squad.get("ow2_players", [])}
        ow2_available = [p for p in ow2_preset_players if p["name"] not in ow2_current]

        st.markdown("---")
        ow2_list = st.session_state.squad.get("ow2_players", [])
        if ow2_list:
            st.markdown(f'<div class="sidebar-section">Your Squad ({len(ow2_list)})</div>', unsafe_allow_html=True)
        to_remove = None
        for i, p in enumerate(ow2_list):
            col_name, col_btn = st.columns([3, 1])
            col_name.markdown(f'<div class="player-tag-row"><span class="player-name">{p["name"]}</span><span class="plat-tag" style="background:#f99e1a;">OW2</span></div>', unsafe_allow_html=True)
            if col_btn.button("✕", key=f"ow2_rm_{i}"):
                to_remove = i
        if to_remove is not None:
            st.session_state.squad["ow2_players"].pop(to_remove)
            _save_and_sync(st.session_state.squad)
            st.rerun()

        with st.expander("Search For Player", expanded=False):
            new_ow2 = st.text_input("Display Name", key="ow2_new_name", label_visibility="collapsed", placeholder="BattleTag (public profile)")
            if st.button("Add Player", key="ow2_add", width="stretch"):
                if new_ow2.strip():
                    st.session_state.squad["ow2_players"].append({"name": new_ow2.strip()})
                    _save_and_sync(st.session_state.squad)
                    st.rerun()

    st.markdown("---")
    st.markdown(
        '<div style="text-align:center;margin:0.5rem 0;">'
        '<button onclick="navigator.clipboard.writeText(window.location.href).then(()=>{this.textContent=\'Copied!\';setTimeout(()=>{this.textContent=\'Share Link\'},2000)})" '
        'style="background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid #e94560;color:#e94560;'
        'padding:8px 20px;border-radius:8px;font-family:\'JetBrains Mono\',monospace;font-size:0.8rem;'
        'font-weight:700;cursor:pointer;letter-spacing:0.5px;width:100%;">'
        'Share Link</button></div>',
        unsafe_allow_html=True
    )

# ═══════════════════════════════════════════════════════════════════════════
# FORTNITE
# ═══════════════════════════════════════════════════════════════════════════
if active_game == "Fortnite":
    fn_players = st.session_state.squad.get("fortnite_players", [])
    if not fn_players:
        st.info("Add Fortnite players in the sidebar.")
    else:
        # Load all stats from MotherDuck (populated by daily snapshot)
        if "db_player_cache" not in st.session_state:
            with st.spinner("Loading stats..."):
                _pc = fetch_player_cache([p["name"] for p in fn_players])
                st.session_state.db_player_cache = _pc if _pc else {}

        db_cache = st.session_state.db_player_cache
        all_fn = {}
        db_7d = {}
        db_30d = {}
        _fn_needs_live = []
        for p in fn_players:
            name = p["name"]
            pc = db_cache.get(name, {})
            if "lifetime" in pc:
                all_fn[name] = pc["lifetime"]
            else:
                _fn_needs_live.append(p)
            if "7d" in pc:
                db_7d[name] = pc["7d"]
            if "30d" in pc:
                db_30d[name] = pc["30d"]

        # Live API fallback for players not in MotherDuck cache
        if _fn_needs_live:
            _api_key = get_fortnite_api_key()
            if _api_key:
                for p in _fn_needs_live:
                    name = p["name"]
                    # Check session cache first
                    if f"live_fn_{name}" in st.session_state:
                        all_fn[name] = st.session_state[f"live_fn_{name}"]
                        continue
                    with st.spinner(f"Loading {name} from API..."):
                        data = fetch_fortnite_stats(name, p.get("type", "epic"), _api_key)
                        if data:
                            all_fn[name] = data
                            st.session_state[f"live_fn_{name}"] = data

        if not all_fn:
            st.info("No stats available. Check player names or try again later.")
        else:
            # Helper to get stats for the selected time window
            def get_stats(data, name, time_window):
                if time_window == "7 Days":
                    return db_7d.get(name)
                if time_window == "30 Days":
                    return db_30d.get(name)
                if time_window == "Season":
                    _eids = st.session_state.get("epic_ids", {})
                    if _eids.get(name):
                        aid = _eids[name]
                        start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
                        end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())
                        cache_key = f"epic_{aid}_{start_ts}_{end_ts}"
                        cached = st.session_state.get("epic_cache", {}).get(cache_key)
                        if cached is not None:
                            return cached
                    if data.get("season_stats"):
                        return data["season_stats"]
                    return None
                if time_window == "Custom":
                    _eids = st.session_state.get("epic_ids", {})
                    aid = _eids.get(name)
                    if not aid:
                        return None
                    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
                    end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())
                    cache_key = f"epic_{aid}_{start_ts}_{end_ts}"
                    return st.session_state.get("epic_cache", {}).get(cache_key)
                return data.get("stats")  # Lifetime

            # Time window toggle - default to "7 Days"
            has_epic = bool(load_tokens() or load_device_auth())
            time_options = ["7 Days", "30 Days", "Lifetime", "Season"]
            if has_epic:
                time_options.append("Custom")
            time_window = st.segmented_control("Time Window", time_options, default="7 Days", key="fn_time_window")
            if not time_window:
                time_window = "7 Days"

            # Known Fortnite seasons (date ranges for Epic Stats Proxy lookup)
            FORTNITE_SEASONS = {
                "C6S2": (date(2026, 3, 8), date.today()),
                "C6S1": (date(2025, 12, 1), date(2026, 3, 7)),
                "C5S4": (date(2025, 9, 27), date(2025, 11, 30)),
                "C5S3": (date(2025, 6, 14), date(2025, 9, 26)),
                "C5S2": (date(2025, 3, 8), date(2025, 6, 13)),
                "C5S1": (date(2024, 12, 3), date(2025, 3, 7)),
            }

            epic_ids = st.session_state.get("epic_ids", {})

            if time_window == "Season":
                season_pick = st.segmented_control(
                    "Select Season", list(FORTNITE_SEASONS.keys()),
                    default=list(FORTNITE_SEASONS.keys())[0],
                    key="fn_season_select"
                )
                if not season_pick:
                    season_pick = list(FORTNITE_SEASONS.keys())[0]
                start_date, end_date = FORTNITE_SEASONS[season_pick]

                # Resolve Epic IDs on demand for Season lookup
                if has_epic and not epic_ids:
                    with st.spinner("Resolving Epic account IDs..."):
                        _ids = {}
                        config_ids = {p["name"]: p["epic_id"] for p in fn_players if p.get("epic_id")}
                        token = get_valid_token()
                        if token:
                            for name, data in all_fn.items():
                                if name in config_ids:
                                    _ids[name] = config_ids[name]
                                    continue
                                display = data.get("account", {}).get("name", name)
                                result = lookup_account_by_name(display, token)
                                if result:
                                    _ids[name] = result["id"]
                                time.sleep(0.2)
                        st.session_state.epic_ids = _ids
                        epic_ids = _ids

                if epic_ids:
                    if "epic_cache" not in st.session_state:
                        st.session_state.epic_cache = {}
                    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
                    end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())
                    range_key = f"{start_ts}_{end_ts}"
                    missing = [n for n in all_fn if epic_ids.get(n) and f"epic_{epic_ids[n]}_{range_key}" not in st.session_state.epic_cache]
                    if missing:
                        with st.spinner(f"Loading {season_pick} stats..."):
                            for name in missing:
                                aid = epic_ids[name]
                                parsed_raw = fetch_stats_epic(aid, start_ts, end_ts)
                                cache_key = f"epic_{aid}_{range_key}"
                                if parsed_raw:
                                    st.session_state.epic_cache[cache_key] = epic_parsed_to_mode_stats(parse_raw_stats(parsed_raw))
                                else:
                                    st.session_state.epic_cache[cache_key] = None
                                time.sleep(0.3)

            elif time_window == "Custom":
                col_start, col_end = st.columns(2)
                with col_start:
                    start_date = st.date_input("Start Date", value=date.today() - timedelta(days=14), max_value=date.today(), key="fn_start_date")
                with col_end:
                    end_date = st.date_input("End Date", value=date.today(), max_value=date.today(), key="fn_end_date")
                if start_date > end_date:
                    st.error("Start date must be before end date.")
                    st.stop()

                # Resolve Epic IDs on demand for Custom range
                if has_epic and not epic_ids:
                    with st.spinner("Resolving Epic account IDs..."):
                        _ids = {}
                        config_ids = {p["name"]: p["epic_id"] for p in fn_players if p.get("epic_id")}
                        token = get_valid_token()
                        if token:
                            for name, data in all_fn.items():
                                if name in config_ids:
                                    _ids[name] = config_ids[name]
                                    continue
                                display = data.get("account", {}).get("name", name)
                                result = lookup_account_by_name(display, token)
                                if result:
                                    _ids[name] = result["id"]
                                time.sleep(0.2)
                        st.session_state.epic_ids = _ids
                        epic_ids = _ids

                if epic_ids:
                    if "epic_cache" not in st.session_state:
                        st.session_state.epic_cache = {}
                    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
                    end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())
                    range_key = f"{start_ts}_{end_ts}"
                    missing = [n for n in all_fn if epic_ids.get(n) and f"epic_{epic_ids[n]}_{range_key}" not in st.session_state.epic_cache]
                    if missing:
                        with st.spinner(f"Loading stats for {start_date} to {end_date}..."):
                            for name in missing:
                                aid = epic_ids[name]
                                parsed_raw = fetch_stats_epic(aid, start_ts, end_ts)
                                cache_key = f"epic_{aid}_{range_key}"
                                if parsed_raw:
                                    st.session_state.epic_cache[cache_key] = epic_parsed_to_mode_stats(parse_raw_stats(parsed_raw))
                                else:
                                    st.session_state.epic_cache[cache_key] = None
                                time.sleep(0.3)

            names = list(all_fn.keys())
            display_names = [all_fn[n]["account"]["name"] for n in names]

            # Get the right stats dict for each player
            def player_mode(name, mode="overall"):
                stats = get_stats(all_fn[name], name, time_window)
                if not stats or "all" not in stats:
                    return {}
                if mode == "overall":
                    return stats["all"].get("overall", {}) or {}
                return stats["all"].get(mode, {}) or {}

            # Dub Scores from DB-cached 7d/30d stats
            perf_scores = {}
            for name in all_fn:
                s7 = db_7d.get(name)
                s30 = db_30d.get(name)
                perf_scores[name] = (perf_score(s7, window_days=7), perf_score(s30, window_days=30))

            # Rankings - only among players with recent activity (both dub scores > 0)
            active_names = [n for n in names if perf_scores.get(n, (None, None))[0] is not None
                            and perf_scores[n][0] > 0 and perf_scores[n][1] is not None and perf_scores[n][1] > 0]
            best_kd = max((player_mode(n).get("kd", 0) or 0 for n in active_names), default=0)
            best_wins = max((player_mode(n).get("wins", 0) or 0 for n in active_names), default=0)
            best_kills = max((player_mode(n).get("kills", 0) or 0 for n in active_names), default=0)
            best_kpm = max((player_mode(n).get("killsPerMatch", 0) or 0 for n in active_names), default=0)

            # Supreme Leader - best composite score, must have played in the last 7 days
            fn_composite = {}
            for n in names:
                s7_score = perf_scores.get(n, (None, None))[0]
                if s7_score is None:
                    continue  # no 7-day activity = not eligible
                o = player_mode(n)
                if o and o.get("matches", 0):
                    fn_composite[n] = (
                        0.4 * value_to_percentile(o.get("kd", 0) or 0, SCORE_CURVES["kd"])
                        + 0.3 * value_to_percentile(o.get("winRate", 0) or 0, SCORE_CURVES["winRate"])
                        + 0.3 * value_to_percentile(o.get("killsPerMatch", 0) or 0, SCORE_CURVES["killsPerMatch"])
                    )
            fn_supreme = max(fn_composite, key=fn_composite.get) if fn_composite and max(fn_composite.values()) > 0 else None

            # Mini percentile bar for battle cards
            _pct_map = {"K/D": "K/D", "Win%": "Win Rate", "K/M": "Kills/Match", "Out/M": "Outlived/Match"}
            def _mini_pct_bar(label, value, matches):
                if not matches:
                    return ""
                curve_name = _pct_map.get(label)
                if not curve_name or curve_name not in PERCENTILE_CURVES:
                    return ""
                pct = max(0, min(100, round(value_to_percentile(value, PERCENTILE_CURVES[curve_name]))))
                color = pct_color(pct)
                bar_w = max(pct, 3)
                return f'''<div style="display:flex;align-items:center;margin-bottom:3px;">
                    <div style="width:38px;font-size:0.6em;color:#a8a8b3;flex-shrink:0;">{label}</div>
                    <div style="flex:1;background:#0f1923;border-radius:4px;height:12px;position:relative;">
                        <div style="width:{bar_w}%;height:100%;background:{color};border-radius:4px;"></div>
                    </div>
                    <div style="width:26px;text-align:right;font-size:0.55em;color:white;font-weight:700;flex-shrink:0;">{pct}</div>
                </div>'''

            # Battle Cards - Supreme Leader first
            st.markdown("## Battle Cards")
            fn_card_order = sorted(all_fn.keys(), key=lambda n: perf_scores.get(n, (0, 0))[0] or 0, reverse=True)
            if fn_supreme and fn_supreme in fn_card_order:
                fn_card_order.remove(fn_supreme)
                fn_card_order.insert(0, fn_supreme)
            fn_cards_html = []
            for idx, name in enumerate(fn_card_order):
                data = all_fn[name]
                overall = player_mode(name)
                bp = data.get("battlePass", {})
                platform = next((p["platform"] for p in fn_players if p["name"] == name), "")
                _plat_colors = {"Xbox": "#2d9f2d", "PlayStation": "#006fcd", "Epic (PC)": "#6b6b7b", "Nintendo Switch": "#e4000f"}
                _plat_abbr = {"Xbox": "XBOX", "PlayStation": "PSN", "Epic (PC)": "PC"}
                _plat_c = _plat_colors.get(platform, "#6b6b7b")
                _plat_tag = f'<span style="background:{_plat_c};color:white;padding:2px 8px;border-radius:4px;font-size:0.7em;font-weight:700;letter-spacing:0.5px;">{_plat_abbr.get(platform, platform)}</span>'

                kd = overall.get("kd", 0) or 0
                wr = overall.get("winRate", 0) or 0
                kills = overall.get("kills", 0) or 0
                wins = overall.get("wins", 0) or 0
                deaths = overall.get("deaths", 0) or 0
                matches = overall.get("matches", 0) or 0
                kpm = overall.get("killsPerMatch", 0) or 0
                score = overall.get("score", 0) or 0
                spm = overall.get("scorePerMin", 0) or 0
                spmatch = overall.get("scorePerMatch", 0) or 0
                hours = round((overall.get("minutesPlayed", 0) or 0) / 60, 1)
                outlived = overall.get("playersOutlived", 0) or 0
                opm = round(outlived / max(matches, 1), 1)
                # Get lastModified from lifetime data (not available in windowed stats)
                _lt_overall = all_fn[name].get("stats", {}).get("all", {}).get("overall", {})
                last_on = (overall.get("lastModified", "") or _lt_overall.get("lastModified", "") or "")[:10]

                s7, s30 = perf_scores.get(name, (None, None))
                is_active = name in active_names
                kd_badge = ' <span class="rank-badge">BEST</span>' if is_active and kd == best_kd and len(all_fn) > 1 and kd > 0 else ""
                wins_badge = ' <span class="rank-badge">BEST</span>' if is_active and wins == best_wins and len(all_fn) > 1 and wins > 0 else ""
                kills_badge = ' <span class="rank-badge">BEST</span>' if is_active and kills == best_kills and len(all_fn) > 1 and kills > 0 else ""
                kpm_badge = ' <span class="rank-badge">BEST</span>' if is_active and kpm == best_kpm and len(all_fn) > 1 and kpm > 0 else ""

                circle_7d = score_circle_html(s7, "7-Day<br>Dub Score")
                circle_30d = score_circle_html(s30, "30-Day<br>Dub Score")

                is_supreme = name == fn_supreme and len(all_fn) > 1

                _supreme_ribbon = '<div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:linear-gradient(90deg,#ffd700,#ffaa00);color:#1a1a2e;padding:2px 12px;border-radius:10px;font-size:0.55rem;font-weight:800;letter-spacing:0.5px;white-space:nowrap;z-index:1;">SUPREME LEADER</div>' if is_supreme else ''
                fn_cards_html.append(f"""
                <div class="battle-card" style="position:relative;margin-top:14px;{'border-color:#ffd700;box-shadow:0 0 12px rgba(255,215,0,0.3);' if is_supreme else ''}">
                    {_supreme_ribbon}
                    <div class="player-name" style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">{data['account']['name']} {_plat_tag}</div>
                    <div class="player-platform">BP Lv {bp.get('level', '?')}</div>
                    <div style="display: flex; justify-content: center; gap: 16px; margin-bottom: 12px;">
                        {circle_7d}{circle_30d}
                    </div>
                    <div style="display: flex; justify-content: space-around; margin-bottom: 16px;">
                        <div class="big-stat"><div class="big-stat-value">{kd:.2f}</div><div class="big-stat-label">K/D</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wins:,}</div><div class="big-stat-label">Dubs</div></div>
                        <div class="big-stat"><div class="big-stat-value">{kpm:.2f}</div><div class="big-stat-label">Kills/Match</div></div>
                    </div>
                    <div class="stat-row"><span class="stat-label">Matches</span><span class="stat-value">{matches:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Dubs</span><span class="stat-highlight">{wins:,} <span style="font-size:0.8em;color:rgba(144,202,249,0.45);">{wr:.1f}%</span>{wins_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Total Kills</span><span class="stat-highlight">{kills:,}{kills_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Deaths</span><span class="stat-value">{deaths:,}</span></div>
                    <div class="stat-row"><span class="stat-label">K/D Ratio</span><span class="stat-highlight">{kd:.2f}{kd_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Kills / Match</span><span class="stat-highlight">{kpm:.2f}{kpm_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Total Score</span><span class="stat-value">{score:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Score / Min</span><span class="stat-value">{spm:.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Score / Match</span><span class="stat-value">{spmatch:.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Players Outlived</span><span class="stat-value">{outlived:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Outlived / Match</span><span class="stat-value">{opm}</span></div>
                    <div class="stat-row"><span class="stat-label">Hours Played</span><span class="stat-value">{hours:,.1f}</span></div>
                    {'<div class="stat-row"><span class="stat-label">Last Active</span><span class="stat-value">' + last_on + '</span></div>' if last_on else ''}
                    <div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08);">
                        <div style="font-size:0.6em;color:#a8a8b3;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Percentiles</div>
                        {"".join(_mini_pct_bar(sn, sv, matches) for sn, sv in [("Win%", wr), ("K/D", kd), ("K/M", kpm), ("Out/M", opm)])}
                    </div>
                </div>""")

            # Render all cards in a scrollable row
            cards_joined = "".join(fn_cards_html)
            st.html(f"""
            {card_css(accent="#e94560", badge_color="#e94560")}
            <div class="cards-scroll">{cards_joined}</div>
            """)

            # Weekly Trend (12 weeks) - right after battle cards, independent of time window
            st.markdown("---")

            @st.fragment
            def render_trend():
                TREND_METRICS = {
                    "K/D": {"key": "kd", "fmt": lambda v: round(v, 2), "axis": "K/D Ratio", "max_y": 10},
                    "Win Rate": {"key": "win_rate", "fmt": lambda v: round(v, 1), "axis": "Win Rate %"},
                    "Kills/Match": {"key": "kills_per_match", "fmt": lambda v: round(v, 2), "axis": "Kills per Match", "max_y": 10},
                    "Hours Played": {"key": "minutes_played", "fmt": lambda v: round(v / 60, 1), "axis": "Hours Played"},
                }

                _trend_opts = list(TREND_METRICS.keys())
                selected_metric = st.segmented_control(
                    "Trend Metric", _trend_opts, default=_trend_opts[0],
                    key="trend_metric_select"
                )
                if not selected_metric:
                    selected_metric = _trend_opts[0]
                metric_info = TREND_METRICS[selected_metric]

                st.markdown(f"## {selected_metric} Trend (YTD)")

                # Load from MotherDuck - fetch enough weeks for YTD + 3 seed weeks for rolling avg
                if "db_trends" not in st.session_state:
                    with st.spinner("Loading trend data..."):
                        db_data = fetch_weekly_trends(list(all_fn.keys()), num_weeks=52)
                        st.session_state.db_trends = db_data

                db_data = st.session_state.get("db_trends")
                if not db_data:
                    st.caption("Trend data not available yet.")
                    return

                st.caption("Source: MotherDuck")
                all_weeks, display_start = get_ytd_week_ranges(extra_seed_weeks=0)
                week_ranges = all_weeks

                # Build x labels with date ranges
                x_labels = []
                for i, (ws, we) in enumerate(week_ranges):
                    date_range = f"{ws.strftime('%b %-d')}-{we.strftime('%b %-d')}" if ws.month != we.month else f"{ws.strftime('%b %-d')}-{we.strftime('%-d')}"
                    if i == len(week_ranges) - 1:
                        x_labels.append(f"Last Week<br><span style='font-size:0.7em;color:#6e7681;'>{date_range}</span>")
                    elif i == len(week_ranges) - 2:
                        x_labels.append(f"2 Wks Ago<br><span style='font-size:0.7em;color:#6e7681;'>{date_range}</span>")
                    else:
                        x_labels.append(f"Wk {i + 1}<br><span style='font-size:0.7em;color:#6e7681;'>{date_range}</span>")

                tmk = metric_info["key"]
                fmt_fn = metric_info["fmt"]
                fig = go.Figure()
                for n in names:
                    player_weeks = db_data.get(n, [])
                    week_lookup = {str(w["week_start"]): w for w in player_weeks}
                    y_vals = []
                    cap = metric_info.get("max_y")
                    for ws, we in week_ranges:
                        w = week_lookup.get(str(ws))
                        if w and w.get("matches", 0) > 0 and tmk in w:
                            v = fmt_fn(w[tmk])
                            y_vals.append(min(v, cap) if cap else v)
                        else:
                            y_vals.append(None)
                    fig.add_trace(go.Scatter(
                        x=x_labels, y=y_vals, mode="lines+markers",
                        name=all_fn[n]["account"]["name"],
                        line=dict(width=3), marker=dict(size=10),
                    ))

                if "max_y" in metric_info:
                    cap_val = metric_info["max_y"]
                    y_range = [0, cap_val * 1.05]
                    # Label top tick as "10+" etc.
                    fig.update_layout(yaxis=dict(
                        tickvals=list(range(0, cap_val + 1, 2)) if cap_val <= 10 else None,
                        ticktext=[str(v) if v < cap_val else f"{cap_val}+" for v in range(0, cap_val + 1, 2)] if cap_val <= 10 else None,
                    ))
                else:
                    y_range = None
                fig.update_layout(
                    template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)", height=400,
                    yaxis_title=metric_info["axis"], yaxis_range=y_range,
                    font=dict(family="JetBrains Mono, monospace", color="white"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                    margin=dict(t=60, b=40), dragmode=False,
                )
                _lock_axes(fig)
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

            render_trend()

            # Player Deep Dive - weekly trend per player with more metrics
            st.markdown("---")

            @st.fragment
            def render_player_trend():
                PLAYER_METRICS = {
                    "Dubs": {"key": "wins", "fmt": lambda v: int(v), "axis": "Total Wins", "cumulative": True},
                    "K/D": {"key": "kd", "fmt": lambda v: round(v, 2), "axis": "K/D"},
                    "K/M": {"key": "kills_per_match", "fmt": lambda v: round(v, 2), "axis": "Kills per Match"},
                    "Win%": {"key": "win_rate", "fmt": lambda v: round(v, 1), "axis": "Win Rate %"},
                }

                col_player, col_metric = st.columns([1, 2])
                with col_player:
                    rolling_player = st.selectbox(
                        "Player", names,
                        format_func=lambda n: all_fn[n]["account"]["name"],
                        key="player_trend_select",
                    )
                _pm_opts = list(PLAYER_METRICS.keys())
                with col_metric:
                    rolling_metric = st.segmented_control(
                        "Stat", _pm_opts, default=_pm_opts[1],
                        key="player_metric_select",
                    )
                    if not rolling_metric:
                        rolling_metric = _pm_opts[1]

                metric_info = PLAYER_METRICS[rolling_metric]

                # Use weekly trend data (already loaded)
                if "db_trends" not in st.session_state:
                    _td = fetch_weekly_trends([p["name"] for p in fn_players])
                    st.session_state.db_trends = _td if _td else {}

                trends = st.session_state.db_trends
                player_weeks = trends.get(rolling_player, [])

                if not player_weeks:
                    st.caption("No weekly trend data available for this player.")
                    return

                dates = [w["week_end"] for w in player_weeks]
                if metric_info.get("cumulative"):
                    values = []
                    running = 0
                    for w in player_weeks:
                        running += w.get(metric_info["key"], 0) or 0
                        values.append(running)
                else:
                    values = [w.get(metric_info["key"], 0) or 0 for w in player_weeks]

                display_name = all_fn[rolling_player]["account"]["name"]

                fig = go.Figure()
                if not metric_info.get("cumulative") and len(values) >= 3:
                    rolling = []
                    for i in range(len(values)):
                        window = values[max(0, i - 2):i + 1]
                        rolling.append(round(sum(window) / len(window), 2))
                    plot_y = rolling
                    trace_name = f"{display_name} (3-Wk Avg)"
                else:
                    plot_y = values
                    trace_name = display_name

                fig.add_trace(go.Scatter(
                    x=dates, y=plot_y,
                    mode="lines+markers",
                    line=dict(color="#e94560", width=3),
                    marker=dict(size=6),
                    name=trace_name,
                    hovertemplate="<span style='font-size:14px'>%{x|%b %d}<br><b>" + rolling_metric + ": %{y}</b></span><extra></extra>",
                ))

                fig.update_layout(
                    title=f"{display_name} - {rolling_metric} {'(3-Wk Rolling Avg)' if not PLAYER_METRICS[rolling_metric].get('cumulative') else '(YTD)'}",
                    template="plotly_dark",
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=350,
                    yaxis_title=metric_info["axis"],
                    font=dict(family="JetBrains Mono, monospace", color="white"),
                    hoverlabel=dict(font_size=14, font_family="JetBrains Mono, monospace"),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                    margin=dict(t=60, b=40),
                    xaxis=dict(tickformat="%b %d"), dragmode=False,
                )
                _lock_axes(fig)
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

            # Charts
            st.markdown("---")
            st.markdown("## Squad Comparison")

            def _hbar(labels, values, title, fmt, accent="#e94560"):
                paired = sorted(zip(labels, values), key=lambda x: x[1])
                s_labels, s_vals = zip(*paired) if paired else ([], [])
                colors = [accent if v == max(s_vals) else "#16213e" for v in s_vals]
                texts = [fmt.format(v) for v in s_vals]
                fig = go.Figure(go.Bar(y=list(s_labels), x=list(s_vals), marker_color=colors, text=texts,
                                       textposition="outside", orientation="h", hoverinfo="none", cliponaxis=False))
                h = max(250, len(s_labels) * 40 + 80)
                _max_val = max(s_vals) if s_vals else 1
                fig.update_layout(title=title, template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  height=h, font=dict(family="JetBrains Mono, monospace", color="white"), margin=dict(l=140, r=100),
                                  xaxis=dict(range=[0, _max_val * 1.2]), dragmode=False)
                _lock_axes(fig)
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

            c1, c2 = st.columns(2)
            with c1:
                _hbar(display_names, [player_mode(n).get("kd", 0) or 0 for n in names], "K/D Ratio", "{:.2f}")
            with c2:
                _hbar(display_names, [player_mode(n).get("winRate", 0) or 0 for n in names], "Win Rate", "{:.1f}%")

            c3, c4 = st.columns(2)
            with c3:
                _hbar(display_names, [player_mode(n).get("killsPerMatch", 0) or 0 for n in names], "Kills / Match", "{:.2f}")
            with c4:
                _hbar(display_names, [player_mode(n).get("scorePerMatch", 0) or 0 for n in names], "Score / Match", "{:.0f}")

            # Radar - normalize each stat to 0-100 across squad
            st.divider()
            st.markdown("### Skill Radar")
            categories = ["K/D", "Win%", "Kills/Match", "Score/Min", "Outlived/Match", "Score/Match"]
            raw_data = {}
            for name in names:
                o = player_mode(name)
                m = max(o.get("matches", 1) or 1, 1)
                raw_data[name] = [
                    o.get("kd", 0) or 0,
                    o.get("winRate", 0) or 0,
                    o.get("killsPerMatch", 0) or 0,
                    o.get("scorePerMin", 0) or 0,
                    (o.get("playersOutlived", 0) or 0) / m,
                    o.get("scorePerMatch", 0) or 0,
                ]

            fig = go.Figure()
            for name in names:
                normalized = []
                for i in range(len(categories)):
                    all_vals = [raw_data[n][i] for n in names]
                    mn, mx = min(all_vals), max(all_vals)
                    if mx > mn:
                        normalized.append(20 + 80 * (raw_data[name][i] - mn) / (mx - mn))
                    else:
                        normalized.append(50)
                fig.add_trace(go.Scatterpolar(
                    r=normalized,
                    theta=categories, fill="toself", name=all_fn[name]["account"]["name"], opacity=0.6,
                ))
            fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, range=[0, 105], color="#a8a8b3", showticklabels=False), angularaxis=dict(color="#a8a8b3")),
                              template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=420, font=dict(family="JetBrains Mono, monospace", color="white"), dragmode=False)
            _lock_axes(fig)
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

            # Player Deep Dive
            st.markdown("---")
            render_player_trend()

            # Game Mode Breakdown
            st.markdown("---")
            st.markdown("## Game Mode Breakdown")
            mode_tab_sel = st.segmented_control("Mode", ["Overall", "Solo", "Duo", "Trio", "Squad", "LTM"], default="Overall", key="fn_mode", label_visibility="collapsed")
            if not mode_tab_sel:
                mode_tab_sel = "Overall"
            mk = mode_tab_sel.lower()
            table_data = []
            for name in names:
                s = player_mode(name, mk)
                if not s:
                    continue
                m = max(s.get("matches", 0) or 0, 1)
                table_data.append({
                    "Player": all_fn[name]["account"]["name"],
                    "Matches": f"{s.get('matches', 0) or 0:,}",
                    "Wins": f"{s.get('wins', 0) or 0:,}",
                    "Win%": f"{s.get('winRate', 0) or 0:.1f}%",
                    "K/D": f"{s.get('kd', 0) or 0:.2f}",
                    "Kills": f"{s.get('kills', 0) or 0:,}",
                    "Deaths": f"{s.get('deaths', 0) or 0:,}",
                    "K/Match": f"{s.get('killsPerMatch', 0) or 0:.2f}",
                    "Score": f"{s.get('score', 0) or 0:,}",
                    "Score/Match": f"{s.get('scorePerMatch', 0) or 0:.0f}",
                    "Score/Min": f"{s.get('scorePerMin', 0) or 0:.1f}",
                    "Outlived": f"{s.get('playersOutlived', 0) or 0:,}",
                    "Outlived/Match": f"{(s.get('playersOutlived', 0) or 0) / m:.1f}",
                    "Hours": f"{round((s.get('minutesPlayed', 0) or 0) / 60, 1):,.1f}",
                })
            if table_data:
                st.dataframe(table_data, width="stretch", hide_index=True)


            # AI Weekly Summary
            st.markdown("---")
            st.markdown("## AI Weekly Summary")

            if not HAS_ANTHROPIC:
                st.caption("Install the `anthropic` package to enable AI summaries.")
            elif not _anthropic_key:
                st.caption("Add ANTHROPIC_API_KEY to secrets to enable AI summaries.")
            else:
                st.caption("Powered by Claude. Based on the last 7 days of stats.")

                # Player context for the AI summary
                PLAYER_NOTES = {
                    "Gascan46310": "she/her pronouns",
                    "i7VoSUNZ458": "he/him. Always tease or roast this player. Find something to rib him about no matter how well he played - low win rate, dying too much, whatever you can find. Make it funny. Also always subtly hint that he needs to put in more time and grind harder.",
                }

                # Build this-week and last-week stats for WoW comparison
                summary_lines = []
                wow_lines = []
                dub_lines = []
                # Load db_trends for WoW comparison if not already loaded
                if "db_trends" not in st.session_state:
                    _dt = fetch_weekly_trends(list(all_fn.keys()), num_weeks=12)
                    st.session_state.db_trends = _dt
                db_trends_data = st.session_state.get("db_trends") or {}

                def _delta(curr, prev, fmt=".2f"):
                    diff = curr - prev
                    sign = "+" if diff >= 0 else ""
                    return f"{sign}{diff:{fmt}}"

                for name in names:
                    display = all_fn[name]["account"]["name"]
                    s7_data = db_7d.get(name)
                    if not s7_data:
                        continue
                    o7 = s7_data.get("all", {}).get("overall", {})
                    if not o7 or not o7.get("matches", 0):
                        continue
                    summary_lines.append(
                        f"{display}: {o7.get('matches', 0)} matches, "
                        f"{o7.get('kills', 0)} kills, "
                        f"K/D {o7.get('kd', 0):.2f}, "
                        f"Win Rate {o7.get('winRate', 0):.1f}%, "
                        f"Kills/Match {o7.get('killsPerMatch', 0):.2f}, "
                        f"Score/Match {o7.get('scorePerMatch', 0):.0f}, "
                        f"Players Outlived {o7.get('playersOutlived', 0)}, "
                        f"Hours {round((o7.get('minutesPlayed', 0) or 0) / 60, 1)}"
                    )
                    # Add Dub Score context
                    s7_score, s30_score = perf_scores.get(name, (None, None))
                    dub_lines.append(f"{display}: 7-Day Dub Score {s7_score or 'N/A'}, 30-Day Dub Score {s30_score or 'N/A'}")
                    # Pull last completed week from DB for WoW comparison
                    player_weeks = db_trends_data.get(name, [])
                    lw = player_weeks[-1] if player_weeks else None
                    if lw and lw.get("matches", 0) > 0:
                        wow_lines.append(
                            f"{display} week-over-week changes: K/D {_delta(o7.get('kd',0), lw.get('kd',0))} WoW, "
                            f"Win Rate {_delta(o7.get('winRate',0), lw.get('win_rate',0), '.1f')}% WoW, "
                            f"Kills/Match {_delta(o7.get('killsPerMatch',0), lw.get('kills_per_match',0))} WoW, "
                            f"Matches this week: {o7.get('matches',0)} vs last week: {lw.get('matches',0)}"
                        )

                if summary_lines:
                    stats_block = "\n".join(summary_lines)
                    dub_block = "\n".join(dub_lines)
                    wow_block = "\n".join(wow_lines) if wow_lines else "No last-week data available for comparison."
                    # Build player notes context
                    player_notes = []
                    for name in names:
                        display = all_fn[name]["account"]["name"]
                        if display in PLAYER_NOTES:
                            player_notes.append(f"- {display}: {PLAYER_NOTES[display]}")
                    notes_block = "\n".join(player_notes) if player_notes else ""
                    # Rotating styles and structures for variety
                    SUMMARY_VOICES = [
                        "Write like a late-night sports talk radio host who's way too invested in Fortnite stats.",
                        "Write like a sarcastic group chat friend who's been watching everyone's stats all week.",
                        "Write like a disappointed but loving coach giving a halftime speech.",
                        "Write like an overhyped esports commentator doing a post-match breakdown.",
                        "Write like a sports columnist filing a deadline piece for the local paper.",
                        "Write like someone giving a best man speech but about Fortnite stats instead of a wedding.",
                        "Write like a detective filing a case report on this week's Fortnite crimes.",
                        "Write like a nature documentary narrator observing the squad in their natural habitat.",
                        "Write like a weatherman but the forecast is Fortnite performance.",
                        "Write like a brutally honest fantasy football analyst evaluating roster moves.",
                        "Write like a drill sergeant reviewing troop performance after training exercises.",
                        "Write like a Yelp reviewer rating each player's week like a restaurant visit.",
                    ]
                    SUMMARY_STRUCTURES = [
                        "1. Crown the MVP with receipts (specific stats)\n2. WoW trends - rises, falls, ghosts\n3. Dub Score audit - who's coasting?\n4. Superlatives - most kills, best K/D, grindiest, most improved\n5. Roasts and shoutouts\n6. Next week's challenge",
                        "1. Power rankings - rank every active player this week, 1 sentence each\n2. Biggest glow-up and biggest fall-off (WoW comparison)\n3. Dub Score spotlight - highest and lowest\n4. The Grind Report - who put in hours, who ghosted\n5. Personalized callouts for each player\n6. Throw down a squad challenge",
                        "1. Headlines - 3 one-liner headlines summarizing the week\n2. Player of the Week breakdown with stats\n3. WoW movers - who trended up, who fell off\n4. Stat superlatives with commentary\n5. The Roast Corner - pick 2-3 players to flame\n6. Dub Score predictions for next week",
                        "1. Opening hot take that's slightly controversial\n2. MVP case - make the argument with numbers\n3. The Good, The Bad, The Missing (WoW context)\n4. Dub Score report card\n5. Award show - hand out 3-4 funny custom awards\n6. Closing challenge or dare",
                    ]

                    voice = random.choice(SUMMARY_VOICES)
                    structure = random.choice(SUMMARY_STRUCTURES)

                    col_btn, _ = st.columns([1, 2])
                    with col_btn:
                        generate_clicked = st.button("Generate AI Summary", key="ai_summary_btn", type="primary", width="stretch")

                    if generate_clicked:
                        # Always generate fresh on click (no caching)
                        st.session_state["ai_summary_result"] = None
                        with st.spinner("Generating weekly summary..."):
                            try:
                                client = anthropic.Anthropic(api_key=_anthropic_key)
                                resp = client.messages.create(
                                    model="claude-haiku-4-5-20251001",
                                    max_tokens=800,
                                    messages=[{
                                        "role": "user",
                                        "content": f"""You are a Fortnite squad analyst writing a fun weekly recap for a friend group.

VOICE/STYLE FOR THIS WEEK: {voice}

THIS WEEK'S STATS (last 7 days only):
{stats_block}

DUB SCORES (composite performance rating, 0-100 scale):
{dub_block}

WEEK-OVER-WEEK CHANGES:
{wow_block}

{f"PLAYER NOTES:{chr(10)}{notes_block}" if notes_block else ""}

Write a weekly summary (200-250 words) using this structure:
{structure}

Writing rules:
- ONLY reference the 7-day stats provided. Never mention lifetime, career, or all-time numbers.
- Use display names exactly as shown.
- Follow ALL instructions in PLAYER NOTES (pronouns, roast targets, etc.).
- Lean hard into the VOICE/STYLE. Make it feel genuinely different from a generic recap.
- When citing a WoW delta (e.g. "K/D down 0.88"), say "week over week" so the reader knows it's a comparison.
- Double-check superlative claims against the numbers. Don't say someone leads a stat if they don't.
- No corporate voice, no "let's delve into", no "it's worth noting".
- No em dashes. Use commas, periods, or hyphens instead.
- No emojis.
- Don't oversell or inflate. "Solid K/D" not "absolutely bonkers insane K/D".
- Don't use "pivotal", "landscape", "robust", "comprehensive", "witnessing", or "peak performance".
- Don't start paragraphs with "But let's talk about" or "Here's where it gets spicy".
- Be direct. Cut filler. If you can say it shorter, do.
- NEVER suggest anyone should play less or take a break. More time playing is always good. Encourage grinding."""
                                    }]
                                )
                                st.session_state["ai_summary_result"] = resp.content[0].text
                            except Exception as e:
                                st.session_state["ai_summary_result"] = f"Could not generate summary: {e}"

                    if st.session_state.get("ai_summary_result"):
                        st.markdown(f'<div class="prose-section">\n\n{st.session_state["ai_summary_result"]}\n\n</div>', unsafe_allow_html=True)
                else:
                    st.caption("No 7-day data available. Players need recent matches for the AI summary.")

            # Data Definitions
            st.markdown("---")
            with st.expander("Data Definitions"):
                st.markdown('<div class="prose-section">', unsafe_allow_html=True)
                st.markdown("""
| Stat | Definition |
|------|-----------|
| **Dub Score** | Composite 0-100 performance rating. Formula: 45% Win Rate + 30% K/D + 25% Outlived/Match, each mapped to a percentile curve, then scaled by an activity multiplier (more matches = higher confidence). |
| **K/D** | Kill/Death ratio. Kills divided by deaths (deaths = matches minus wins). |
| **Win Rate** | Percentage of matches won. |
| **Kills/Match** | Average kills per match played. |
| **Score** | Epic's composite score combining kills, placement, survival, and assists. |
| **Score/Min** | Score earned per minute of playtime. Measures efficiency. |
| **Score/Match** | Average score per match. |
| **Players Outlived** | Total players eliminated before you in each match. Higher = better survival. |
| **Outlived/Match** | Average players outlived per match. Proxy for how deep you go in games. |
| **Deaths** | Estimated as matches played minus wins (each match ends in either a win or a death). |
| **Hours Played** | Total minutes played divided by 60. |
| **BP Level** | Current Battle Pass level for the season. |

**Time Windows:**
| Window | Source | Notes |
|--------|--------|-------|
| **Lifetime** | fortnite-api.com | All-time career stats. |
| **Season** | fortnite-api.com | Current season only. |
| **Last 7 / 30 Days** | Epic Stats Proxy | Custom time window via Epic OAuth. One account powers lookups for everyone. |
| **Custom Range** | Epic Stats Proxy | Pick any start/end date. Same source as 7/30 day. |

**Input Types:** KB/Mouse, Gamepad (controller), Touch (mobile). Stats are tracked separately by Epic per input device.
""")
                st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# OVERWATCH 2
# ═══════════════════════════════════════════════════════════════════════════
elif active_game == "Overwatch 2":
    ow2_players = st.session_state.squad.get("ow2_players", [])

    if not ow2_players:
        st.info("Add OW2 players in the sidebar.")
    else:
        # Load OW2 stats from MotherDuck (populated by daily snapshot)
        if "db_ow2_cache" not in st.session_state:
            with st.spinner("Loading stats..."):
                _ow2c = fetch_ow2_cache([p["name"] for p in ow2_players])
                st.session_state.db_ow2_cache = _ow2c if _ow2c else {}

        db_ow2 = st.session_state.db_ow2_cache
        all_ow2 = {}
        _ow2_needs_live = []
        for p in ow2_players:
            name = p["name"]
            if name in db_ow2:
                all_ow2[name] = db_ow2[name]
            else:
                _ow2_needs_live.append(p)

        # Fallback: live API for players not in DB
        for p in _ow2_needs_live:
            name = p["name"]
            if name in st.session_state.ow2_cache:
                all_ow2[name] = st.session_state.ow2_cache[name]
                continue
            pid = p.get("player_id")
            if not pid:
                search = search_ow2_player(name)
                if search:
                    pid = search["player_id"]
                    p["player_id"] = pid
                    _save_and_sync(st.session_state.squad)
                else:
                    continue
            with st.spinner(f"Loading {name} stats..."):
                data = fetch_ow2_stats(pid)
                if data:
                    all_ow2[name] = data
                    st.session_state.ow2_cache[name] = data

        if not all_ow2:
            st.info("No OW2 stats available yet. Stats refresh daily at 7am ET, or players may have private profiles.")

        if all_ow2:
            # Dub Scores for all players
            ow2_dub_scores = {}
            for n, d in all_ow2.items():
                g = d.get("stats", {}).get("general", {})
                ow2_dub_scores[n] = ow2_perf_score(g)

            # Rankings - BEST badges
            active_ow2 = {n: d for n, d in all_ow2.items() if (d.get("stats", {}).get("general", {}).get("games_played", 0) or 0) > 0}
            kda_vals = {n: d.get("stats", {}).get("general", {}).get("kda", 0) or 0 for n, d in active_ow2.items()}
            wins_vals = {n: d.get("stats", {}).get("general", {}).get("games_won", 0) or 0 for n, d in active_ow2.items()}
            elims_vals = {n: d.get("stats", {}).get("general", {}).get("average", {}).get("eliminations", 0) or 0 for n, d in active_ow2.items()}
            dmg_vals = {n: d.get("stats", {}).get("general", {}).get("average", {}).get("damage", 0) or 0 for n, d in active_ow2.items()}
            best_kda = max(kda_vals.values()) if kda_vals else 0
            best_wins = max(wins_vals.values()) if wins_vals else 0
            best_elims = max(elims_vals.values()) if elims_vals else 0
            best_dmg = max(dmg_vals.values()) if dmg_vals else 0

            # Supreme Leader - highest Dub Score
            ow2_supreme = max(ow2_dub_scores, key=lambda n: ow2_dub_scores[n] or 0) if ow2_dub_scores and any(v for v in ow2_dub_scores.values() if v) else None

            # Sort cards by Dub Score (Supreme Leader first)
            ow2_card_order = sorted(all_ow2.keys(), key=lambda n: ow2_dub_scores.get(n) or 0, reverse=True)

            # OW2 mini percentile bar for battle cards
            _ow2_pct_map = {"KDA": "kda", "Win%": "winRate", "Elims": "avgElims", "Dmg": "avgDamage"}
            def _mini_pct_bar_ow2(label, value):
                curve_key = _ow2_pct_map.get(label)
                if not curve_key or curve_key not in OW2_CURVES:
                    return ""
                pct = max(0, min(100, round(value_to_percentile(value, OW2_CURVES[curve_key]))))
                color = pct_color(pct)
                bar_w = max(pct, 3)
                return f'''<div style="display:flex;align-items:center;margin-bottom:3px;">
                    <div style="width:38px;font-size:0.6em;color:#a8a8b3;flex-shrink:0;">{label}</div>
                    <div style="flex:1;background:#0f1923;border-radius:4px;height:12px;position:relative;">
                        <div style="width:{bar_w}%;height:100%;background:{color};border-radius:4px;"></div>
                    </div>
                    <div style="width:26px;text-align:right;font-size:0.55em;color:white;font-weight:700;flex-shrink:0;">{pct}</div>
                </div>'''

            # Battle Cards
            st.markdown("## Battle Cards")
            ow2_cards_html = []

            for name in ow2_card_order:
                data = all_ow2[name]
                summary = data.get("summary", {})
                stats = data.get("stats", {})
                general = stats.get("general", {})

                username = summary.get("username", name)
                title = summary.get("title", "")
                avatar = summary.get("avatar", "")
                endorsement = summary.get("endorsement", {}).get("level", "?")

                # Competitive rank
                comp = summary.get("competitive", {})
                rank_text = ""
                rank_icon = ""
                for platform_key in ["console", "pc"]:
                    pdata = comp.get(platform_key)
                    if not pdata:
                        continue
                    for role_key in ["open", "tank", "damage", "support"]:
                        rdata = pdata.get(role_key)
                        if rdata:
                            div = rdata.get("division", "").title()
                            tier = rdata.get("tier", "")
                            rk_icon = rdata.get("rank_icon", "")
                            role_label = role_key.upper() if role_key != "open" else "OPEN QUEUE"
                            if rank_text:
                                rank_text += f" | {role_label}: {div} {tier}"
                            else:
                                rank_text = f"{role_label}: {div} {tier}"
                                rank_icon = rk_icon

                games = general.get("games_played", 0) or 0
                wins = general.get("games_won", 0) or 0
                losses = general.get("games_lost", 0) or 0
                winrate = general.get("winrate", 0) or 0
                kda = general.get("kda", 0) or 0
                total = general.get("total", {})
                avg = general.get("average", {})
                hours = round((general.get("time_played", 0) or 0) / 3600, 1)

                is_active = name in active_ow2
                kda_badge = ' <span class="rank-badge">BEST</span>' if is_active and kda == best_kda and len(all_ow2) > 1 and kda > 0 else ""
                wins_badge = ' <span class="rank-badge">BEST</span>' if is_active and wins == best_wins and len(all_ow2) > 1 and wins > 0 else ""
                elims_badge = ' <span class="rank-badge">BEST</span>' if is_active and (avg.get("eliminations", 0) or 0) == best_elims and len(all_ow2) > 1 and best_elims > 0 else ""
                dmg_badge = ' <span class="rank-badge">BEST</span>' if is_active and (avg.get("damage", 0) or 0) == best_dmg and len(all_ow2) > 1 and best_dmg > 0 else ""

                avatar_html = f'<img class="player-avatar" src="{avatar}" /><br>' if avatar else ""
                rank_icon_html = f'<img class="rank-icon" src="{rank_icon}" />' if rank_icon else ""

                is_supreme = name == ow2_supreme and len(all_ow2) > 1

                dub_score = ow2_dub_scores.get(name)
                circle_html = score_circle_html(dub_score, "Dub Score")

                _supreme_ribbon_ow = '<div style="position:absolute;top:-12px;left:50%;transform:translateX(-50%);background:linear-gradient(90deg,#e94560,#c23152);color:white;padding:2px 12px;border-radius:10px;font-size:0.55rem;font-weight:800;letter-spacing:0.5px;white-space:nowrap;z-index:1;">SUPREME LEADER</div>' if is_supreme else ''
                ow2_cards_html.append(f"""
                <div class="battle-card" style="position:relative;margin-top:14px;{'border:2px solid #e94560;box-shadow:0 0 12px rgba(233,69,96,0.3);' if is_supreme else ''}">
                    {_supreme_ribbon_ow}
                    {avatar_html}
                    <div class="player-name">{username}</div>
                    <div class="player-platform">{title} | Endorsement {endorsement}</div>
                    <div class="player-platform">{rank_icon_html} {rank_text}</div>
                    <div style="display: flex; justify-content: center; gap: 16px; margin-bottom: 12px;">
                        {circle_html}
                    </div>
                    <div style="display: flex; justify-content: space-around; margin-bottom: 16px;">
                        <div class="big-stat"><div class="big-stat-value">{kda:.2f}</div><div class="big-stat-label">KDA</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wins:,}</div><div class="big-stat-label">Dubs</div></div>
                        <div class="big-stat"><div class="big-stat-value">{avg.get('eliminations', 0) or 0:.1f}</div><div class="big-stat-label">Avg Elims</div></div>
                    </div>
                    <div class="stat-row"><span class="stat-label">Games Played</span><span class="stat-value">{games:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Dubs</span><span class="stat-highlight">{wins:,} <span style="font-size:0.8em;color:rgba(249,158,26,0.45);">{winrate:.1f}%</span>{wins_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">KDA</span><span class="stat-highlight">{kda:.2f}{kda_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Eliminations</span><span class="stat-value">{total.get('eliminations', 0) or 0:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Assists</span><span class="stat-value">{total.get('assists', 0) or 0:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Deaths</span><span class="stat-value">{total.get('deaths', 0) or 0:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Elims</span><span class="stat-highlight">{avg.get('eliminations', 0) or 0:.1f}{elims_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Dmg</span><span class="stat-highlight">{avg.get('damage', 0) or 0:,.0f}{dmg_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Healing</span><span class="stat-value">{avg.get('healing', 0) or 0:,.0f}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Assists</span><span class="stat-value">{avg.get('assists', 0):.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Total Damage</span><span class="stat-value">{total.get('damage', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Total Healing</span><span class="stat-value">{total.get('healing', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Hours Played</span><span class="stat-value">{hours:,.1f}</span></div>
                    <div style="margin-top:10px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.08);">
                        <div style="font-size:0.6em;color:#a8a8b3;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Percentiles</div>
                        {"".join(_mini_pct_bar_ow2(sn, sv) for sn, sv in [("Win%", winrate), ("KDA", kda), ("Elims", avg.get('eliminations', 0) or 0), ("Dmg", avg.get('damage', 0) or 0)])}
                    </div>
                </div>""")

            ow2_cards_joined = "".join(ow2_cards_html)
            st.html(f"""
            {card_css(accent="#f99e1a", badge_color="#f99e1a")}
            <div class="cards-scroll">{ow2_cards_joined}</div>
            """)

            # Charts
            st.markdown("---")
            st.markdown("## Squad Comparison")
            ow2_names = list(all_ow2.keys())
            ow2_display = [all_ow2[n].get("summary", {}).get("username", n) for n in ow2_names]

            def _hbar_ow2(labels, values, title, fmt, accent="#f99e1a"):
                paired = sorted(zip(labels, values), key=lambda x: x[1])
                s_labels, s_vals = zip(*paired) if paired else ([], [])
                colors = [accent if v == max(s_vals) else "#16213e" for v in s_vals]
                texts = [fmt.format(v) for v in s_vals]
                fig = go.Figure(go.Bar(y=list(s_labels), x=list(s_vals), marker_color=colors, text=texts,
                                       textposition="outside", orientation="h", hoverinfo="none", cliponaxis=False))
                h = max(250, len(s_labels) * 40 + 80)
                _max_val = max(s_vals) if s_vals else 1
                fig.update_layout(title=title, template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                                  height=h, font=dict(family="JetBrains Mono, monospace", color="white"), margin=dict(l=140, r=100),
                                  xaxis=dict(range=[0, _max_val * 1.2]), dragmode=False)
                _lock_axes(fig)
                st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

            c1, c2 = st.columns(2)
            with c1:
                _hbar_ow2(ow2_display, [all_ow2[n].get("stats", {}).get("general", {}).get("kda", 0) for n in ow2_names], "KDA", "{:.2f}")
            with c2:
                _hbar_ow2(ow2_display, [all_ow2[n].get("stats", {}).get("general", {}).get("winrate", 0) for n in ow2_names], "Win Rate", "{:.1f}%")

            c3, c4 = st.columns(2)
            with c3:
                _hbar_ow2(ow2_display, [all_ow2[n].get("stats", {}).get("general", {}).get("average", {}).get("damage", 0) for n in ow2_names], "Avg Damage / Game", "{:,.0f}")
            with c4:
                _hbar_ow2(ow2_display, [all_ow2[n].get("stats", {}).get("general", {}).get("average", {}).get("healing", 0) for n in ow2_names], "Avg Healing / Game", "{:,.0f}")

            # Radar - normalize each stat to 0-100 across squad
            st.divider()
            st.markdown("### Skill Radar")
            categories = ["KDA", "Win%", "Avg Elims", "Avg Dmg (k)", "Avg Healing (k)"]
            raw_ow2 = {}
            for n in ow2_names:
                g = all_ow2[n].get("stats", {}).get("general", {})
                a = g.get("average", {})
                raw_ow2[n] = [g.get("kda", 0) or 0, g.get("winrate", 0) or 0, a.get("eliminations", 0) or 0, (a.get("damage", 0) or 0) / 1000, (a.get("healing", 0) or 0) / 1000]

            fig = go.Figure()
            for n in ow2_names:
                normalized = []
                for i in range(len(categories)):
                    all_vals = [raw_ow2[nm][i] for nm in ow2_names]
                    mn, mx = min(all_vals), max(all_vals)
                    if mx > mn:
                        normalized.append(20 + 80 * (raw_ow2[n][i] - mn) / (mx - mn))
                    else:
                        normalized.append(50)
                fig.add_trace(go.Scatterpolar(
                    r=normalized,
                    theta=categories, fill="toself", name=all_ow2[n].get("summary", {}).get("username", n), opacity=0.6,
                ))
            fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(visible=True, range=[0, 105], color="#a8a8b3", showticklabels=False), angularaxis=dict(color="#a8a8b3")),
                              template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=420, font=dict(family="JetBrains Mono, monospace", color="white"), dragmode=False)
            _lock_axes(fig)
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)

            # Role breakdown table
            st.markdown("---")

            @st.fragment
            def role_breakdown():
                st.markdown("## Role Breakdown")
                role_sel = st.segmented_control("Role", ["Overall", "Tank", "Damage", "Support"], default="Overall", key="ow2_role")
                if not role_sel:
                    role_sel = "Overall"
                table_data = []
                for n in ow2_names:
                    s = all_ow2[n].get("stats", {})
                    if role_sel == "Overall":
                        g = s.get("general", {})
                    else:
                        g = s.get("roles", {}).get(role_sel.lower(), {})
                    if not g:
                        continue
                    a = g.get("average", {})
                    t = g.get("total", {})
                    _wins = g.get('games_won', 0) or 0
                    _wr = g.get('winrate', 0) or 0
                    table_data.append({
                        "Player": all_ow2[n].get("summary", {}).get("username", n),
                        "Games": f"{g.get('games_played', 0):,}",
                        "Dubs": f"{_wins:,} ({_wr:.1f}%)",
                        "KDA": f"{g.get('kda', 0):.2f}",
                        "Elims": f"{t.get('eliminations', 0):,}",
                        "Assists": f"{t.get('assists', 0):,}",
                        "Deaths": f"{t.get('deaths', 0):,}",
                        "Avg Elims": f"{a.get('eliminations', 0):.1f}",
                        "Avg Dmg": f"{a.get('damage', 0):,.0f}",
                        "Avg Healing": f"{a.get('healing', 0):,.0f}",
                        "Hours": f"{round(g.get('time_played', 0) / 3600, 1):,.1f}",
                    })
                if table_data:
                    st.dataframe(table_data, width="stretch", hide_index=True)

            role_breakdown()

            # Hero Breakdown
            st.markdown("---")

            @st.fragment
            def hero_breakdown():
                st.markdown("## Hero Breakdown")
                hero_player = st.segmented_control("Select Player", ow2_display, default=ow2_display[0], key="ow2_hero_player")
                if not hero_player:
                    hero_player = ow2_display[0]
                hero_player_key = ow2_names[ow2_display.index(hero_player)]
                heroes = all_ow2[hero_player_key].get("stats", {}).get("heroes", {})
                if heroes:
                    hero_data = []
                    for hero_name, h in heroes.items():
                        if h.get("games_played", 0) == 0:
                            continue
                        ha = h.get("average", {})
                        ht = h.get("total", {})
                        hero_data.append({
                            "Hero": hero_name.replace("-", " ").title(),
                            "Games": h.get("games_played", 0),
                            "Win%": round(h.get("winrate", 0), 1),
                            "KDA": round(h.get("kda", 0), 2),
                            "Avg Elims": round(ha.get("eliminations", 0), 1),
                            "Avg Dmg": round(ha.get("damage", 0)),
                            "Avg Healing": round(ha.get("healing", 0)),
                            "Hours": round(h.get("time_played", 0) / 3600, 1),
                        })
                    hero_data.sort(key=lambda x: x["Games"], reverse=True)
                    st.dataframe(hero_data, width="stretch", hide_index=True)

                    # Top 5 heroes horizontal bar chart
                    top5 = sorted(hero_data[:5], key=lambda x: x["Avg Elims"])
                    if top5:
                        heroes_y = [h["Hero"] for h in top5]
                        elims_x = [h["Avg Elims"] for h in top5]
                        kda_texts = [f'{h["KDA"]:.2f}' for h in top5]
                        max_val = max(elims_x) if elims_x else 1
                        best_val = max(elims_x)
                        colors = ["#f99e1a" if v == best_val else "#16213e" for v in elims_x]
                        texts = [f"{v:.1f}  (KDA: {k})" for v, k in zip(elims_x, kda_texts)]
                        fig = go.Figure(go.Bar(
                            y=heroes_y, x=elims_x, orientation="h",
                            marker_color=colors, text=texts,
                            textposition="outside", hoverinfo="none", cliponaxis=False,
                        ))
                        h = max(250, len(top5) * 40 + 80)
                        fig.update_layout(title=f"{hero_player}'s Top 5 Heroes (Avg Elims)", template="plotly_dark",
                                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=h,
                                          font=dict(family="JetBrains Mono, monospace", color="white"),
                                          margin=dict(l=120, r=140), xaxis=dict(range=[0, max_val * 1.35]), dragmode=False)
                        _lock_axes(fig)
                        st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG)
                else:
                    st.caption("No hero data available for this player.")

            hero_breakdown()

            # OW2 AI Summary
            st.markdown("---")
            st.markdown("## AI Weekly Recap")
            if _anthropic_key and len(all_ow2) >= 2:
                # Build stats context from OW2 data
                ow2_summary_lines = []
                ow2_dub_lines = []
                for n in ow2_names:
                    d = all_ow2[n]
                    disp = d.get("summary", {}).get("username", n)
                    g = d.get("stats", {}).get("general", {})
                    if not g or not g.get("games_played"):
                        continue
                    avg = g.get("average", {})
                    tot = g.get("total", {})
                    ow2_summary_lines.append(
                        f"{disp}: {g.get('games_played',0):,} games, "
                        f"KDA {g.get('kda',0):.2f}, Win% {g.get('winrate',0):.1f}%, "
                        f"Avg Elims {avg.get('eliminations',0):.1f}, "
                        f"Avg Dmg {avg.get('damage',0):,.0f}, "
                        f"Avg Healing {avg.get('healing',0):,.0f}, "
                        f"Total Elims {tot.get('eliminations',0):,}, "
                        f"Total Deaths {tot.get('deaths',0):,}"
                    )
                    ds = ow2_perf_score(g)
                    if ds is not None:
                        ow2_dub_lines.append(f"{disp}: {ds}/100")

                if ow2_summary_lines:
                    ow2_stats_block = "\n".join(ow2_summary_lines)
                    ow2_dub_block = "\n".join(ow2_dub_lines) if ow2_dub_lines else "No Dub Scores available."

                    # OW2-specific player notes (display names differ from Fortnite)
                    OW2_PLAYER_NOTES = {
                        "GasCan": "she/her pronouns",
                        "i7vosunz458": "he/him. Always tease or roast this player. Find something to rib him about no matter how well he played - low win rate, dying too much, bad hero picks, whatever you can find. Make it funny. Also always subtly hint that he needs to put in more time and grind harder.",
                    }
                    ow2_player_notes = []
                    for n in ow2_names:
                        disp = all_ow2[n].get("summary", {}).get("username", n)
                        # Check both exact and case-insensitive matches
                        note = OW2_PLAYER_NOTES.get(disp) or OW2_PLAYER_NOTES.get(disp.lower()) or OW2_PLAYER_NOTES.get(n)
                        if note:
                            ow2_player_notes.append(f"- {disp}: {note}")
                    ow2_notes_block = "\n".join(ow2_player_notes) if ow2_player_notes else ""

                    OW2_VOICES = [
                        "Write like a late-night esports desk analyst who takes Overwatch way too seriously.",
                        "Write like a sarcastic group chat friend who's been spectating everyone's OW2 games all week.",
                        "Write like a disappointed but loving coach reviewing VODs after a losing streak.",
                        "Write like an overhyped OWL commentator doing a post-match breakdown.",
                        "Write like someone giving a best man speech but about Overwatch stats instead of a wedding.",
                        "Write like a detective investigating why the team keeps losing fights.",
                        "Write like a nature documentary narrator observing the squad's competitive habits.",
                        "Write like a brutally honest fantasy esports analyst evaluating roster moves.",
                        "Write like a drill sergeant reviewing troop performance after scrims.",
                        "Write like a Yelp reviewer rating each player's performance like a restaurant visit.",
                        "Write like a sports radio caller who's furious about tank play and won't stop talking about it.",
                        "Write like a patch notes writer but instead of hero changes, it's player performance updates.",
                    ]
                    OW2_STRUCTURES = [
                        "1. Crown the MVP with receipts (specific stats)\n2. Role check - best tank, damage, support player\n3. Dub Score audit - who's carrying, who's coasting?\n4. Superlatives - most elims, best KDA, most heals, highest damage\n5. Roasts and shoutouts\n6. Next week's challenge",
                        "1. Power rankings - rank every player, 1 sentence each\n2. Biggest carry and biggest liability\n3. Dub Score spotlight - highest and lowest\n4. The Grind Report - who put in hours, who ghosted\n5. Personalized callouts for each player\n6. Throw down a squad challenge",
                        "1. Headlines - 3 one-liner headlines summarizing the squad\n2. Player of the Week breakdown with stats\n3. Role report card - tank/damage/support grades\n4. Stat superlatives with commentary\n5. The Roast Corner - pick 2-3 players to flame\n6. Hero pick predictions or recommendations",
                        "1. Opening hot take that's slightly controversial\n2. MVP case - make the argument with numbers\n3. The Good, The Bad, The Missing\n4. Dub Score report card\n5. Award show - hand out 3-4 funny custom awards\n6. Closing challenge or dare",
                    ]

                    ow2_voice = random.choice(OW2_VOICES)
                    ow2_structure = random.choice(OW2_STRUCTURES)

                    col_btn_ow2, _ = st.columns([1, 2])
                    with col_btn_ow2:
                        ow2_gen_clicked = st.button("Generate AI Summary", key="ow2_ai_summary_btn", type="primary", width="stretch")

                    if ow2_gen_clicked:
                        st.session_state["ow2_ai_summary_result"] = None
                        with st.spinner("Generating OW2 summary..."):
                            try:
                                client = anthropic.Anthropic(api_key=_anthropic_key)
                                resp = client.messages.create(
                                    model="claude-haiku-4-5-20251001",
                                    max_tokens=800,
                                    messages=[{
                                        "role": "user",
                                        "content": f"""You are an Overwatch 2 squad analyst writing a fun recap for a friend group.

VOICE/STYLE FOR THIS RECAP: {ow2_voice}

SQUAD STATS (career totals - OW2 does not provide weekly breakdowns):
{ow2_stats_block}

DUB SCORES (composite performance rating, 0-100 scale):
{ow2_dub_block}

{f"PLAYER NOTES:{chr(10)}{ow2_notes_block}" if ow2_notes_block else ""}

Write a squad recap (200-250 words) using this structure:
{ow2_structure}

Writing rules:
- These are career/overall stats. Do NOT frame them as "this week" or "last 7 days". Say "career", "overall", or just reference the stats directly.
- Use display names exactly as shown.
- Follow ALL instructions in PLAYER NOTES (pronouns, roast targets, etc.).
- Lean hard into the VOICE/STYLE. Make it feel genuinely different from a generic recap.
- Reference OW2-specific concepts: roles (tank/damage/support), hero picks, payload, objectives, team fights.
- Double-check superlative claims against the numbers. Don't say someone leads a stat if they don't.
- No corporate voice, no "let's delve into", no "it's worth noting".
- No em dashes. Use commas, periods, or hyphens instead.
- No emojis.
- Don't oversell or inflate. "Solid KDA" not "absolutely bonkers insane KDA".
- Don't use "pivotal", "landscape", "robust", "comprehensive", "witnessing", or "peak performance".
- Don't start paragraphs with "But let's talk about" or "Here's where it gets spicy".
- Be direct. Cut filler. If you can say it shorter, do.
- NEVER suggest anyone should play less or take a break. More time playing is always good. Encourage grinding."""
                                    }]
                                )
                                st.session_state["ow2_ai_summary_result"] = resp.content[0].text
                            except Exception as e:
                                st.session_state["ow2_ai_summary_result"] = f"Could not generate summary: {e}"

                    if st.session_state.get("ow2_ai_summary_result"):
                        st.markdown(f'<div class="prose-section">\n\n{st.session_state["ow2_ai_summary_result"]}\n\n</div>', unsafe_allow_html=True)
                else:
                    st.caption("No OW2 stats available for AI summary.")
            elif not _anthropic_key:
                st.caption("AI Summary requires an Anthropic API key.")
            else:
                st.caption("Need at least 2 players for the AI summary.")

            # OW2 Data Definitions
            st.markdown("---")
            with st.expander("Data Definitions"):
                st.markdown('<div class="prose-section">', unsafe_allow_html=True)
                st.markdown("""
| Stat | Definition |
|------|-----------|
| **Dub Score** | Composite 0-100 performance rating. Formula: 40% Win Rate + 30% KDA + 15% Avg Elims + 15% Avg Damage, each mapped to a percentile curve, then scaled by an activity multiplier. |
| **KDA** | (Eliminations + Assists) / Deaths. Measures overall combat contribution. |
| **Win Rate** | Percentage of games won. |
| **Eliminations** | Final blows + assists that result in a kill. |
| **Assists** | Contributions to a kill without landing the final blow. |
| **Deaths** | Number of times you died. |
| **Damage** | Total damage dealt to enemies. |
| **Healing** | Total healing done to teammates (and self for some heroes). |
| **Endorsement** | Community rating (1-5) based on sportsmanship, shotcalling, and teamwork. |

**Roles:** Tank (frontline, space creation), Damage (eliminations), Support (healing/utility). Stats are tracked per role.

**Hero Breakdown:** Per-hero stats across all games played. Sorted by games played.

**Note:** OW2 stats are career totals only. Blizzard does not provide time-windowed stats through any public API.
""")
                st.markdown('</div>', unsafe_allow_html=True)
