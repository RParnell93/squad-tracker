# Squad Stats - Fortnite & Overwatch 2 Tracker

Streamlit app that tracks and compares gaming stats for a friend group.
Live at [squadstats.streamlit.app](https://squadstats.streamlit.app). GitHub: RParnell93/squad-tracker.

## Tech Stack

Python 3.12, Streamlit, Plotly, requests, DuckDB (pinned to v1.4.4 for MotherDuck compat), Anthropic SDK (Claude Haiku for AI summaries).

## Modules

- **app.py** - Main Streamlit app. Battle cards, charts (bar, radar, trend lines), AI weekly summaries, sidebar squad management. Uses `@st.fragment` for chart re-renders.
- **config.py** - Constants: default player lists (Fortnite + OW2), API URLs, global CSS, card_css() function, skeleton loading HTML generators.
- **api.py** - HTTP calls to fortnite-api.com and OverFast API (OW2). Converts Epic raw stats to fortnite-api.com format. OW2 player search with case variants.
- **metrics.py** - Percentile curves, Dub Score formula (composite 0-100 rating), score_circle_html() for CSS donut charts. Separate curves for Fortnite and OW2.
- **helpers.py** - API key retrieval (secrets with fallback), squad save/load to JSON file.
- **epic_auth.py** - Epic Games OAuth: auth code flow, refresh tokens, device auth (permanent creds). Stats proxy for custom time windows. CLI for initial setup.
- **snapshot.py** - Daily ETL to MotherDuck: lifetime, 7d, 30d stats + weekly aggregates + daily stats + OW2 cache. CLI with --setup, --backfill, --check flags.
- **db.py** - MotherDuck read layer for the app. Fetches cached stats, weekly trends, OW2 data.

## Key Commands

```bash
streamlit run app.py                    # Run locally
python snapshot.py                      # Daily refresh (all stats to MotherDuck)
python snapshot.py --setup              # Create MotherDuck tables
python snapshot.py --backfill 12        # Backfill 12 weeks of weekly_stats
python snapshot.py --backfill-daily 14  # Backfill 14 days of daily_stats
python snapshot.py --check              # Show DB contents
python epic_auth.py                     # Initial Epic OAuth setup (browser flow)
python epic_auth.py --test              # Test Epic stats fetch
```

## Deployment

- **Streamlit Cloud**: Auto-deploys from main branch. App at squadstats.streamlit.app.
- **GitHub Pages**: rparnell93.github.io/squad-tracker redirects with OG meta tags for social previews.
- **GitHub Action**: Weekly snapshot runs Monday 8am UTC.
- **MotherDuck**: Cloud DuckDB, database name "squad_tracker". Tables: weekly_stats, player_cache, daily_stats, ow2_player_cache.

## Secrets

| Key | Where | Purpose |
|-----|-------|---------|
| FORTNITE_API_KEY | .env / Streamlit secrets | fortnite-api.com auth |
| EPIC_CLIENT_ID | .env / Streamlit secrets | Epic OAuth client |
| EPIC_CLIENT_SECRET | .env / Streamlit secrets | Epic OAuth client |
| ANTHROPIC_API_KEY | .env / Streamlit secrets | Claude Haiku AI summaries |
| MOTHERDUCK_TOKEN | .env / GitHub Actions | MotherDuck connection |
| epic_device_auth | .epic_device_auth.json / Streamlit secrets (TOML table) | Permanent Epic device auth |

Local: `.env` file + `.streamlit/secrets.toml` (both gitignored).
Cloud: Streamlit Cloud Settings > Secrets (TOML format).

## Conventions

- DuckDB pinned to v1.4.4. Do not upgrade without checking MotherDuck compat.
- All HTTP calls wrapped in try/except for requests.RequestException.
- No API keys in source code. Use .env locally, st.secrets on cloud.
- `st.set_page_config()` must be the first Streamlit command in app.py.
- `st.html()` is isolated from global CSS. Card styles use scoped CSS via `card_css()`.
- Use `@st.fragment` for interactive chart sections to avoid full page reruns.
- Plotly config: always disable displayModeBar and scrollZoom for mobile.
- fortniteapi.io is shutting down. Only use fortnite-api.com.
