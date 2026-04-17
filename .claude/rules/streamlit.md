---
paths:
  - "app.py"
  - "helpers.py"
---
# Streamlit Conventions

- st.set_page_config() must be the first Streamlit command in app.py.
- st.stop() kills the ENTIRE app. Use elif chains instead.
- st.html() is isolated - global CSS from st.markdown() does not apply inside it.
- Use @st.fragment for chart re-renders.
- Secrets: os.environ.get() + load_dotenv() locally, st.secrets on cloud (try/except pattern).
- st.columns auto-stacks at 640px on mobile.
- SVG is stripped by Streamlit's sanitizer - use CSS alternatives (conic-gradient for donuts).
- Cache keys must include all parameters that affect the result.
- Always clear all related caches on Refresh button.
