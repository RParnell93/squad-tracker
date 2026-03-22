"""MotherDuck database layer for cached stats reads."""

import logging
import os
from datetime import date, timedelta

logger = logging.getLogger(__name__)

try:
    import duckdb
    HAS_DUCKDB = True
except ImportError:
    HAS_DUCKDB = False


def _get_token():
    """Get MotherDuck token from env or Streamlit secrets."""
    token = os.environ.get("MOTHERDUCK_TOKEN", "")
    if not token:
        try:
            import streamlit as st
            token = st.secrets["MOTHERDUCK_TOKEN"]
        except Exception:
            pass
    return token


def get_connection():
    """Get a read-only MotherDuck connection. Returns None if unavailable."""
    if not HAS_DUCKDB:
        return None
    token = _get_token()
    if not token:
        return None
    try:
        return duckdb.connect(f"md:squad_tracker?motherduck_token={token}")
    except Exception as e:
        logger.warning("MotherDuck connection failed: %s", e)
        return None


def fetch_weekly_trends(player_names, num_weeks=12):
    """Fetch weekly stats from MotherDuck for trend charts.

    Returns dict: {player_name: [{week_start, week_end, kd, kills, matches, ...}, ...]}
    Weeks are ordered oldest-first.
    """
    con = get_connection()
    if not con:
        return None

    try:
        # Get the last num_weeks of completed weeks
        today = date.today()
        days_since_sunday = (today.weekday() + 1) % 7
        if days_since_sunday == 0:
            cutoff_end = today - timedelta(days=7)
        else:
            cutoff_end = today - timedelta(days=days_since_sunday)
        cutoff_start = cutoff_end - timedelta(weeks=num_weeks - 1, days=6)

        rows = con.execute("""
            SELECT player_name, week_start, week_end,
                   kills, deaths, wins, matches, score,
                   players_outlived, minutes_played,
                   kd, kills_per_match, win_rate
            FROM weekly_stats
            WHERE week_start >= ? AND week_end <= ?
              AND player_name = ANY(?)
            ORDER BY week_start ASC
        """, [cutoff_start, cutoff_end, player_names]).fetchall()

        columns = ["player_name", "week_start", "week_end",
                    "kills", "deaths", "wins", "matches", "score",
                    "players_outlived", "minutes_played",
                    "kd", "kills_per_match", "win_rate"]

        result = {name: [] for name in player_names}
        for row in rows:
            entry = dict(zip(columns, row))
            name = entry["player_name"]
            if name in result:
                result[name].append(entry)

        con.close()
        return result
    except Exception as e:
        logger.warning("MotherDuck query failed: %s", e)
        try:
            con.close()
        except Exception:
            pass
        return None


def get_all_week_ranges(num_weeks=12):
    """Get the Mon-Sun week ranges for the last num_weeks completed weeks.
    Returns list of (week_start, week_end) tuples, oldest first.
    """
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
