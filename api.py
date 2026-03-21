import requests
import time

from config import FORTNITE_API, OW2_API
from epic_auth import get_valid_token, lookup_account_by_name


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
        "solo": ["defaultsolo", "nobuildbrsolo", "nobuildbr_solo", "figmentsolo",
                 "figmentnobuildsolo"],
        "duo": ["defaultduo", "nobuildbrduos", "nobuildbr_duo", "figmentduo",
                "figmentnobuildduo", "bots_nobuildbr_duo"],
        "squad": ["defaultsquad", "nobuildbrsquad", "nobuildbr_squad", "sunflowernobuildsquad",
                  "arseniccore_squads_maxfog", "punchberrynobuildsquad",
                  "mash_squads_legacy", "forbiddenfruitnobuildbrsquad"],
        "trio": ["trios", "nobuildbr_trio", "bots_nobuildbr_trio"],
    }

    totals = {}  # mode -> {metric: value}
    for mode in ["solo", "duo", "trio", "squad", "overall"]:
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
