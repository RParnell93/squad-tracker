"""Daily stats snapshot - fetches all player stats and writes to MotherDuck.

Usage:
    python snapshot.py              # Daily refresh (lifetime + 7d + 30d + current week)
    python snapshot.py --backfill 12  # Backfill last 12 weeks of weekly_stats
    python snapshot.py --setup      # Create all MotherDuck tables
    python snapshot.py --check      # Show what's in the DB

Requires:
    - MOTHERDUCK_TOKEN env var or in .env file
    - FORTNITE_API_KEY env var or in .env file
    - Epic device auth (local file or Streamlit secrets)
"""

import json
import os
import sys
import time
from datetime import date, timedelta

import duckdb
import requests

from config import DEFAULT_FORTNITE_PLAYERS, FORTNITE_API
from epic_auth import get_valid_token, lookup_account_by_name, fetch_stats_epic, parse_raw_stats
from api import epic_parsed_to_mode_stats

MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN", "")
FORTNITE_API_KEY = os.environ.get("FORTNITE_API_KEY", "")
DB_URL = f"md:squad_tracker?motherduck_token={MOTHERDUCK_TOKEN}"

# Fetch window for "7 days" padded for API reporting lag
FETCH_7D = 9
FETCH_30D = 30


def get_connection():
    return duckdb.connect(DB_URL)


def setup_tables():
    """Create all tables in MotherDuck."""
    con = get_connection()
    con.execute("""
        CREATE TABLE IF NOT EXISTS weekly_stats (
            player_name VARCHAR,
            epic_account_id VARCHAR,
            week_start DATE,
            week_end DATE,
            kills INTEGER,
            deaths INTEGER,
            wins INTEGER,
            matches INTEGER,
            score INTEGER,
            players_outlived INTEGER,
            minutes_played INTEGER,
            kd DOUBLE,
            kills_per_match DOUBLE,
            win_rate DOUBLE,
            created_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (player_name, week_start)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS player_cache (
            player_name VARCHAR,
            "window" VARCHAR,
            data_json VARCHAR,
            fetched_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (player_name, "window")
        )
    """)
    print("Tables created (or already exist).")
    con.close()


def resolve_account_ids():
    """Look up Epic account IDs for all players."""
    token = get_valid_token()
    if not token:
        print("No valid Epic token. Run: python epic_auth.py")
        return {}

    ids = {}
    for p in DEFAULT_FORTNITE_PLAYERS:
        if p.get("epic_id"):
            ids[p["name"]] = p["epic_id"]
            print(f"  {p['name']} -> {p['epic_id']} (from config)")
            continue
        display = p.get("epic_name", p["name"])
        result = lookup_account_by_name(display, token)
        if result:
            ids[p["name"]] = result["id"]
            print(f"  {p['name']} ({display}) -> {result['id']}")
        else:
            print(f"  {p['name']} ({display}) -> NOT FOUND")
        time.sleep(0.3)
    return ids


def fetch_fortnite_api_stats(name, account_type):
    """Fetch lifetime + season stats from fortnite-api.com."""
    if not FORTNITE_API_KEY:
        return None
    result = {}
    for window in ["lifetime", "season"]:
        try:
            resp = requests.get(
                FORTNITE_API,
                headers={"Authorization": FORTNITE_API_KEY},
                params={"name": name, "accountType": account_type, "timeWindow": window},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()
            if data["status"] == 200:
                result[window] = data["data"]
        except requests.RequestException as e:
            print(f"    Fortnite API error for {name} ({window}): {e}")
        time.sleep(0.5)
    if result.get("lifetime"):
        merged = result["lifetime"]
        if result.get("season"):
            merged["season_stats"] = result["season"].get("stats", {})
        return merged
    return None


def fetch_epic_window_stats(account_id, days):
    """Fetch stats for a time window via Epic Stats Proxy."""
    from epic_auth import stats_for_window
    parsed = stats_for_window(account_id, days=days)
    if not parsed:
        return None
    return epic_parsed_to_mode_stats(parsed)


def fetch_week_stats(account_id, week_start, week_end):
    """Fetch stats for a week using epoch timestamps."""
    import datetime
    start_ts = int(datetime.datetime.combine(week_start, datetime.datetime.min.time()).timestamp())
    end_ts = int(datetime.datetime.combine(week_end, datetime.datetime.max.time()).timestamp())
    raw = fetch_stats_epic(account_id, start_ts, end_ts)
    if not raw:
        return None

    parsed = parse_raw_stats(raw)
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

    if totals["matches"] == 0:
        return None

    totals["kd"] = round(totals["kills"] / max(totals["deaths"], 1), 2)
    totals["kills_per_match"] = round(totals["kills"] / max(totals["matches"], 1), 2)
    totals["win_rate"] = round(totals["wins"] / max(totals["matches"], 1) * 100, 1)
    return totals


def get_week_ranges(num_weeks):
    """Get week ranges (Mon-Sun) going back num_weeks from the most recent completed week."""
    today = date.today()
    days_since_sunday = (today.weekday() + 1) % 7
    if days_since_sunday == 0:
        last_sunday = today - timedelta(days=7)
    else:
        last_sunday = today - timedelta(days=days_since_sunday)

    weeks = []
    for i in range(num_weeks):
        week_end = last_sunday - timedelta(weeks=i)
        week_start = week_end - timedelta(days=6)
        weeks.append((week_start, week_end))
    return list(reversed(weeks))


def daily_refresh():
    """Full daily refresh: lifetime, 7d, 30d stats for all players + weekly stats."""
    if not MOTHERDUCK_TOKEN:
        print("Set MOTHERDUCK_TOKEN in .env or environment.")
        return

    print("Resolving Epic account IDs...")
    ids = resolve_account_ids()

    con = get_connection()

    # Fetch and cache lifetime stats from fortnite-api.com
    print("\n=== Lifetime Stats (fortnite-api.com) ===")
    for p in DEFAULT_FORTNITE_PLAYERS:
        name = p["name"]
        print(f"  {name}...", end=" ")
        data = fetch_fortnite_api_stats(name, p["type"])
        if data:
            con.execute("""
                INSERT OR REPLACE INTO player_cache (player_name, "window", data_json, fetched_at)
                VALUES (?, 'lifetime', ?, current_timestamp)
            """, [name, json.dumps(data)])
            matches = data.get("stats", {}).get("all", {}).get("overall", {}).get("matches", 0)
            print(f"{matches} matches")
        else:
            print("no data")
        time.sleep(0.5)

    # Fetch 7d and 30d stats from Epic Stats Proxy
    for days, label in [(FETCH_7D, "7d"), (FETCH_30D, "30d")]:
        print(f"\n=== {label} Stats (Epic Stats Proxy) ===")
        for p in DEFAULT_FORTNITE_PLAYERS:
            name = p["name"]
            aid = ids.get(name)
            if not aid:
                print(f"  {name}: no Epic ID, skipping")
                continue
            print(f"  {name}...", end=" ")
            stats = fetch_epic_window_stats(aid, days)
            if stats:
                con.execute("""
                    INSERT OR REPLACE INTO player_cache (player_name, "window", data_json, fetched_at)
                    VALUES (?, ?, ?, current_timestamp)
                """, [name, label, json.dumps(stats)])
                o = stats.get("all", {}).get("overall", {})
                print(f"{o.get('matches', 0)} matches, K/D {o.get('kd', 0):.2f}")
            else:
                print("no data")
            time.sleep(0.5)

    # Update weekly_stats for current + prior week
    print("\n=== Weekly Stats ===")
    weeks = get_week_ranges(2)
    for week_start, week_end in weeks:
        print(f"\n--- {week_start} to {week_end} ---")
        for name, aid in ids.items():
            is_current_week = week_end >= date.today() - timedelta(days=6)
            existing = con.execute(
                "SELECT 1 FROM weekly_stats WHERE player_name = ? AND week_start = ?",
                [name, week_start]
            ).fetchone()
            if existing and not is_current_week:
                print(f"  {name}: already stored, skipping")
                continue

            stats = fetch_week_stats(aid, week_start, week_end)
            if not stats:
                print(f"  {name}: no games played")
                continue

            if existing:
                con.execute("""
                    UPDATE weekly_stats SET
                        kills = ?, deaths = ?, wins = ?, matches = ?, score = ?,
                        players_outlived = ?, minutes_played = ?,
                        kd = ?, kills_per_match = ?, win_rate = ?,
                        created_at = current_timestamp
                    WHERE player_name = ? AND week_start = ?
                """, [stats["kills"], stats["deaths"], stats["wins"], stats["matches"],
                      stats["score"], stats["players_outlived"], stats["minutes_played"],
                      stats["kd"], stats["kills_per_match"], stats["win_rate"],
                      name, week_start])
                print(f"  {name}: updated - {stats['matches']} matches")
            else:
                con.execute("""
                    INSERT INTO weekly_stats (player_name, epic_account_id, week_start, week_end,
                        kills, deaths, wins, matches, score, players_outlived, minutes_played,
                        kd, kills_per_match, win_rate)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [name, aid, week_start, week_end,
                      stats["kills"], stats["deaths"], stats["wins"], stats["matches"],
                      stats["score"], stats["players_outlived"], stats["minutes_played"],
                      stats["kd"], stats["kills_per_match"], stats["win_rate"]])
                print(f"  {name}: {stats['matches']} matches")
            time.sleep(0.5)

    con.close()
    print("\nDaily refresh complete!")


def backfill_weeks(num_weeks=12):
    """Backfill weekly_stats only."""
    if not MOTHERDUCK_TOKEN:
        print("Set MOTHERDUCK_TOKEN in .env or environment.")
        return

    print("Resolving Epic account IDs...")
    ids = resolve_account_ids()
    if not ids:
        return

    con = get_connection()
    weeks = get_week_ranges(num_weeks)

    for week_start, week_end in weeks:
        print(f"\n--- {week_start} to {week_end} ---")
        for name, aid in ids.items():
            existing = con.execute(
                "SELECT 1 FROM weekly_stats WHERE player_name = ? AND week_start = ?",
                [name, week_start]
            ).fetchone()
            if existing:
                print(f"  {name}: already stored, skipping")
                continue

            stats = fetch_week_stats(aid, week_start, week_end)
            if not stats:
                print(f"  {name}: no games played")
                continue

            con.execute("""
                INSERT INTO weekly_stats (player_name, epic_account_id, week_start, week_end,
                    kills, deaths, wins, matches, score, players_outlived, minutes_played,
                    kd, kills_per_match, win_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [name, aid, week_start, week_end,
                  stats["kills"], stats["deaths"], stats["wins"], stats["matches"],
                  stats["score"], stats["players_outlived"], stats["minutes_played"],
                  stats["kd"], stats["kills_per_match"], stats["win_rate"]])
            print(f"  {name}: {stats['matches']} matches, K/D {stats['kd']}")
            time.sleep(0.5)

    con.close()
    print("\nBackfill complete!")


def check_db():
    """Show what's in the database."""
    con = get_connection()

    # Player cache
    rows = con.execute("""
        SELECT player_name, "window", fetched_at
        FROM player_cache ORDER BY player_name, "window"
    """).fetchall()
    if rows:
        print("=== Player Cache ===")
        print(f"{'Player':<20} {'Window':<12} {'Fetched At'}")
        print("-" * 55)
        for r in rows:
            print(f"{r[0]:<20} {r[1]:<12} {r[2]}")
    else:
        print("No data in player_cache.")

    # Weekly stats
    rows = con.execute("""
        SELECT player_name, week_start, week_end, matches, kills, kd, win_rate
        FROM weekly_stats ORDER BY week_start DESC, player_name LIMIT 30
    """).fetchall()
    if rows:
        print(f"\n=== Weekly Stats (last 30 rows) ===")
        print(f"{'Player':<20} {'Week':<25} {'Matches':>8} {'Kills':>7} {'K/D':>6} {'Win%':>6}")
        print("-" * 75)
        for r in rows:
            print(f"{r[0]:<20} {r[1]} - {r[2]}  {r[3]:>8} {r[4]:>7} {r[5]:>6.2f} {r[6]:>5.1f}%")
    else:
        print("\nNo data in weekly_stats.")

    con.close()


if __name__ == "__main__":
    # Load .env if present
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"'))
        # Re-read after loading .env - update module-level globals
        globals()["MOTHERDUCK_TOKEN"] = os.environ.get("MOTHERDUCK_TOKEN", "")
        globals()["FORTNITE_API_KEY"] = os.environ.get("FORTNITE_API_KEY", "")
        globals()["DB_URL"] = f"md:squad_tracker?motherduck_token={globals()['MOTHERDUCK_TOKEN']}"

    if "--setup" in sys.argv:
        setup_tables()
    elif "--backfill" in sys.argv:
        idx = sys.argv.index("--backfill")
        weeks = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 12
        backfill_weeks(num_weeks=weeks)
    elif "--check" in sys.argv:
        check_db()
    else:
        daily_refresh()
