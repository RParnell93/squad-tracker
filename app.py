import streamlit as st
import requests
import json
import os
import time
from datetime import date, datetime, timedelta
import plotly.graph_objects as go
from epic_auth import (
    load_tokens, load_device_auth, get_valid_token, lookup_account_by_name,
    stats_for_window, fetch_stats_epic, parse_raw_stats,
)

st.set_page_config(page_title="Squad Tracker", page_icon="🎮", layout="wide")

SAVE_FILE = os.path.join(os.path.dirname(__file__), "squad.json")
FORTNITE_API = "https://fortnite-api.com/v2/stats/br/v2"
OW2_API = "https://overfast-api.tekrop.fr"

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .battle-card {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        border-radius: 16px;
        padding: 20px;
        margin: 8px 0;
        border: 2px solid #e94560;
        color: white;
        position: relative;
        overflow: hidden;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }
    .battle-card.ow2 {
        border-color: #f99e1a;
    }
    .battle-card.ow2 .player-name,
    .battle-card.ow2 .stat-highlight,
    .battle-card.ow2 .mode-title {
        color: #f99e1a;
    }
    .battle-card.ow2 .rank-badge {
        background: #f99e1a;
    }
    .battle-card::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: radial-gradient(circle, rgba(233,69,96,0.1) 0%, transparent 70%);
        pointer-events: none;
    }
    .player-name {
        font-size: 1.1em;
        font-weight: 800;
        margin-bottom: 4px;
        color: #e94560;
        text-transform: uppercase;
        letter-spacing: 1px;
        word-break: break-word;
    }
    .player-platform {
        font-size: 0.8em;
        color: #a8a8b3;
        margin-bottom: 16px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .stat-row {
        display: flex;
        justify-content: space-between;
        padding: 6px 0;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }
    .stat-label {
        color: #a8a8b3;
        font-size: 0.85em;
    }
    .stat-value {
        color: white;
        font-weight: 700;
        font-size: 0.95em;
    }
    .stat-highlight {
        color: #e94560;
        font-weight: 700;
        font-size: 0.95em;
    }
    .big-stat {
        text-align: center;
        padding: 8px;
    }
    .big-stat-value {
        font-size: 1.8em;
        font-weight: 800;
        color: white;
    }
    .big-stat-label {
        font-size: 0.7em;
        color: #a8a8b3;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .rank-badge {
        display: inline-block;
        background: #e94560;
        color: white;
        padding: 2px 10px;
        border-radius: 12px;
        font-size: 0.75em;
        font-weight: 700;
        margin-left: 8px;
    }
    .mode-tab {
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 12px;
        margin-top: 12px;
    }
    .mode-title {
        font-size: 0.85em;
        color: #e94560;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 8px;
    }
    .rank-icon {
        width: 40px;
        height: 40px;
        vertical-align: middle;
        margin-right: 6px;
    }
    .player-avatar {
        width: 64px;
        height: 64px;
        border-radius: 50%;
        border: 2px solid #f99e1a;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ── State / Persistence ─────────────────────────────────────────────────────
def get_fortnite_api_key():
    """Get API key from secrets (preferred) or session state fallback."""
    try:
        key = st.secrets["FORTNITE_API_KEY"]
        if key:
            return key
    except Exception:
        pass
    return st.session_state.get("fn_api_key_input", "")


DEFAULT_FORTNITE_PLAYERS = [
    {"name": "astros44", "type": "xbl", "platform": "Xbox"},
    {"name": "zippomanjingles", "type": "psn", "platform": "PlayStation"},
    {"name": "crazy in basye", "type": "xbl", "platform": "Xbox"},
    {"name": "i7vosunz458", "type": "xbl", "platform": "Xbox"},
    {"name": "callmepot", "type": "epic", "platform": "Epic (PC)"},
    {"name": "Jbone", "type": "epic", "platform": "Epic (PC)"},
    {"name": "hailedcanvas141", "type": "xbl", "platform": "Xbox"},
    {"name": "mrfox733", "type": "xbl", "platform": "Xbox"},
]

DEFAULT_OW2_PLAYERS = [
    {"name": "bigdumpy", "player_id": "f057ab8ea67c8bb4a4a126a7d603%7C4e6a5ab09612cbe141cc5cca93318eab"},
    {"name": "meowforheals", "player_id": "ff5ba39db57e89a5ecf17be3c903a40a4a%7C675748059c6913c6fafb628a567232f0"},
    {"name": "classic", "player_id": "f152ad99a07898e0baa120a7d4%7C156e54723040e35b417b08d93b151741"},
    {"name": "Batzz", "player_id": "d05fb890a93cc9f9bea1%7Cee7e46b8d5cd02a21bd084bd5004fdbe"},
    {"name": "GasCan", "player_id": "d55fbfa9b27fd6fcb8a220a4%7C60d238a9723f0c5c425ab4c56d4579b8"},
    {"name": "GreyBeast", "player_id": "d54ca99391749abefdbd25a7d607a5%7C2b7fa8e1b80a57998ee25a9d17f99925"},
    {"name": "Jbone", "player_id": "d85ca384b63ccafcbda92e%7C508837fd0c53ce752effa237b8d205a8"},
    {"name": "Paulpummeler"},
    {"name": "i7vosunz458"},
]


def load_squad():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE) as f:
            data = json.load(f)
            data.pop("fortnite_api_key", None)
            data.pop("api_key", None)
            return data
    return {
        "fortnite_players": list(DEFAULT_FORTNITE_PLAYERS),
        "ow2_players": list(DEFAULT_OW2_PLAYERS),
    }


def save_squad(data):
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f, indent=2)


if "squad" not in st.session_state:
    st.session_state.squad = load_squad()
    if "players" in st.session_state.squad:
        st.session_state.squad["fortnite_players"] = st.session_state.squad.pop("players", [])
    # Always ensure all default players are present
    fn_existing = {p["name"] for p in st.session_state.squad.get("fortnite_players", [])}
    for p in DEFAULT_FORTNITE_PLAYERS:
        if p["name"] not in fn_existing:
            st.session_state.squad.setdefault("fortnite_players", []).append(p)
    ow2_existing = {p["name"] for p in st.session_state.squad.get("ow2_players", [])}
    for p in DEFAULT_OW2_PLAYERS:
        if p["name"] not in ow2_existing:
            st.session_state.squad.setdefault("ow2_players", []).append(p)

if "fn_cache" not in st.session_state:
    st.session_state.fn_cache = {}
if "ow2_cache" not in st.session_state:
    st.session_state.ow2_cache = {}


# ── Fortnite API ─────────────────────────────────────────────────────────────
def fetch_fortnite_stats(name, account_type, api_key):
    """Fetch both lifetime and season stats."""
    result = {}
    for window in ["lifetime", "season"]:
        resp = requests.get(
            FORTNITE_API,
            headers={"Authorization": api_key},
            params={"name": name, "accountType": account_type, "timeWindow": window},
            timeout=15,
        )
        data = resp.json()
        if data["status"] == 200:
            result[window] = data["data"]
        time.sleep(0.5)
    if result.get("lifetime"):
        # Merge: primary data is lifetime, attach season as extra key
        merged = result["lifetime"]
        if result.get("season"):
            merged["season_stats"] = result["season"].get("stats", {})
        return merged
    return None


def epic_parsed_to_mode_stats(parsed):
    """Convert Epic raw parsed stats into fortnite-api.com-style mode stats.

    Groups playlists into solo/duo/squad/overall and sums across inputs.
    Returns dict like: {"all": {"overall": {...}, "solo": {...}, ...}}
    """
    mode_map = {
        "solo": ["defaultsolo", "nobuildbrsolo", "figmentsolo"],
        "duo": ["defaultduo", "nobuildbrduos", "figmentduo"],
        "squad": ["defaultsquad", "nobuildbrsquad", "sunflowernobuildsquad",
                  "arseniccore_squads_maxfog", "punchberrynobuildsquad",
                  "mash_squads_legacy"],
    }

    totals = {}  # mode -> {metric: value}
    for mode in ["solo", "duo", "squad", "overall"]:
        totals[mode] = {}

    for input_type, playlists in parsed.items():
        for playlist, metrics in playlists.items():
            # Determine which mode this playlist belongs to
            assigned = "overall"  # everything counts toward overall
            for mode, keywords in mode_map.items():
                if any(kw in playlist for kw in keywords):
                    assigned = mode
                    break

            # Add to the assigned mode AND overall
            for target in ([assigned, "overall"] if assigned != "overall" else ["overall"]):
                for metric, val in metrics.items():
                    if metric == "lastmodified":
                        continue
                    totals[target][metric] = totals[target].get(metric, 0) + val

    # Convert to fortnite-api.com format
    result = {"all": {}}
    for mode, raw in totals.items():
        matches = raw.get("matchesplayed", 0)
        kills = raw.get("kills", 0)
        wins = raw.get("placetop1", 0)
        deaths = max(matches - wins, 0)
        result["all"][mode] = {
            "score": raw.get("score", 0),
            "scorePerMin": raw.get("score", 0) / max(raw.get("minutesplayed", 1), 1),
            "scorePerMatch": raw.get("score", 0) / max(matches, 1),
            "wins": wins,
            "top3": raw.get("placetop3", 0),
            "top5": raw.get("placetop5", 0),
            "top6": raw.get("placetop6", 0),
            "top10": raw.get("placetop10", 0),
            "top12": raw.get("placetop12", 0),
            "top25": raw.get("placetop25", 0),
            "kills": kills,
            "killsPerMin": kills / max(raw.get("minutesplayed", 1), 1),
            "killsPerMatch": kills / max(matches, 1),
            "deaths": deaths,
            "kd": kills / max(deaths, 1),
            "matches": matches,
            "winRate": wins / max(matches, 1) * 100,
            "minutesPlayed": raw.get("minutesplayed", 0),
            "playersOutlived": raw.get("playersoutlived", 0),
        }
    return result


def fetch_epic_account_ids(fn_players):
    """Look up Epic account IDs for all players. Returns {name: account_id}."""
    token = get_valid_token()
    if not token:
        return {}
    ids = {}
    for p in fn_players:
        # Use Epic display name from fortnite-api data if available
        display = p.get("epic_name") or p["name"]
        result = lookup_account_by_name(display, token)
        if result:
            ids[p["name"]] = result["id"]
        time.sleep(0.2)
    return ids


# ── OW2 API ──────────────────────────────────────────────────────────────────
def search_ow2_player(name):
    """Search for an OW2 player by name, trying multiple case variants."""
    variants = list(dict.fromkeys([name, name.title(), name.capitalize(), name.lower(), name.upper()]))
    for variant in variants:
        try:
            resp = requests.get(f"{OW2_API}/players", params={"name": variant}, timeout=30)
            data = resp.json()
            results = data.get("results", [])
            public = [r for r in results if r.get("is_public")]
            if public:
                return public[0]
            if results:
                return results[0]
        except Exception:
            pass
        time.sleep(1)
    return None


def fetch_ow2_stats(player_id):
    """Fetch summary and stats for an OW2 player."""
    result = {}
    try:
        resp = requests.get(f"{OW2_API}/players/{player_id}/summary", timeout=30)
        if resp.status_code == 200:
            result["summary"] = resp.json()
    except Exception:
        pass

    time.sleep(1)

    try:
        resp = requests.get(f"{OW2_API}/players/{player_id}/stats/summary", timeout=30)
        if resp.status_code == 200:
            result["stats"] = resp.json()
    except Exception:
        pass

    return result if result else None


# ── Sidebar ──────────────────────────────────────────────────────────────────
st.sidebar.title("Squad Setup")

game_tab = st.sidebar.radio("Game", ["Fortnite", "Overwatch 2"], horizontal=True)

if game_tab == "Fortnite":
    has_secret = False
    try:
        has_secret = bool(st.secrets["FORTNITE_API_KEY"])
    except Exception:
        pass

    if has_secret:
        st.sidebar.success("API key loaded from secrets")
    else:
        api_key_input = st.sidebar.text_input(
            "Fortnite API Key",
            value="",
            type="password",
            help="Get a free key at dash.fortnite-api.com",
        )
        st.session_state["fn_api_key_input"] = api_key_input

    st.sidebar.markdown("---")
    st.sidebar.subheader("Add Fortnite Player")
    platform_map = {"Xbox": "xbl", "PlayStation": "psn", "Epic (PC)": "epic"}

    # Quick-add presets
    preset_players = list(DEFAULT_FORTNITE_PLAYERS)
    current_names = {p["name"] for p in st.session_state.squad.get("fortnite_players", [])}
    available_presets = [p for p in preset_players if p["name"] not in current_names]

    if available_presets:
        preset_names = ["-- Select a friend --"] + [f"{p['name']} ({p['platform']})" for p in available_presets]
        preset_choice = st.sidebar.selectbox("Quick Add", preset_names, key="fn_preset")
        if st.sidebar.button("Add Selected", key="fn_preset_add", use_container_width=True):
            idx = preset_names.index(preset_choice) - 1
            if idx >= 0:
                st.session_state.squad["fortnite_players"].append(available_presets[idx])
                save_squad(st.session_state.squad)
                st.rerun()
        if st.sidebar.button("Add All Friends", key="fn_preset_all", use_container_width=True):
            st.session_state.squad["fortnite_players"].extend(available_presets)
            save_squad(st.session_state.squad)
            st.rerun()

    st.sidebar.caption("Or add manually:")
    col1, col2 = st.sidebar.columns([2, 1])
    new_name = col1.text_input("Gamertag / Epic Name", key="fn_new_name")
    new_platform = col2.selectbox("Platform", list(platform_map.keys()), key="fn_platform")

    if st.sidebar.button("Add Player", key="fn_add", use_container_width=True):
        if new_name.strip():
            st.session_state.squad["fortnite_players"].append({
                "name": new_name.strip(),
                "type": platform_map[new_platform],
                "platform": new_platform,
            })
            save_squad(st.session_state.squad)
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Fortnite Squad")
    to_remove = None
    for i, p in enumerate(st.session_state.squad.get("fortnite_players", [])):
        col_name, col_btn = st.sidebar.columns([3, 1])
        col_name.markdown(f"**{p['name']}** ({p['platform']})")
        if col_btn.button("X", key=f"fn_rm_{i}"):
            to_remove = i
    if to_remove is not None:
        st.session_state.squad["fortnite_players"].pop(to_remove)
        save_squad(st.session_state.squad)
        st.rerun()

else:  # OW2
    st.sidebar.markdown("---")
    st.sidebar.subheader("Add OW2 Player")

    ow2_preset_players = list(DEFAULT_OW2_PLAYERS)
    ow2_current = {p["name"] for p in st.session_state.squad.get("ow2_players", [])}
    ow2_available = [p for p in ow2_preset_players if p["name"] not in ow2_current]

    if ow2_available:
        ow2_preset_names = ["-- Select a friend --"] + [p["name"] for p in ow2_available]
        ow2_choice = st.sidebar.selectbox("Quick Add", ow2_preset_names, key="ow2_preset")
        if st.sidebar.button("Add Selected", key="ow2_preset_add", use_container_width=True):
            ow2_idx = ow2_preset_names.index(ow2_choice) - 1
            if ow2_idx >= 0:
                st.session_state.squad["ow2_players"].append(ow2_available[ow2_idx])
                save_squad(st.session_state.squad)
                st.rerun()
        if st.sidebar.button("Add All Friends", key="ow2_preset_all", use_container_width=True):
            st.session_state.squad["ow2_players"].extend(ow2_available)
            save_squad(st.session_state.squad)
            st.rerun()

    st.sidebar.caption("Or add manually (display name, profile must be public):")
    new_ow2 = st.sidebar.text_input("Display Name", key="ow2_new_name")

    if st.sidebar.button("Add Player", key="ow2_add", use_container_width=True):
        if new_ow2.strip():
            st.session_state.squad["ow2_players"].append({"name": new_ow2.strip()})
            save_squad(st.session_state.squad)
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.subheader("OW2 Squad")
    to_remove = None
    for i, p in enumerate(st.session_state.squad.get("ow2_players", [])):
        col_name, col_btn = st.sidebar.columns([3, 1])
        col_name.markdown(f"**{p['name']}**")
        if col_btn.button("X", key=f"ow2_rm_{i}"):
            to_remove = i
    if to_remove is not None:
        st.session_state.squad["ow2_players"].pop(to_remove)
        save_squad(st.session_state.squad)
        st.rerun()


# ── Main Area ────────────────────────────────────────────────────────────────
st.title("SQUAD TRACKER")

fn_tab, ow2_tab = st.tabs(["FORTNITE", "OVERWATCH 2"])

# ═══════════════════════════════════════════════════════════════════════════
# FORTNITE TAB
# ═══════════════════════════════════════════════════════════════════════════
with fn_tab:
    fn_players = st.session_state.squad.get("fortnite_players", [])
    fn_api_key = get_fortnite_api_key()

    if not fn_api_key:
        st.warning("Enter your Fortnite API key in the sidebar, or add it to .streamlit/secrets.toml")
        st.stop()
    if not fn_players:
        st.info("Add Fortnite players in the sidebar.")
    else:
        if st.button("Refresh Stats"):
            st.session_state.fn_cache = {}
            st.session_state.pop("epic_ids", None)
            st.session_state.pop("epic_cache", None)

        all_fn = {}
        for p in fn_players:
            cache_key = f"{p['name']}_{p['type']}"
            if cache_key in st.session_state.fn_cache:
                all_fn[p["name"]] = st.session_state.fn_cache[cache_key]
            else:
                with st.spinner(f"Loading {p['name']}..."):
                    data = fetch_fortnite_stats(p["name"], p["type"], fn_api_key)
                    if data:
                        all_fn[p["name"]] = data
                        st.session_state.fn_cache[cache_key] = data
                    else:
                        st.error(f"Could not find **{p['name']}** on {p.get('platform', p['type'])}.")

        # Resolve Epic account IDs (needed for 7/30 day stats)
        has_epic = bool(load_tokens() or load_device_auth())
        if has_epic and "epic_ids" not in st.session_state:
            with st.spinner("Resolving Epic account IDs..."):
                epic_ids = {}
                token = get_valid_token()
                if token:
                    for name, data in all_fn.items():
                        display = data.get("account", {}).get("name", name)
                        result = lookup_account_by_name(display, token)
                        if result:
                            epic_ids[name] = result["id"]
                        time.sleep(0.2)
                st.session_state.epic_ids = epic_ids
        elif not has_epic:
            st.session_state.epic_ids = {}

        if all_fn:
            epic_ids = st.session_state.get("epic_ids", {})

            # Helper to get stats for the selected time window
            def get_stats(data, name, time_window):
                if time_window == "Season" and data.get("season_stats"):
                    return data["season_stats"]
                if time_window in ("Last 7 Days", "Last 30 Days"):
                    days = 7 if time_window == "Last 7 Days" else 30
                    aid = epic_ids.get(name)
                    if not aid:
                        return None
                    cache_key = f"epic_{aid}_{days}"
                    return st.session_state.get("epic_cache", {}).get(cache_key)
                if time_window == "Custom Range":
                    aid = epic_ids.get(name)
                    if not aid:
                        return None
                    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
                    end_ts = int(datetime.combine(end_date, datetime.max.time()).timestamp())
                    cache_key = f"epic_{aid}_{start_ts}_{end_ts}"
                    return st.session_state.get("epic_cache", {}).get(cache_key)
                return data["stats"]

            # Time window toggle
            time_options = ["Lifetime", "Season"]
            if epic_ids:
                time_options += ["Last 7 Days", "Last 30 Days", "Custom Range"]
            time_window = st.radio("Time Window", time_options, horizontal=True, key="fn_time_window")

            custom_days = None
            if time_window == "Custom Range":
                col_start, col_end = st.columns(2)
                with col_start:
                    start_date = st.date_input("Start Date", value=date.today() - timedelta(days=14), key="fn_start_date")
                with col_end:
                    end_date = st.date_input("End Date", value=date.today(), key="fn_end_date")
                if start_date > end_date:
                    st.error("Start date must be before end date.")
                    st.stop()

            # Fetch Epic window stats if needed (batch all players)
            if "epic_cache" not in st.session_state:
                st.session_state.epic_cache = {}

            # Always fetch 7d and 30d stats for performance score circles
            if epic_ids:
                for score_days in (7, 30):
                    missing = [n for n in all_fn if epic_ids.get(n) and f"epic_{epic_ids[n]}_{score_days}" not in st.session_state.epic_cache]
                    if missing:
                        with st.spinner(f"Loading {score_days}-day stats..."):
                            for name in missing:
                                aid = epic_ids[name]
                                parsed = stats_for_window(aid, days=score_days)
                                cache_key = f"epic_{aid}_{score_days}"
                                if parsed:
                                    st.session_state.epic_cache[cache_key] = epic_parsed_to_mode_stats(parsed)
                                else:
                                    st.session_state.epic_cache[cache_key] = None
                                time.sleep(0.3)

            if time_window in ("Last 7 Days", "Last 30 Days") and epic_ids:
                days = 7 if time_window == "Last 7 Days" else 30
                missing = [n for n in all_fn if epic_ids.get(n) and f"epic_{epic_ids[n]}_{days}" not in st.session_state.epic_cache]
                if missing:
                    with st.spinner(f"Loading {time_window.lower()} stats..."):
                        for name in missing:
                            aid = epic_ids[name]
                            parsed = stats_for_window(aid, days=days)
                            cache_key = f"epic_{aid}_{days}"
                            if parsed:
                                st.session_state.epic_cache[cache_key] = epic_parsed_to_mode_stats(parsed)
                            else:
                                st.session_state.epic_cache[cache_key] = None
                            time.sleep(0.3)

            elif time_window == "Custom Range" and epic_ids:
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
                                from epic_auth import parse_raw_stats
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

            # Rankings
            best_kd = max((player_mode(n).get("kd", 0) or 0) for n in names)
            best_wr = max((player_mode(n).get("winRate", 0) or 0) for n in names)
            best_kills = max((player_mode(n).get("kills", 0) or 0) for n in names)
            best_kpm = max((player_mode(n).get("killsPerMatch", 0) or 0) for n in names)

            # Performance Score: composite 0-100 from K/D, Win Rate, Kills/Match percentiles
            SCORE_CURVES = {
                "kd": [
                    (0, 0), (0.5, 15), (0.8, 30), (1.0, 50), (1.3, 65),
                    (1.5, 72), (2.0, 85), (2.5, 90), (3.0, 95), (4.0, 98), (6.0, 100),
                ],
                "winRate": [
                    (0, 0), (1, 15), (2, 25), (3, 35), (5, 50), (7, 60),
                    (10, 72), (15, 82), (20, 90), (30, 95), (50, 99), (100, 100),
                ],
                "killsPerMatch": [
                    (0, 0), (0.5, 15), (1.0, 30), (1.5, 45), (2.0, 58),
                    (2.5, 68), (3.0, 78), (4.0, 88), (5.0, 93), (7.0, 98), (10.0, 100),
                ],
            }

            def _interp(value, curve):
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

            def perf_score(stats_dict):
                """Weighted composite: 40% K/D + 30% Win Rate + 30% Kills/Match."""
                if not stats_dict:
                    return None
                o = stats_dict.get("all", {}).get("overall", {})
                if not o or not o.get("matches", 0):
                    return None
                kd_pct = _interp(o.get("kd", 0) or 0, SCORE_CURVES["kd"])
                wr_pct = _interp(o.get("winRate", 0) or 0, SCORE_CURVES["winRate"])
                kpm_pct = _interp(o.get("killsPerMatch", 0) or 0, SCORE_CURVES["killsPerMatch"])
                return round(0.4 * kd_pct + 0.3 * wr_pct + 0.3 * kpm_pct)

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
                    <div style="width:72px;height:72px;border-radius:50%;background:conic-gradient({color} {deg}deg, #1a1a2e {deg}deg);display:flex;align-items:center;justify-content:center;">
                        <div style="width:58px;height:58px;border-radius:50%;background:#16213e;display:flex;flex-direction:column;align-items:center;justify-content:center;">
                            <span style="color:white;font-size:18px;font-weight:800;line-height:1;">{score_text}</span>
                        </div>
                    </div>
                    <span style="color:#a8a8b3;font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:1px;margin-top:4px;text-align:center;line-height:1.4;">{label}</span>
                </div>'''

            # Compute 7d and 30d performance scores per player
            perf_scores = {}
            for name in all_fn:
                aid = epic_ids.get(name)
                if aid:
                    s7 = st.session_state.get("epic_cache", {}).get(f"epic_{aid}_7")
                    s30 = st.session_state.get("epic_cache", {}).get(f"epic_{aid}_30")
                    perf_scores[name] = (perf_score(s7), perf_score(s30))
                else:
                    perf_scores[name] = (None, None)

            # Battle Cards
            st.markdown("## Battle Cards")
            fn_cards_html = []
            for idx, (name, data) in enumerate(all_fn.items()):
                overall = player_mode(name)
                bp = data.get("battlePass", {})
                platform = next((p["platform"] for p in fn_players if p["name"] == name), "")

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
                top10 = overall.get("top10", 0) or 0
                top25 = overall.get("top25", 0) or 0
                last_on = (overall.get("lastModified", "") or "")[:10]

                kd_badge = ' <span class="rank-badge">BEST</span>' if kd == best_kd and len(all_fn) > 1 and kd > 0 else ""
                wr_badge = ' <span class="rank-badge">BEST</span>' if wr == best_wr and len(all_fn) > 1 and wr > 0 else ""
                kills_badge = ' <span class="rank-badge">BEST</span>' if kills == best_kills and len(all_fn) > 1 and kills > 0 else ""
                kpm_badge = ' <span class="rank-badge">BEST</span>' if kpm == best_kpm and len(all_fn) > 1 and kpm > 0 else ""

                window_label = time_window.upper()

                s7, s30 = perf_scores.get(name, (None, None))
                circle_7d = score_circle_html(s7, "7-Day<br>Dub Score")
                circle_30d = score_circle_html(s30, "30-Day<br>Dub Score")

                fn_cards_html.append(f"""
                <div class="battle-card">
                    <div class="player-name">{data['account']['name']}</div>
                    <div class="player-platform">{platform} | BP Lv {bp.get('level', '?')} | {window_label}</div>
                    <div style="display: flex; justify-content: center; gap: 16px; margin-bottom: 12px;">
                        {circle_7d}{circle_30d}
                    </div>
                    <div style="display: flex; justify-content: space-around; margin-bottom: 16px;">
                        <div class="big-stat"><div class="big-stat-value">{kd:.2f}</div><div class="big-stat-label">K/D</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wr:.1f}%</div><div class="big-stat-label">Win Rate</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wins:,}</div><div class="big-stat-label">Wins</div></div>
                    </div>
                    <div class="stat-row"><span class="stat-label">Total Kills</span><span class="stat-highlight">{kills:,}{kills_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Deaths</span><span class="stat-value">{deaths:,}</span></div>
                    <div class="stat-row"><span class="stat-label">K/D Ratio</span><span class="stat-highlight">{kd:.2f}{kd_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Kills / Match</span><span class="stat-highlight">{kpm:.2f}{kpm_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-highlight">{wr:.1f}%{wr_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Matches</span><span class="stat-value">{matches:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Score</span><span class="stat-value">{score:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Score / Min</span><span class="stat-value">{spm:.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Score / Match</span><span class="stat-value">{spmatch:.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Players Outlived</span><span class="stat-value">{outlived:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Outlived / Match</span><span class="stat-value">{opm}</span></div>
                    <div class="stat-row"><span class="stat-label">Top 10s</span><span class="stat-value">{top10:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Top 25s</span><span class="stat-value">{top25:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Hours Played</span><span class="stat-value">{hours:,.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Last Active</span><span class="stat-value">{last_on}</span></div>
                </div>""")

            # Render all cards in a scrollable row
            cards_joined = "".join(fn_cards_html)
            st.html(f"""
            <style>
                .cards-scroll {{ display: flex; gap: 16px; overflow-x: auto; padding: 8px 0 16px 0; }}
                .cards-scroll .battle-card {{ min-width: 280px; max-width: 340px; flex: 1 0 280px; }}
                .battle-card {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); border-radius: 16px; padding: 20px; border: 2px solid #e94560; color: white; overflow: hidden; word-wrap: break-word; box-sizing: border-box; }}
                .player-name {{ font-size: 1.1em; font-weight: 800; margin-bottom: 4px; color: #e94560; text-transform: uppercase; letter-spacing: 1px; }}
                .player-platform {{ font-size: 0.8em; color: #a8a8b3; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }}
                .stat-row {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
                .stat-label {{ color: #a8a8b3; font-size: 0.82em; white-space: nowrap; }}
                .stat-value {{ color: white; font-weight: 700; font-size: 0.9em; white-space: nowrap; }}
                .stat-highlight {{ color: #e94560; font-weight: 700; font-size: 0.9em; white-space: nowrap; }}
                .big-stat {{ text-align: center; padding: 8px; }}
                .big-stat-value {{ font-size: 1.8em; font-weight: 800; color: white; }}
                .big-stat-label {{ font-size: 0.7em; color: #a8a8b3; text-transform: uppercase; letter-spacing: 1px; }}
                .rank-badge {{ display: inline-block; background: #e94560; color: white; padding: 2px 6px; border-radius: 12px; font-size: 0.65em; font-weight: 700; margin-left: 4px; white-space: nowrap; }}
            </style>
            <div class="cards-scroll">{cards_joined}</div>
            """)

            # Weekly Trend (12 weeks) - right after battle cards, independent of time window
            if epic_ids:
                st.markdown("---")

                @st.fragment
                def render_trend():
                    TREND_METRICS = {
                        "K/D": {"key": "kd", "fmt": lambda v: round(v, 2), "axis": "K/D Ratio"},
                        "Win Rate": {"key": "winRate", "fmt": lambda v: round(v, 1), "axis": "Win Rate %"},
                        "Kills/Match": {"key": "killsPerMatch", "fmt": lambda v: round(v, 2), "axis": "Kills per Match"},
                        "Score/Min": {"key": "scorePerMin", "fmt": lambda v: round(v, 1), "axis": "Score per Minute"},
                        "Score/Match": {"key": "scorePerMatch", "fmt": lambda v: round(v, 1), "axis": "Score per Match"},
                        "Top 10": {"key": "top10", "fmt": lambda v: int(v), "axis": "Top 10 Finishes"},
                        "Top 25": {"key": "top25", "fmt": lambda v: int(v), "axis": "Top 25 Finishes"},
                        "Hours Played": {"key": "minutesPlayed", "fmt": lambda v: round(v / 60, 1), "axis": "Hours Played"},
                    }

                    col_metric, _ = st.columns([1, 3])
                    with col_metric:
                        selected_metric = st.selectbox(
                            "Trend Metric", list(TREND_METRICS.keys()), index=0,
                            key="trend_metric_select"
                        )
                    metric_info = TREND_METRICS[selected_metric]

                    st.markdown(f"## {selected_metric} Trend (Past 12 Weeks)")
                    st.caption("Weekly values from Epic stats proxy. Each point is one week. Independent of the time window filter above.")

                    def week_label(i):
                        if i == 0:
                            return "This Week"
                        if i == 1:
                            return "Last Week"
                        return f"Wk {12 - i}"
                    trend_windows = [(week_label(i), i * 7, (i + 1) * 7) for i in range(12)]
                    now_ts = int(time.time())

                    if "trend_cache" not in st.session_state:
                        st.session_state.trend_cache = {}

                    trend_missing = False
                    for n in names:
                        aid = epic_ids.get(n)
                        if not aid:
                            continue
                        for lbl, d_s, d_e in trend_windows:
                            if f"trend_{aid}_{d_s}_{d_e}" not in st.session_state.trend_cache:
                                trend_missing = True
                                break

                    if trend_missing:
                        with st.spinner("Loading trend data..."):
                            for n in names:
                                aid = epic_ids.get(n)
                                if not aid:
                                    continue
                                for lbl, d_s, d_e in trend_windows:
                                    ck = f"trend_{aid}_{d_s}_{d_e}"
                                    if ck in st.session_state.trend_cache:
                                        continue
                                    s_ts = now_ts - (d_e * 86400)
                                    e_ts = now_ts - (d_s * 86400)
                                    raw = fetch_stats_epic(aid, s_ts, e_ts)
                                    if raw:
                                        parsed = parse_raw_stats(raw)
                                        ms = epic_parsed_to_mode_stats(parsed)
                                        o = ms.get("all", {}).get("overall", {})
                                        st.session_state.trend_cache[ck] = {
                                            "kd": o.get("kd", 0),
                                            "kills": o.get("kills", 0),
                                            "matches": o.get("matches", 0),
                                            "winRate": o.get("winRate", 0),
                                            "killsPerMatch": o.get("killsPerMatch", 0),
                                            "scorePerMin": o.get("scorePerMin", 0),
                                            "scorePerMatch": o.get("scorePerMatch", 0),
                                            "top10": o.get("top10", 0),
                                            "top25": o.get("top25", 0),
                                            "minutesPlayed": o.get("minutesPlayed", 0),
                                        }
                                    else:
                                        st.session_state.trend_cache[ck] = None
                                    time.sleep(0.3)

                    fig = go.Figure()
                    x_labels = [w[0] for w in reversed(trend_windows)]
                    tmk = metric_info["key"]
                    fmt_fn = metric_info["fmt"]
                    for n in names:
                        aid = epic_ids.get(n)
                        if not aid:
                            continue
                        y_vals = []
                        for lbl, d_s, d_e in reversed(trend_windows):
                            ck = f"trend_{aid}_{d_s}_{d_e}"
                            cached = st.session_state.trend_cache.get(ck)
                            if cached and cached.get("matches", 0) > 0 and tmk in cached:
                                y_vals.append(fmt_fn(cached[tmk]))
                            else:
                                y_vals.append(None)
                        fig.add_trace(go.Scatter(
                            x=x_labels, y=y_vals, mode="lines+markers",
                            name=all_fn[n]["account"]["name"],
                            line=dict(width=3), marker=dict(size=10),
                        ))
                    fig.update_layout(
                        template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)", height=450,
                        yaxis_title=metric_info["axis"], font=dict(color="white"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    )
                    st.plotly_chart(fig, use_container_width=True)

                render_trend()

            # Percentile Rankings (click to expand per player)
            st.markdown("---")
            st.markdown("## Percentile Rankings")
            st.caption("Estimated global percentiles based on community benchmarks. Higher = better among all Fortnite players.")

            # Community-sourced percentile lookup tables
            # Based on FortniteTracker tier data and community analysis
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

            # Single player selector for percentile view
            pct_col, _ = st.columns([1, 3])
            with pct_col:
                pct_player = st.selectbox(
                    "Select Player", names,
                    format_func=lambda n: all_fn[n]["account"]["name"],
                    key="pct_player_select"
                )

            o = player_mode(pct_player)
            if o and o.get("matches", 0):
                display = all_fn[pct_player]["account"]["name"]
                m = max(o.get("matches", 1) or 1, 1)

                stats_for_pct = {
                    "K/D": o.get("kd", 0) or 0,
                    "Win Rate": o.get("winRate", 0) or 0,
                    "Kills/Match": o.get("killsPerMatch", 0) or 0,
                    "Score/Match": o.get("scorePerMatch", 0) or 0,
                    "Outlived/Match": (o.get("playersOutlived", 0) or 0) / m,
                }

                bars_html = ""
                for stat_name, stat_val in stats_for_pct.items():
                    pct = value_to_percentile(stat_val, PERCENTILE_CURVES[stat_name])
                    pct = max(0, min(100, round(pct)))
                    color = pct_color(pct)
                    # Cap display width so circle doesn't overflow
                    bar_width = min(pct, 96)
                    if stat_name == "Win Rate":
                        val_str = f"{stat_val:.1f}%"
                    elif stat_name in ("K/D", "Kills/Match"):
                        val_str = f"{stat_val:.2f}"
                    else:
                        val_str = f"{stat_val:.1f}"

                    bars_html += f"""
                    <div style="display:flex;align-items:center;margin-bottom:8px;">
                        <div style="width:110px;font-size:0.8em;color:#a8a8b3;flex-shrink:0;">{stat_name}</div>
                        <div style="flex:1;background:#1a1a2e;border-radius:8px;height:24px;position:relative;">
                            <div style="width:{bar_width}%;height:100%;background:{color};border-radius:8px;"></div>
                            <div style="position:absolute;left:{bar_width}%;top:50%;transform:translate(-50%,-50%);background:{color};color:white;font-size:0.7em;font-weight:800;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;border:2px solid white;">{pct}</div>
                        </div>
                        <div style="width:55px;text-align:right;font-size:0.8em;color:white;font-weight:700;flex-shrink:0;padding-left:8px;">{val_str}</div>
                    </div>"""

                st.html(f"""
                <div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 50%,#0f3460 100%);border-radius:12px;padding:16px;border:1px solid #e94560;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                        <span style="color:#a8a8b3;font-size:0.7em;text-transform:uppercase;letter-spacing:1px;">POOR</span>
                        <span style="color:#a8a8b3;font-size:0.7em;text-transform:uppercase;letter-spacing:1px;">AVERAGE</span>
                        <span style="color:#a8a8b3;font-size:0.7em;text-transform:uppercase;letter-spacing:1px;">GREAT</span>
                    </div>
                    {bars_html}
                    <div style="margin-top:8px;font-size:0.65em;color:#666;">Estimated percentiles based on community benchmarks. Not official Epic data.</div>
                </div>
                """)

            # Charts
            st.markdown("---")
            st.markdown("## Squad Comparison")

            c1, c2 = st.columns(2)
            with c1:
                kds = [player_mode(n).get("kd", 0) or 0 for n in names]
                colors = ["#e94560" if v == max(kds) else "#16213e" for v in kds]
                fig = go.Figure(go.Bar(x=display_names, y=kds, marker_color=colors, text=[f"{v:.2f}" for v in kds], textposition="outside"))
                fig.update_layout(title="K/D Ratio", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="K/D", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                wrs = [player_mode(n).get("winRate", 0) or 0 for n in names]
                colors = ["#e94560" if v == max(wrs) else "#16213e" for v in wrs]
                fig = go.Figure(go.Bar(x=display_names, y=wrs, marker_color=colors, text=[f"{v:.1f}%" for v in wrs], textposition="outside"))
                fig.update_layout(title="Win Rate", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="Win %", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            c3, c4 = st.columns(2)
            with c3:
                kpms = [player_mode(n).get("killsPerMatch", 0) or 0 for n in names]
                colors = ["#e94560" if v == max(kpms) else "#16213e" for v in kpms]
                fig = go.Figure(go.Bar(x=display_names, y=kpms, marker_color=colors, text=[f"{v:.2f}" for v in kpms], textposition="outside"))
                fig.update_layout(title="Kills / Match", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="Kills", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)
            with c4:
                spms = [player_mode(n).get("scorePerMatch", 0) or 0 for n in names]
                colors = ["#e94560" if v == max(spms) else "#16213e" for v in spms]
                fig = go.Figure(go.Bar(x=display_names, y=spms, marker_color=colors, text=[f"{v:.0f}" for v in spms], textposition="outside"))
                fig.update_layout(title="Score / Match", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="Score", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            # Radar - normalize each stat to 0-100 across squad
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
                              template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=500, font=dict(color="white"))
            st.plotly_chart(fig, use_container_width=True)

            # Mode Breakdown
            st.markdown("---")
            st.markdown("## Mode Breakdown")
            mode_tab_sel = st.selectbox("Select Mode", ["Overall", "Solo", "Duo", "Squad", "LTM"], key="fn_mode")
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
                    "Top 10": f"{s.get('top10', 0) or 0:,}",
                    "Top 25": f"{s.get('top25', 0) or 0:,}",
                    "Hours": f"{round((s.get('minutesPlayed', 0) or 0) / 60, 1):,.1f}",
                })
            if table_data:
                st.dataframe(table_data, use_container_width=True, hide_index=True)


            # Data Definitions
            st.markdown("---")
            with st.expander("Data Definitions"):
                st.markdown("""
| Stat | Definition |
|------|-----------|
| **K/D** | Kill/Death ratio. Kills divided by deaths (deaths = matches minus wins). |
| **Win Rate** | Percentage of matches won. |
| **Kills/Match** | Average kills per match played. |
| **Score** | Epic's composite score combining kills, placement, survival, and assists. |
| **Score/Min** | Score earned per minute of playtime. Measures efficiency. |
| **Score/Match** | Average score per match. |
| **Players Outlived** | Total players eliminated before you in each match. Higher = better survival. |
| **Outlived/Match** | Average players outlived per match. Proxy for how deep you go in games. |
| **Top 10 / Top 25** | Number of matches finishing in the top 10 or top 25. |
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


# ═══════════════════════════════════════════════════════════════════════════
# OVERWATCH 2 TAB
# ═══════════════════════════════════════════════════════════════════════════
with ow2_tab:
    ow2_players = st.session_state.squad.get("ow2_players", [])

    if not ow2_players:
        st.info("Add OW2 players in the sidebar (switch to Overwatch 2 first).")
    else:
        if st.button("Refresh Stats", key="ow2_refresh"):
            st.session_state.ow2_cache = {}

        all_ow2 = {}
        for p in ow2_players:
            cache_key = p["name"]
            if cache_key in st.session_state.ow2_cache:
                all_ow2[p["name"]] = st.session_state.ow2_cache[cache_key]
            else:
                with st.spinner(f"Searching for {p['name']}... (OW2 API can be slow)"):
                    # Use cached player_id if we have it
                    pid = p.get("player_id")
                    if not pid:
                        search = search_ow2_player(p["name"])
                        if search:
                            pid = search["player_id"]
                            p["player_id"] = pid
                            save_squad(st.session_state.squad)
                        else:
                            st.error(f"Could not find **{p['name']}** on OW2. Make sure profile is public and name is exact.")
                            continue

                with st.spinner(f"Loading {p['name']} stats..."):
                    data = fetch_ow2_stats(pid)
                    if data:
                        all_ow2[p["name"]] = data
                        st.session_state.ow2_cache[cache_key] = data
                    else:
                        st.error(f"Could not load stats for **{p['name']}**. Profile may be private.")

        if all_ow2:
            # Rankings
            kda_vals = {n: d.get("stats", {}).get("general", {}).get("kda", 0) for n, d in all_ow2.items()}
            wr_vals = {n: d.get("stats", {}).get("general", {}).get("winrate", 0) for n, d in all_ow2.items()}
            best_kda = max(kda_vals.values()) if kda_vals else 0
            best_wr = max(wr_vals.values()) if wr_vals else 0

            # Battle Cards
            st.markdown("## Battle Cards")
            ow2_cards_html = []

            for idx, (name, data) in enumerate(all_ow2.items()):
                summary = data.get("summary", {})
                stats = data.get("stats", {})
                general = stats.get("general", {})
                roles = stats.get("roles", {})

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

                games = general.get("games_played", 0)
                wins = general.get("games_won", 0)
                losses = general.get("games_lost", 0)
                winrate = general.get("winrate", 0)
                kda = general.get("kda", 0)
                total = general.get("total", {})
                avg = general.get("average", {})
                hours = round(general.get("time_played", 0) / 3600, 1)

                kda_badge = ' <span class="rank-badge">SQUAD BEST</span>' if kda == best_kda and len(all_ow2) > 1 else ""
                wr_badge = ' <span class="rank-badge">SQUAD BEST</span>' if winrate == best_wr and len(all_ow2) > 1 else ""

                avatar_html = f'<img class="player-avatar" src="{avatar}" /><br>' if avatar else ""
                rank_icon_html = f'<img class="rank-icon" src="{rank_icon}" />' if rank_icon else ""

                ow2_cards_html.append(f"""
                <div class="battle-card">
                    {avatar_html}
                    <div class="player-name">{username}</div>
                    <div class="player-platform">{title} | Endorsement {endorsement}</div>
                    <div class="player-platform">{rank_icon_html} {rank_text}</div>

                    <div style="display: flex; justify-content: space-around; margin-bottom: 16px;">
                        <div class="big-stat"><div class="big-stat-value">{kda:.2f}</div><div class="big-stat-label">KDA</div></div>
                        <div class="big-stat"><div class="big-stat-value">{winrate:.1f}%</div><div class="big-stat-label">Win Rate</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wins:,}</div><div class="big-stat-label">Wins</div></div>
                    </div>

                    <div class="stat-row"><span class="stat-label">Games Played</span><span class="stat-value">{games:,}</span></div>
                    <div class="stat-row"><span class="stat-label">W / L</span><span class="stat-value">{wins:,} / {losses:,}</span></div>
                    <div class="stat-row"><span class="stat-label">KDA</span><span class="stat-highlight">{kda:.2f}{kda_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-highlight">{winrate:.1f}%{wr_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Eliminations</span><span class="stat-value">{total.get('eliminations', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Assists</span><span class="stat-value">{total.get('assists', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Deaths</span><span class="stat-value">{total.get('deaths', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Damage Done</span><span class="stat-value">{total.get('damage', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Healing Done</span><span class="stat-value">{total.get('healing', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Elims/Game</span><span class="stat-value">{avg.get('eliminations', 0):.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Assists/Game</span><span class="stat-value">{avg.get('assists', 0):.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Dmg/Game</span><span class="stat-value">{avg.get('damage', 0):,.0f}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Healing/Game</span><span class="stat-value">{avg.get('healing', 0):,.0f}</span></div>
                    <div class="stat-row"><span class="stat-label">Hours Played</span><span class="stat-value">{hours:,.1f}</span></div>
                </div>""")

            ow2_cards_joined = "".join(ow2_cards_html)
            st.html(f"""
            <style>
                .cards-scroll {{ display: flex; gap: 16px; overflow-x: auto; padding: 8px 0 16px 0; }}
                .cards-scroll .battle-card {{ min-width: 280px; max-width: 340px; flex: 1 0 280px; }}
                .battle-card {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); border-radius: 16px; padding: 20px; border: 2px solid #f99e1a; color: white; overflow: hidden; word-wrap: break-word; box-sizing: border-box; }}
                .player-name {{ font-size: 1.1em; font-weight: 800; margin-bottom: 4px; color: #f99e1a; text-transform: uppercase; letter-spacing: 1px; }}
                .player-platform {{ font-size: 0.8em; color: #a8a8b3; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }}
                .stat-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
                .stat-label {{ color: #a8a8b3; font-size: 0.85em; white-space: nowrap; }}
                .stat-value {{ color: white; font-weight: 700; font-size: 0.95em; white-space: nowrap; }}
                .stat-highlight {{ color: #f99e1a; font-weight: 700; font-size: 0.95em; white-space: nowrap; }}
                .big-stat {{ text-align: center; padding: 8px; }}
                .big-stat-value {{ font-size: 1.8em; font-weight: 800; color: white; }}
                .big-stat-label {{ font-size: 0.7em; color: #a8a8b3; text-transform: uppercase; letter-spacing: 1px; }}
                .rank-badge {{ display: inline-block; background: #f99e1a; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.7em; font-weight: 700; margin-left: 4px; white-space: nowrap; }}
                .player-avatar {{ width: 64px; height: 64px; border-radius: 50%; border: 2px solid #f99e1a; margin-bottom: 8px; }}
                .rank-icon {{ width: 40px; height: 40px; vertical-align: middle; margin-right: 6px; }}
            </style>
            <div class="cards-scroll">{ow2_cards_joined}</div>
            """)

            # Charts
            st.markdown("---")
            st.markdown("## Squad Comparison")
            ow2_names = list(all_ow2.keys())
            ow2_display = [all_ow2[n].get("summary", {}).get("username", n) for n in ow2_names]

            c1, c2 = st.columns(2)
            with c1:
                kdas = [all_ow2[n].get("stats", {}).get("general", {}).get("kda", 0) for n in ow2_names]
                colors = ["#f99e1a" if v == max(kdas) else "#16213e" for v in kdas]
                fig = go.Figure(go.Bar(x=ow2_display, y=kdas, marker_color=colors, text=[f"{v:.2f}" for v in kdas], textposition="outside"))
                fig.update_layout(title="KDA", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                wrs = [all_ow2[n].get("stats", {}).get("general", {}).get("winrate", 0) for n in ow2_names]
                colors = ["#f99e1a" if v == max(wrs) else "#16213e" for v in wrs]
                fig = go.Figure(go.Bar(x=ow2_display, y=wrs, marker_color=colors, text=[f"{v:.1f}%" for v in wrs], textposition="outside"))
                fig.update_layout(title="Win Rate", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            c3, c4 = st.columns(2)
            with c3:
                dmgs = [all_ow2[n].get("stats", {}).get("general", {}).get("average", {}).get("damage", 0) for n in ow2_names]
                colors = ["#f99e1a" if v == max(dmgs) else "#16213e" for v in dmgs]
                fig = go.Figure(go.Bar(x=ow2_display, y=dmgs, marker_color=colors, text=[f"{v:,.0f}" for v in dmgs], textposition="outside"))
                fig.update_layout(title="Avg Damage / Game", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)
            with c4:
                heals = [all_ow2[n].get("stats", {}).get("general", {}).get("average", {}).get("healing", 0) for n in ow2_names]
                colors = ["#f99e1a" if v == max(heals) else "#16213e" for v in heals]
                fig = go.Figure(go.Bar(x=ow2_display, y=heals, marker_color=colors, text=[f"{v:,.0f}" for v in heals], textposition="outside"))
                fig.update_layout(title="Avg Healing / Game", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            # Radar - normalize each stat to 0-100 across squad
            st.markdown("### Skill Radar")
            categories = ["KDA", "Win%", "Avg Elims", "Avg Dmg (k)", "Avg Healing (k)"]
            raw_ow2 = {}
            for n in ow2_names:
                g = all_ow2[n].get("stats", {}).get("general", {})
                a = g.get("average", {})
                raw_ow2[n] = [g.get("kda", 0), g.get("winrate", 0), a.get("eliminations", 0), a.get("damage", 0) / 1000, a.get("healing", 0) / 1000]

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
                              template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=500, font=dict(color="white"))
            st.plotly_chart(fig, use_container_width=True)

            # Role breakdown table
            st.markdown("---")
            st.markdown("## Role Breakdown")
            role_sel = st.selectbox("Select View", ["Overall", "Tank", "Damage", "Support"], key="ow2_role")
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
                table_data.append({
                    "Player": all_ow2[n].get("summary", {}).get("username", n),
                    "Games": f"{g.get('games_played', 0):,}",
                    "Win%": f"{g.get('winrate', 0):.1f}%",
                    "KDA": f"{g.get('kda', 0):.2f}",
                    "Elims": f"{t.get('eliminations', 0):,}",
                    "Assists": f"{t.get('assists', 0):,}",
                    "Deaths": f"{t.get('deaths', 0):,}",
                    "Dmg": f"{t.get('damage', 0):,}",
                    "Healing": f"{t.get('healing', 0):,}",
                    "Avg Elims": f"{a.get('eliminations', 0):.1f}",
                    "Avg Assists": f"{a.get('assists', 0):.1f}",
                    "Avg Dmg": f"{a.get('damage', 0):,.0f}",
                    "Avg Healing": f"{a.get('healing', 0):,.0f}",
                    "Hours": f"{round(g.get('time_played', 0) / 3600, 1):,.1f}",
                })
            if table_data:
                st.dataframe(table_data, use_container_width=True, hide_index=True)

            # Hero Breakdown
            st.markdown("---")
            st.markdown("## Hero Breakdown")
            hero_player = st.selectbox("Select Player", ow2_display, key="ow2_hero_player")
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
                st.dataframe(hero_data, use_container_width=True, hide_index=True)

                # Top 5 heroes bar chart
                top5 = hero_data[:5]
                if top5:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(name="Avg Elims", x=[h["Hero"] for h in top5], y=[h["Avg Elims"] for h in top5], marker_color="#f99e1a"))
                    fig.add_trace(go.Bar(name="KDA", x=[h["Hero"] for h in top5], y=[h["KDA"] for h in top5], marker_color="#e94560"))
                    fig.update_layout(title=f"{hero_player}'s Top 5 Heroes", barmode="group", template="plotly_dark",
                                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", height=400, font=dict(color="white"))
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No hero data available for this player.")

            # OW2 Data Definitions
            st.markdown("---")
            with st.expander("Data Definitions"):
                st.markdown("""
| Stat | Definition |
|------|-----------|
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
