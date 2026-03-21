"""
Epic Games OAuth for Fortnite Stats Proxy.

Usage:
    1. Run this script: python epic_auth.py
    2. It opens your browser to log in to Epic Games
    3. You'll get redirected to a page with a JSON response containing an authorization code
    4. Paste the code when prompted
    5. Script saves your tokens to .epic_tokens.json (gitignored)

After initial auth, tokens auto-refresh. Run `epic_auth.py --refresh` to refresh silently.
"""

import base64
import json
import os
import sys
import time
import webbrowser
import requests

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".epic_tokens.json")
DEVICE_AUTH_FILE = os.path.join(os.path.dirname(__file__), ".epic_device_auth.json")

# Fortnite PC Game Client (community-documented, used by all third-party tools)
CLIENT_ID = "REDACTED_CLIENT_ID"
CLIENT_SECRET = "REDACTED_CLIENT_SECRET"

OAUTH_TOKEN_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
STATS_URL = "https://statsproxy-public-service-live.ol.epicgames.com/statsproxy/api/statsv2/account"

# Authorization code URL - after logging in, visiting this gives you a code
AUTH_CODE_URL = "https://www.epicgames.com/id/api/redirect?clientId={}&responseType=code".format(CLIENT_ID)


def _basic_auth():
    """Base64 encode client credentials for Basic auth header."""
    raw = f"{CLIENT_ID}:{CLIENT_SECRET}"
    return base64.b64encode(raw.encode()).decode()


def get_token_with_auth_code(code):
    """Exchange an authorization code for access + refresh tokens."""
    resp = requests.post(
        OAUTH_TOKEN_URL,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "token_type": "eg1",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Auth failed ({resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    save_tokens(data)
    return data


def refresh_token(refresh_tok):
    """Use a refresh token to get new access + refresh tokens."""
    resp = requests.post(
        OAUTH_TOKEN_URL,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "token_type": "eg1",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Refresh failed ({resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    save_tokens(data)
    return data


def create_device_auth(access_token, account_id):
    """Create a device auth credential (permanent, never expires).

    This only needs to be done once. The device_id + secret can then
    generate new access tokens forever without browser login.
    """
    resp = requests.post(
        f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Device auth creation failed ({resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    device_data = {
        "account_id": data["accountId"],
        "device_id": data["deviceId"],
        "secret": data["secret"],
    }
    with open(DEVICE_AUTH_FILE, "w") as f:
        json.dump(device_data, f, indent=2)
    print(f"Device auth saved to {DEVICE_AUTH_FILE}")
    print("You will never need to log in manually again.")
    return device_data


def load_device_auth():
    """Load saved device auth credentials (local file or Streamlit secrets)."""
    if os.path.exists(DEVICE_AUTH_FILE):
        with open(DEVICE_AUTH_FILE) as f:
            return json.load(f)
    # Fall back to Streamlit secrets
    try:
        import streamlit as st
        da = st.secrets.get("epic_device_auth")
        if da:
            return dict(da)
    except Exception:
        pass
    return None


def token_from_device_auth(device_data=None):
    """Get a fresh access token using device auth (no browser needed)."""
    if not device_data:
        device_data = load_device_auth()
    if not device_data:
        return None

    # Device auth may use a different client than the PC game client
    da_client_id = device_data.get("client_id", CLIENT_ID)
    da_client_secret = device_data.get("client_secret", CLIENT_SECRET)
    da_basic = base64.b64encode(f"{da_client_id}:{da_client_secret}".encode()).decode()

    resp = requests.post(
        OAUTH_TOKEN_URL,
        headers={
            "Authorization": f"Basic {da_basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "device_auth",
            "account_id": device_data["account_id"],
            "device_id": device_data["device_id"],
            "secret": device_data["secret"],
            "token_type": "eg1",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Device auth token failed ({resp.status_code}): {resp.text}")
        return None
    data = resp.json()
    save_tokens(data)
    return data


def save_tokens(token_data):
    """Save tokens to disk."""
    to_save = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data.get("refresh_token", ""),
        "account_id": token_data.get("account_id", ""),
        "display_name": token_data.get("displayName", ""),
        "expires_at": token_data.get("expires_at", ""),
        "refresh_expires_at": token_data.get("refresh_expires_at", ""),
        "saved_at": time.time(),
    }
    with open(TOKEN_FILE, "w") as f:
        json.dump(to_save, f, indent=2)
    print(f"Tokens saved to {TOKEN_FILE}")


def load_tokens():
    """Load saved tokens from disk."""
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE) as f:
        return json.load(f)


def get_valid_token():
    """Get a valid access token. Tries in order: cached token, refresh, device auth."""
    tokens = load_tokens()

    if tokens:
        access_token = tokens["access_token"]
        refresh_tok = tokens.get("refresh_token", "")

        # Try cached token
        test = requests.get(
            f"{STATS_URL}/{tokens['account_id']}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"startTime": 0, "endTime": 9223372036854775807},
            timeout=10,
        )
        if test.status_code == 200 or test.status_code == 204:
            return access_token

        # Try refresh token
        if refresh_tok:
            new_tokens = refresh_token(refresh_tok)
            if new_tokens:
                return new_tokens["access_token"]

    # Try device auth (permanent credentials, no browser needed)
    device_data = load_device_auth()
    if device_data:
        new_tokens = token_from_device_auth(device_data)
        if new_tokens:
            return new_tokens["access_token"]

    print("No valid tokens. Run: python epic_auth.py")
    return None


def fetch_stats_epic(account_id, start_time=0, end_time=9223372036854775807):
    """Fetch stats from Epic's stats proxy with custom time window.

    Args:
        account_id: Epic account ID
        start_time: Unix epoch seconds (0 = all time)
        end_time: Unix epoch seconds (max int = all time)

    Returns:
        dict with raw stat keys, or None on failure
    """
    token = get_valid_token()
    if not token:
        return None

    resp = requests.get(
        f"{STATS_URL}/{account_id}",
        headers={"Authorization": f"Bearer {token}"},
        params={"startTime": start_time, "endTime": end_time},
        timeout=15,
    )
    if resp.status_code == 204:
        print(f"Stats are private for {account_id}")
        return None
    if resp.status_code != 200:
        print(f"Stats fetch failed ({resp.status_code}): {resp.text}")
        return None
    return resp.json()


def lookup_account_by_name(display_name, token=None):
    """Look up an Epic account ID by display name."""
    if not token:
        token = get_valid_token()
    if not token:
        return None
    resp = requests.get(
        f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{display_name}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()
    return None


def parse_raw_stats(raw_stats):
    """Parse Epic's raw stat keys into a structured format.

    Raw keys look like: br_kills_gamepad_m0_playlist_defaultsolo
    Format: br_{metric}_{input}_m0_playlist_{playlist}
    """
    stats = raw_stats.get("stats", {})
    parsed = {}
    input_types = ["keyboardmouse", "gamepad", "touch"]

    for key, value in stats.items():
        parts = key.split("_")
        if len(parts) < 4 or parts[0] != "br":
            continue

        # Find the input type in the key
        metric_parts = []
        input_type = "unknown"
        playlist_parts = []
        found_input = False
        found_playlist = False
        for p in parts[1:]:
            if not found_input and p in input_types:
                input_type = p
                found_input = True
            elif found_input and p == "playlist":
                found_playlist = True
            elif found_playlist:
                playlist_parts.append(p)
            elif found_input and not found_playlist:
                pass  # skip "m0"
            else:
                metric_parts.append(p)

        metric = "_".join(metric_parts) if metric_parts else key
        playlist = "_".join(playlist_parts) if playlist_parts else "all"

        if input_type not in parsed:
            parsed[input_type] = {}
        if playlist not in parsed[input_type]:
            parsed[input_type][playlist] = {}
        parsed[input_type][playlist][metric] = value

    return parsed


def stats_for_window(account_id, days=None):
    """Fetch stats for a specific time window.

    Args:
        account_id: Epic account ID
        days: Number of days back (None = lifetime)

    Returns:
        Parsed stats dict
    """
    if days:
        end_time = int(time.time())
        start_time = end_time - (days * 86400)
    else:
        start_time = 0
        end_time = 9223372036854775807

    raw = fetch_stats_epic(account_id, start_time, end_time)
    if not raw:
        return None
    return parse_raw_stats(raw)


# ── CLI ──────────────────────────────────────────────────────────────────────

def interactive_login():
    """Walk the user through the OAuth flow."""
    print("\n=== Epic Games OAuth Setup ===\n")
    print("1. Opening your browser to log in to Epic Games...")
    print("2. After logging in, you'll see a JSON response with a 'redirectUrl'")
    print("3. The URL will contain ?code=XXXXX - copy that code\n")

    webbrowser.open(AUTH_CODE_URL)

    print("If the browser didn't open, go to:")
    print(f"  {AUTH_CODE_URL}\n")

    code = input("Paste the authorization code here: ").strip()
    if not code:
        print("No code entered. Aborting.")
        return

    print("\nExchanging code for tokens...")
    tokens = get_token_with_auth_code(code)
    if tokens:
        print(f"\nAuthenticated as: {tokens.get('displayName', 'Unknown')}")
        print(f"Account ID: {tokens.get('account_id', 'Unknown')}")

        # Create device auth for permanent access
        existing_device = load_device_auth()
        if not existing_device:
            print("\nCreating permanent device auth (so you never need to log in again)...")
            create_device_auth(tokens["access_token"], tokens["account_id"])
        else:
            print("\nDevice auth already exists - permanent access is set up.")

        print("\nAll done. The app can now query any time window automatically.")
    else:
        print("\nFailed to authenticate. Make sure the code is correct and try again.")


def test_stats():
    """Quick test: fetch your own lifetime + 7-day stats."""
    tokens = load_tokens()
    if not tokens:
        print("No tokens. Run: python epic_auth.py")
        return

    account_id = tokens["account_id"]
    name = tokens.get("display_name", account_id)

    print(f"\n=== Stats for {name} ===\n")

    for label, days in [("Lifetime", None), ("Last 7 Days", 7), ("Last 30 Days", 30)]:
        parsed = stats_for_window(account_id, days)
        if not parsed:
            print(f"{label}: No data")
            continue

        # Sum across all inputs and playlists for a quick overview
        total_kills = 0
        total_matches = 0
        total_wins = 0
        total_outlived = 0
        total_score = 0
        for input_type, playlists in parsed.items():
            for playlist, metrics in playlists.items():
                total_kills += metrics.get("kills", 0)
                total_matches += metrics.get("matchesplayed", 0)
                total_wins += metrics.get("placetop1", 0)
                total_outlived += metrics.get("playersoutlived", 0)
                total_score += metrics.get("score", 0)

        kd = total_kills / max(total_matches - total_wins, 1)
        wr = total_wins / max(total_matches, 1) * 100
        kpm = total_kills / max(total_matches, 1)

        print(f"--- {label} ---")
        print(f"  Matches: {total_matches:,}")
        print(f"  Wins: {total_wins:,} ({wr:.1f}%)")
        print(f"  Kills: {total_kills:,}")
        print(f"  K/D: {kd:.2f}")
        print(f"  Kills/Match: {kpm:.2f}")
        print(f"  Players Outlived: {total_outlived:,}")
        print(f"  Score: {total_score:,}")
        print()


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        tokens = load_tokens()
        if tokens and tokens.get("refresh_token"):
            refresh_token(tokens["refresh_token"])
        else:
            print("No refresh token available. Run: python epic_auth.py")
    elif "--test" in sys.argv:
        test_stats()
    else:
        interactive_login()
