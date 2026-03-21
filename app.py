import streamlit as st
import requests
import json
import os
import time
import plotly.graph_objects as go

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


def load_squad():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE) as f:
            data = json.load(f)
            data.pop("fortnite_api_key", None)
            data.pop("api_key", None)
            return data
    return {"fortnite_players": [], "ow2_players": []}


def save_squad(data):
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f, indent=2)


if "squad" not in st.session_state:
    st.session_state.squad = load_squad()
    if "players" in st.session_state.squad:
        st.session_state.squad["fortnite_players"] = st.session_state.squad.pop("players", [])
    if "ow2_players" not in st.session_state.squad:
        st.session_state.squad["ow2_players"] = []

if "fn_cache" not in st.session_state:
    st.session_state.fn_cache = {}
if "ow2_cache" not in st.session_state:
    st.session_state.ow2_cache = {}


# ── Fortnite API ─────────────────────────────────────────────────────────────
def fetch_fortnite_stats(name, account_type, api_key):
    resp = requests.get(
        FORTNITE_API,
        headers={"Authorization": api_key},
        params={"name": name, "accountType": account_type},
        timeout=15,
    )
    data = resp.json()
    if data["status"] == 200:
        return data["data"]
    return None


# ── OW2 API ──────────────────────────────────────────────────────────────────
def search_ow2_player(name):
    """Search for an OW2 player by name, return player_id if found."""
    try:
        resp = requests.get(f"{OW2_API}/players", params={"name": name}, timeout=30)
        data = resp.json()
        results = data.get("results", [])
        public = [r for r in results if r.get("is_public")]
        if public:
            return public[0]
        if results:
            return results[0]
    except Exception:
        pass
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
    st.sidebar.caption("Use the display name (not BattleTag). Profile must be public.")
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
        if st.button("Refresh Fortnite Stats", type="primary", use_container_width=True):
            st.session_state.fn_cache = {}

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

        if all_fn:
            # Rankings
            best_kd = max(d["stats"]["all"]["overall"].get("kd", 0) for d in all_fn.values())
            best_wr = max(d["stats"]["all"]["overall"].get("winRate", 0) for d in all_fn.values())
            best_kills = max(d["stats"]["all"]["overall"].get("kills", 0) for d in all_fn.values())

            # Battle Cards
            st.markdown("## Battle Cards")
            fn_cards_html = []
            for idx, (name, data) in enumerate(all_fn.items()):
                overall = data["stats"]["all"]["overall"]
                bp = data.get("battlePass", {})
                platform = next((p["platform"] for p in fn_players if p["name"] == name), "")

                kd = overall.get("kd", 0)
                wr = overall.get("winRate", 0)
                kills = overall.get("kills", 0)
                wins = overall.get("wins", 0)
                matches = overall.get("matches", 0)
                kpm = overall.get("killsPerMatch", 0)
                hours = round(overall.get("minutesPlayed", 0) / 60, 1)
                outlived = overall.get("playersOutlived", 0)
                last_on = overall.get("lastModified", "")[:10]

                kd_badge = ' <span class="rank-badge">SQUAD BEST</span>' if kd == best_kd and len(all_fn) > 1 else ""
                wr_badge = ' <span class="rank-badge">SQUAD BEST</span>' if wr == best_wr and len(all_fn) > 1 else ""
                kills_badge = ' <span class="rank-badge">SQUAD BEST</span>' if kills == best_kills and len(all_fn) > 1 else ""

                fn_cards_html.append(f"""
                <div class="battle-card">
                    <div class="player-name">{data['account']['name']}</div>
                    <div class="player-platform">{platform} | BP Level {bp.get('level', '?')}</div>
                    <div style="display: flex; justify-content: space-around; margin-bottom: 16px;">
                        <div class="big-stat"><div class="big-stat-value">{kd:.2f}</div><div class="big-stat-label">K/D</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wr:.1f}%</div><div class="big-stat-label">Win Rate</div></div>
                        <div class="big-stat"><div class="big-stat-value">{wins:,}</div><div class="big-stat-label">Wins</div></div>
                    </div>
                    <div class="stat-row"><span class="stat-label">Total Kills</span><span class="stat-highlight">{kills:,}{kills_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Kills / Match</span><span class="stat-value">{kpm:.2f}</span></div>
                    <div class="stat-row"><span class="stat-label">K/D Ratio</span><span class="stat-highlight">{kd:.2f}{kd_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-highlight">{wr:.1f}%{wr_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Matches</span><span class="stat-value">{matches:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Players Outlived</span><span class="stat-value">{outlived:,}</span></div>
                    <div class="stat-row"><span class="stat-label">Hours Played</span><span class="stat-value">{hours:,.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Last Active</span><span class="stat-value">{last_on}</span></div>
                </div>""")

            # Render all cards in a scrollable row
            cards_joined = "".join(fn_cards_html)
            num_cards = len(fn_cards_html)
            st.html(f"""
            <style>
                .cards-scroll {{ display: flex; gap: 16px; overflow-x: auto; padding: 8px 0 16px 0; }}
                .cards-scroll .battle-card {{ min-width: 280px; max-width: 340px; flex: 1 0 280px; }}
                .battle-card {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); border-radius: 16px; padding: 20px; border: 2px solid #e94560; color: white; overflow: hidden; word-wrap: break-word; box-sizing: border-box; }}
                .player-name {{ font-size: 1.1em; font-weight: 800; margin-bottom: 4px; color: #e94560; text-transform: uppercase; letter-spacing: 1px; }}
                .player-platform {{ font-size: 0.8em; color: #a8a8b3; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 1px; }}
                .stat-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
                .stat-label {{ color: #a8a8b3; font-size: 0.85em; white-space: nowrap; }}
                .stat-value {{ color: white; font-weight: 700; font-size: 0.95em; white-space: nowrap; }}
                .stat-highlight {{ color: #e94560; font-weight: 700; font-size: 0.95em; white-space: nowrap; }}
                .big-stat {{ text-align: center; padding: 8px; }}
                .big-stat-value {{ font-size: 1.8em; font-weight: 800; color: white; }}
                .big-stat-label {{ font-size: 0.7em; color: #a8a8b3; text-transform: uppercase; letter-spacing: 1px; }}
                .rank-badge {{ display: inline-block; background: #e94560; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.7em; font-weight: 700; margin-left: 4px; white-space: nowrap; }}
            </style>
            <div class="cards-scroll">{cards_joined}</div>
            """)

            # Charts
            st.markdown("---")
            st.markdown("## Squad Comparison")
            names = list(all_fn.keys())
            display_names = [all_fn[n]["account"]["name"] for n in names]

            c1, c2 = st.columns(2)
            with c1:
                kds = [all_fn[n]["stats"]["all"]["overall"].get("kd", 0) for n in names]
                colors = ["#e94560" if v == max(kds) else "#16213e" for v in kds]
                fig = go.Figure(go.Bar(x=display_names, y=kds, marker_color=colors, text=[f"{v:.2f}" for v in kds], textposition="outside"))
                fig.update_layout(title="K/D Ratio", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="K/D", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                wrs = [all_fn[n]["stats"]["all"]["overall"].get("winRate", 0) for n in names]
                colors = ["#e94560" if v == max(wrs) else "#16213e" for v in wrs]
                fig = go.Figure(go.Bar(x=display_names, y=wrs, marker_color=colors, text=[f"{v:.1f}%" for v in wrs], textposition="outside"))
                fig.update_layout(title="Win Rate", template="plotly_dark", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", yaxis_title="Win %", height=400, font=dict(color="white"))
                st.plotly_chart(fig, use_container_width=True)

            # Radar - normalize each stat to 0-100 across squad
            st.markdown("### Skill Radar")
            categories = ["K/D", "Win%", "Kills/Match", "Score/Min", "Outlived/Match"]
            raw_data = {}
            for name in names:
                o = all_fn[name]["stats"]["all"]["overall"]
                m = max(o.get("matches", 1), 1)
                raw_data[name] = [o.get("kd", 0), o.get("winRate", 0), o.get("killsPerMatch", 0), o.get("scorePerMin", 0), o.get("playersOutlived", 0) / m]

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

            # Mode table
            st.markdown("---")
            st.markdown("## Mode Breakdown")
            mode_tab_sel = st.selectbox("Select Mode", ["Overall", "Solo", "Duo", "Squad", "LTM"], key="fn_mode")
            mk = mode_tab_sel.lower()
            table_data = []
            for name in names:
                s = all_fn[name]["stats"]["all"]["overall"] if mk == "overall" else all_fn[name]["stats"]["all"].get(mk, {})
                if not s:
                    continue
                table_data.append({
                    "Player": all_fn[name]["account"]["name"],
                    "Matches": f"{s.get('matches', 0):,}", "Wins": f"{s.get('wins', 0):,}",
                    "Win%": f"{s.get('winRate', 0):.1f}%", "K/D": f"{s.get('kd', 0):.2f}",
                    "Kills": f"{s.get('kills', 0):,}", "K/Match": f"{s.get('killsPerMatch', 0):.2f}",
                    "Hours": f"{round(s.get('minutesPlayed', 0) / 60, 1):,.1f}",
                })
            if table_data:
                st.dataframe(table_data, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════
# OVERWATCH 2 TAB
# ═══════════════════════════════════════════════════════════════════════════
with ow2_tab:
    ow2_players = st.session_state.squad.get("ow2_players", [])

    if not ow2_players:
        st.info("Add OW2 players in the sidebar (switch to Overwatch 2 first).")
    else:
        if st.button("Refresh OW2 Stats", type="primary", use_container_width=True):
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
                    <div class="stat-row"><span class="stat-label">KDA</span><span class="stat-highlight">{kda:.2f}{kda_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Win Rate</span><span class="stat-highlight">{winrate:.1f}%{wr_badge}</span></div>
                    <div class="stat-row"><span class="stat-label">Eliminations</span><span class="stat-value">{total.get('eliminations', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Deaths</span><span class="stat-value">{total.get('deaths', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Damage Done</span><span class="stat-value">{total.get('damage', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Healing Done</span><span class="stat-value">{total.get('healing', 0):,}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Elims/Game</span><span class="stat-value">{avg.get('eliminations', 0):.1f}</span></div>
                    <div class="stat-row"><span class="stat-label">Avg Dmg/Game</span><span class="stat-value">{avg.get('damage', 0):,.0f}</span></div>
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
                    "Deaths": f"{t.get('deaths', 0):,}",
                    "Avg Elims": f"{a.get('eliminations', 0):.1f}",
                    "Avg Dmg": f"{a.get('damage', 0):,.0f}",
                    "Avg Healing": f"{a.get('healing', 0):,.0f}",
                })
            if table_data:
                st.dataframe(table_data, use_container_width=True, hide_index=True)
