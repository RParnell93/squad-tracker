"""Daily stats snapshot - fetches yesterday's stats for all players and writes to MotherDuck.

Usage:
    python snapshot.py              # Fetch yesterday's stats and insert
    python snapshot.py --backfill 30  # Backfill last 30 days (one row per day per player)
    python snapshot.py --setup      # Create the MotherDuck table

Requires:
    - MOTHERDUCK_TOKEN env var or in .env file
    - Epic device auth (local file or Streamlit secrets)
"""

import os
import sys
import time
from datetime import date, datetime, timedelta

import duckdb

# Load .env if present
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from epic_auth import get_valid_token, lookup_account_by_name, fetch_stats_epic, parse_raw_stats

MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN", "")
DB_URL = f"md:squad_tracker?motherduck_token={MOTHERDUCK_TOKEN}"

# All Fortnite players to track
PLAYERS = [
    {"name": "astros44", "type": "xbl"},
    {"name": "zippomanjingles", "type": "psn"},
    {"name": "crazy in basye", "type": "xbl"},
    {"name": "i7vosunz458", "type": "xbl"},
    {"name": "callmepot", "type": "epic"},
    {"name": "Jbone", "type": "epic"},
    {"name": "hailedcanvas141", "type": "xbl"},
    {"name": "mrfox733", "type": "xbl"},
]


def get_connection():
    return duckdb.connect(DB_URL)


def setup_table():
    """Create the daily_stats table in MotherDuck."""
    con = get_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS daily_stats (
            player_name VARCHAR,
            epic_account_id VARCHAR,
            date DATE,
            kills INTEGER,
            deaths INTEGER,
            wins INTEGER,
            matches INTEGER,
            score INTEGER,
            players_outlived INTEGER,
            minutes_played INTEGER,
            created_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (player_name, date)
        )
    """)
    print("Table daily_stats created (or already exists).")
    con.close()


def resolve_account_ids():
    """Look up Epic account IDs for all players."""
    token = get_valid_token()
    if not token:
        print("No valid Epic token. Run: python epic_auth.py")
        return {}

    ids = {}
    for p in PLAYERS:
        result = lookup_account_by_name(p["name"], token)
        if result:
            ids[p["name"]] = result["id"]
            print(f"  {p['name']} -> {result['id']}")
        else:
            print(f"  {p['name']} -> NOT FOUND")
        time.sleep(0.3)
    return ids


def fetch_day_stats(account_id, target_date):
    """Fetch stats for a single day."""
    start = int(datetime.combine(target_date, datetime.min.time()).timestamp())
    end = int(datetime.combine(target_date, datetime.max.time()).timestamp())
    raw = fetch_stats_epic(account_id, start, end)
    if not raw:
        return None

    parsed = parse_raw_stats(raw)
    # Sum across all inputs and playlists
    totals = {"kills": 0, "deaths": 0, "wins": 0, "matches": 0,
              "score": 0, "players_outlived": 0, "minutes_played": 0}
    for input_type, playlists in parsed.items():
        for playlist, metrics in playlists.items():
            totals["kills"] += metrics.get("kills", 0)
            totals["matches"] += metrics.get("matchesplayed", 0)
            totals["wins"] += metrics.get("placetop1", 0)
            totals["score"] += metrics.get("score", 0)
            totals["players_outlived"] += metrics.get("playersoutlived", 0)
            totals["minutes_played"] += metrics.get("minutesplayed", 0)
    totals["deaths"] = max(totals["matches"] - totals["wins"], 0)
    return totals


def snapshot(target_date=None, backfill_days=None):
    """Fetch and store stats."""
    if not MOTHERDUCK_TOKEN:
        print("Set MOTHERDUCK_TOKEN in .env or environment.")
        return

    print("Resolving Epic account IDs...")
    ids = resolve_account_ids()
    if not ids:
        return

    con = get_connection()

    if backfill_days:
        dates = [date.today() - timedelta(days=i) for i in range(1, backfill_days + 1)]
    else:
        dates = [target_date or date.today() - timedelta(days=1)]

    for d in dates:
        print(f"\n--- {d} ---")
        for name, aid in ids.items():
            # Check if already exists
            existing = con.execute(
                "SELECT 1 FROM daily_stats WHERE player_name = ? AND date = ?",
                [name, d]
            ).fetchone()
            if existing:
                print(f"  {name}: already stored, skipping")
                continue

            stats = fetch_day_stats(aid, d)
            if not stats or stats["matches"] == 0:
                print(f"  {name}: no games played")
                continue

            con.execute("""
                INSERT INTO daily_stats (player_name, epic_account_id, date,
                    kills, deaths, wins, matches, score, players_outlived, minutes_played)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [name, aid, d,
                  stats["kills"], stats["deaths"], stats["wins"], stats["matches"],
                  stats["score"], stats["players_outlived"], stats["minutes_played"]])
            kd = stats["kills"] / max(stats["deaths"], 1)
            print(f"  {name}: {stats['matches']} matches, {stats['kills']} kills, K/D {kd:.2f}")
            time.sleep(0.5)

    con.close()
    print("\nDone!")


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup_table()
    elif "--backfill" in sys.argv:
        idx = sys.argv.index("--backfill")
        days = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 30
        snapshot(backfill_days=days)
    else:
        snapshot()
