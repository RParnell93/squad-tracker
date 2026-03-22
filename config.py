import os

SAVE_FILE = os.path.join(os.path.dirname(__file__), "squad.json")
FORTNITE_API = "https://fortnite-api.com/v2/stats/br/v2"
OW2_API = "https://overfast-api.tekrop.fr"

DEFAULT_FORTNITE_PLAYERS = [
    {"name": "astros44", "type": "xbl", "platform": "Xbox", "epic_name": "TLP_ReMuS"},
    {"name": "zippomanjingles", "type": "psn", "platform": "PlayStation", "epic_name": "Zippomanjingles"},
    {"name": "crazy in basye", "type": "xbl", "platform": "Xbox", "epic_name": "Crazy in Basye"},
    {"name": "i7vosunz458", "type": "xbl", "platform": "Xbox", "epic_name": "i7VoSUNZ458"},
    {"name": "callmepot", "type": "epic", "platform": "Epic (PC)", "epic_name": "callmepot"},
    {"name": "mrfox733", "type": "xbl", "platform": "Xbox", "epic_name": "mrfox733"},
    {"name": "gascan46310", "type": "xbl", "platform": "Xbox", "epic_name": "Gascan46310", "epic_id": "caf1138b62b845108deaa20827a24777"},
    {"name": "harpbaby", "type": "epic", "platform": "Nintendo Switch", "epic_name": "Harpbaby"},
]

DEFAULT_OW2_PLAYERS = [
    {"name": "bigdumpy", "player_id": "f057ab8ea67c8bb4a4a126a7d603%7C4e6a5ab09612cbe141cc5cca93318eab"},
    {"name": "meowforheals", "player_id": "ff5ba39db57e89a5ecf17be3c903a40a4a%7C675748059c6913c6fafb628a567232f0"},
    {"name": "classic", "player_id": "f152ad99a07898e0baa120a7d4%7C156e54723040e35b417b08d93b151741"},
    {"name": "Batzz", "player_id": "d05fb890a93cc9f9bea1%7Cee7e46b8d5cd02a21bd084bd5004fdbe"},
    {"name": "GasCan", "player_id": "d55fbfa9b27fd6fcb8a220a4%7C60d238a9723f0c5c425ab4c56d4579b8"},
    {"name": "GreyBeast", "player_id": "d54ca99391749abefdbd25a7d607a5%7C2b7fa8e1b80a57998ee25a9d17f99925"},
    {"name": "i7vosunz458"},
    {"name": "junkrob", "player_id": "JunkRob-1142"},
]

# Shared card CSS used in st.html() blocks (scoped) - parameterized by accent color
def card_css(accent="#e94560", badge_color="#e94560"):
    return f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&display=swap');
        .cards-scroll {{ font-family: 'JetBrains Mono', monospace; }}
        .cards-scroll {{ display: flex; gap: 16px; overflow-x: auto; padding: 8px 0 16px 0; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; }}
        .cards-scroll .battle-card {{ min-width: 280px; max-width: 340px; flex: 1 0 280px; scroll-snap-align: start; }}
        .battle-card {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%); border-radius: 16px; padding: 20px; border: 2px solid {accent}; color: white; overflow: visible; word-wrap: break-word; box-sizing: border-box; font-family: 'JetBrains Mono', monospace; }}
        .battle-card.supreme-red {{ border-color: #e94560 !important; box-shadow: 0 0 12px rgba(233,69,96,0.3); }}
        .player-name {{ font-size: 1.1em; font-weight: 800; margin-bottom: 4px; color: {accent}; text-transform: uppercase; letter-spacing: 0.5px; }}
        .player-platform {{ font-size: 0.8em; color: #a8a8b3; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.5px; }}
        .stat-row {{ display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid rgba(255,255,255,0.08); }}
        .stat-label {{ color: #a8a8b3; font-size: 0.82em; white-space: nowrap; }}
        .stat-value {{ color: white; font-weight: 700; font-size: 0.9em; white-space: nowrap; }}
        .stat-highlight {{ color: {accent}; font-weight: 700; font-size: 0.9em; white-space: nowrap; }}
        .big-stat {{ text-align: center; padding: 4px; min-width: 0; }}
        .big-stat-value {{ font-size: clamp(1.2em, 4vw, 1.6em); font-weight: 800; color: white; white-space: nowrap; }}
        .big-stat-label {{ font-size: 0.65em; color: #a8a8b3; text-transform: uppercase; letter-spacing: 0.5px; }}
        .rank-badge {{ display: inline-block; background: {badge_color}; color: white; padding: 2px 6px; border-radius: 12px; font-size: 0.65em; font-weight: 700; margin-left: 4px; white-space: nowrap; }}
        .player-avatar {{ width: 64px; height: 64px; border-radius: 50%; border: 2px solid {accent}; margin-bottom: 8px; }}
        .rank-icon {{ width: 40px; height: 40px; vertical-align: middle; margin-right: 6px; }}

        /* Mobile responsiveness */
        @media (max-width: 480px) {{
            .cards-scroll {{ gap: 10px; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; }}
            .cards-scroll .battle-card {{ min-width: 85vw; max-width: 92vw; flex: 0 0 85vw; scroll-snap-align: start; }}
            .battle-card {{ padding: 14px; }}
            .player-name {{ font-size: 0.95em; flex-wrap: wrap !important; gap: 4px; }}
            .player-platform {{ font-size: 0.7em; letter-spacing: 0.5px; white-space: normal; word-break: break-word; }}
            .big-stat-value {{ font-size: 1.4em; }}
            .big-stat-label {{ font-size: 0.6em; }}
            .big-stat {{ padding: 4px 2px; }}
            .stat-row {{ flex-wrap: wrap; }}
            .stat-label {{ font-size: 0.75em; }}
            .stat-value, .stat-highlight {{ font-size: 0.8em; }}
            .rank-badge {{ font-size: 0.55em; padding: 1px 4px; margin-left: 2px; }}
            .player-avatar {{ width: 48px; height: 48px; }}
            .rank-icon {{ width: 32px; height: 32px; }}
        }}
    </style>"""

# Global CSS - minimal styles for non-card elements (cards use scoped styles in st.html)
CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;0,600;0,700;0,800;1,400&display=swap');

    /* Global font override - target text elements only, leave icons alone */
    html, body, [class*="css"], .stApp,
    [data-testid="stSidebar"],
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] div,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] button,
    [data-testid="stSidebar"] select {
        font-family: 'JetBrains Mono', monospace !important;
    }
    /* Restore Streamlit's icon fonts - must win over the above */
    [data-testid="stSidebar"] [data-testid="stIcon"],
    [data-testid="stSidebar"] [data-testid="stIconMaterial"],
    [data-testid="stSidebar"] .material-symbols-rounded,
    .material-icons, .material-symbols-rounded, .material-symbols-outlined,
    [data-testid="stIcon"], [data-testid="stIconMaterial"] {
        font-family: 'Material Symbols Rounded', 'Material Icons' !important;
    }
    /* Headings - tighter tracking for mono */
    h1, h2, h3, h4, h5, h6,
    .stApp h1, .stApp h2, .stApp h3 {
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: -0.5px;
    }
    h1, .stApp h1 { font-size: 1.6em; margin-bottom: -0.2rem; }
    h2, .stApp h2 { font-size: 1.25em; margin-top: 0.3em; margin-bottom: 0.2em; }
    h3, .stApp h3 { font-size: 1.05em; }
    /* Tighten gap between game toggle and time window */
    .stApp [data-testid="stSegmentedControl"] { margin-bottom: -0.6rem; }
    /* Keep radio label close to its options */
    .stApp [data-testid="stRadio"] > label { margin-bottom: -0.4rem; }
    /* Reduce top padding on main content area */
    .stApp [data-testid="stMainBlockContainer"] { padding-top: 1rem; }
    /* Inputs and selects */
    input, select, textarea, button,
    [data-testid="stTextInput"] input,
    [data-testid="stSelectbox"] div,
    [data-testid="stSelectbox"] span,
    [data-testid="stSelectbox"] p,
    [data-testid="stSelectbox"] [data-baseweb="select"] *,
    .stButton button {
        font-family: 'JetBrains Mono', monospace !important;
    }
    /* Selectbox - match segmented control sizing */
    [data-testid="stSelectbox"] [data-baseweb="select"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.875rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    [data-testid="stSelectbox"] label {
        font-family: 'JetBrains Mono', monospace !important;
    }
    /* Selectbox dropdown options */
    [data-baseweb="popover"] li,
    [data-baseweb="popover"] ul {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.875rem;
    }
    /* Tabs / segmented control */
    [data-testid="stSegmentedControl"] button {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.875rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    /* Dataframes */
    .stDataFrame, .stDataFrame td, .stDataFrame th {
        font-family: 'JetBrains Mono', monospace !important;
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
        letter-spacing: 0.5px;
        margin-bottom: 8px;
    }
    /* Prose sections - proportional font for readability */
    .prose-section p, .prose-section li, .prose-section td {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        font-size: 0.92em;
        line-height: 1.6;
    }
    .prose-section th, .prose-section strong {
        font-family: 'JetBrains Mono', monospace !important;
    }
</style>
"""
