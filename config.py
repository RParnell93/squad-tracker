import os

SAVE_FILE = os.path.join(os.path.dirname(__file__), "squad.json")
FORTNITE_API = "https://fortnite-api.com/v2/stats/br/v2"
OW2_API = "https://overfast-api.tekrop.fr"

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

CSS = """
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
"""
