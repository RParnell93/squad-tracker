---
paths:
  - "api.py"
  - "epic_auth.py"
---
# API Conventions

- NEVER hardcode API keys or client secrets in source code.
- Wrap all HTTP calls in try/except for requests.RequestException.
- Use resp.raise_for_status() instead of manual status code checks.
- Epic OAuth uses device auth flow - credentials stored in Streamlit secrets as epic_device_auth table.
- Fortnite API (fortnite-api.com): lifetime + season stats, per mode and input type.
- No revives, accuracy, assists, damage, or headshots from any public Fortnite API.
- fortniteapi.io is shutting down - do not use.
