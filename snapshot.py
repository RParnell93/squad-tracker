"""Weekly stats snapshot - fetches weekly stats for all players and writes to MotherDuck.

Usage:
    python snapshot.py              # Fetch last week's stats and insert
    python snapshot.py --backfill 12  # Backfill last 12 weeks
    python snapshot.py --setup      # Create the MotherDuck table
    python snapshot.py --check      # Show what's in the DB

Requires:
    - MOTHERDUCK_TOKEN env var or in .env file
    - Epic device auth (local file or Streamlit secrets)
"""

import os
import sys
import time
from datetime import date, timedelta

import duckdb

from config import DEFAULT_FORTNITE_PLAYERS
from epic_auth import get_valid_token, lookup_account_by_name, fetch_stats_epic, parse_raw_stats

MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN", "")
DB_URL = f"md:squad_tracker?motherduck_token={MOTHERDUCK_TOKEN}"


def get_connection():
    return duckdb.connect(DB_URL)


def setup_table():
    """Create the weekly_stats table in MotherDuck."""
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
    # Drop old daily_stats table if it exists (was never populated)
    con.execute("DROP TABLE IF EXISTS daily_stats")
    print("Table weekly_stats created (or already exists).")
    con.close()


def resolve_account_ids():
    """Look up Epic account IDs for all players."""
    token = get_valid_token()
    if not token:
        print("No valid Epic token. Run: python epic_auth.py")
        return {}

    ids = {}
    for p in DEFAULT_FORTNITE_PLAYERS:
        # Use hardcoded epic_id if available (for players with no Epic display name)
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
    # Find last Sunday (end of most recent completed week)
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


def snapshot(num_weeks=1):
    """Fetch and store weekly stats."""
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
            # For the current (incomplete) week, always update. For past weeks, skip if stored.
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
                # Update current week's running totals
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
                print(f"  {name}: updated - {stats['matches']} matches, K/D {stats['kd']}, Win% {stats['win_rate']}")
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
                print(f"  {name}: {stats['matches']} matches, K/D {stats['kd']}, Win% {stats['win_rate']}")
            time.sleep(0.5)

    con.close()
    print("\nDone!")


def check_db():
    """Show what's in the database."""
    con = get_connection()
    rows = con.execute("""
        SELECT player_name, week_start, week_end, matches, kills, kd, win_rate
        FROM weekly_stats
        ORDER BY week_start, player_name
    """).fetchall()
    if not rows:
        print("No data in weekly_stats.")
    else:
        print(f"{'Player':<20} {'Week':<25} {'Matches':>8} {'Kills':>7} {'K/D':>6} {'Win%':>6}")
        print("-" * 75)
        for r in rows:
            print(f"{r[0]:<20} {r[1]} - {r[2]}  {r[3]:>8} {r[4]:>7} {r[5]:>6.2f} {r[6]:>5.1f}%")
    print(f"\nTotal rows: {len(rows)}")
    con.close()


if __name__ == "__main__":
    if "--setup" in sys.argv:
        setup_table()
    elif "--backfill" in sys.argv:
        idx = sys.argv.index("--backfill")
        weeks = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 12
        snapshot(num_weeks=weeks)
    elif "--check" in sys.argv:
        check_db()
    else:
        snapshot(num_weeks=1)
