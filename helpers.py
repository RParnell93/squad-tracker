import json
import os

import streamlit as st

from config import SAVE_FILE, DEFAULT_FORTNITE_PLAYERS, DEFAULT_OW2_PLAYERS


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
    return {
        "fortnite_players": list(DEFAULT_FORTNITE_PLAYERS),
        "ow2_players": list(DEFAULT_OW2_PLAYERS),
    }


def save_squad(data):
    with open(SAVE_FILE, "w") as f:
        json.dump(data, f, indent=2)
