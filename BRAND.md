# Squad Tracker Brand Book

## Typography
- **Primary Font:** JetBrains Mono (Google Fonts)
- **Weights:** 300 (light), 400 (regular), 500 (medium), 600 (semibold), 700 (bold), 800 (extra bold)
- **Headings:** JetBrains Mono, weight 700-800, letter-spacing: -0.5px
- **Body/Stats:** JetBrains Mono, weight 400-600
- **Uppercase labels:** letter-spacing: 0.5px (not higher - mono already has even spacing)
- **Prose sections** (AI recaps, data definitions): Inter / system sans-serif for readability

## Colors

### Fortnite Accent
- Primary: `#e94560` (red-pink)
- Used for: card borders, highlighted stats, bar chart leaders, accent elements

### Overwatch 2 Accent
- Primary: `#f99e1a` (orange)
- Used for: card borders, highlighted stats, bar chart leaders, accent elements

### Platform Tags
- Xbox: `#2d9f2d` (green)
- PlayStation: `#006fcd` (blue)
- Epic (PC): `#6b6b7b` (gray)
- OW2: `#f99e1a` (orange)

### Backgrounds
- App background: Streamlit dark theme default
- Sidebar gradient: `#0d1117` -> `#161b22` -> `#1a1a2e`
- Card gradient: `linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)`
- Card border: 2px solid accent color

### Score Colors (Dub Score circles)
- 75+: `#00c853` (green)
- 50-74: `#ffc107` (yellow)
- Below 50: `#ef5350` (red)
- No data: `#444`

### Percentile Colors (Statcast-style)
- 90+: `#c8102e` (dark red / elite)
- 75-89: `#ef5350` (light red / great)
- 50-74: `#b0bec5` (gray / average)
- 25-49: `#64b5f6` (light blue / below avg)
- Below 25: `#1565c0` (dark blue / poor)

### Text Colors
- Primary text: `white`
- Secondary labels: `#a8a8b3`
- Muted/tertiary: `#6e7681`
- Sidebar accent labels: game accent color at 0.8 opacity

### Supreme Leader Badge
- Gradient: `linear-gradient(90deg, #ffd700, #ffaa00)`
- Text: `#1a1a2e`
- Card border: `#ffd700` with gold box-shadow

## Layout
- Dark theme only
- Wide layout (Streamlit `layout="wide"`)
- Battle cards: horizontal scroll, 280-340px per card, snap scrolling
- Charts: horizontal bars sorted greatest-to-least, no hover tooltips
- Plotly: `displayModeBar: False`, `scrollZoom: False` on mobile
- Mobile: cards snap at 85vw, font sizes use `clamp()`

## Logo
- Inline SVG crosshair reticle
- Two concentric circles + center dot + four crosshair lines
- Colored in Fortnite accent (`#e94560`)
- 36x36px next to title

## Voice / AI Summary
- 12 rotating voice styles per game
- 4 rotating structural templates per game
- No emojis, no em dashes, no corporate language
- Direct, funny, stat-backed commentary
- Player notes respected (pronouns, roast targets)

## Dub Score Formula
- **Fortnite:** 45% Win Rate + 30% K/D + 25% Outlived/Match (percentile-based, activity-scaled)
- **OW2:** 40% Win Rate + 30% KDA + 15% Avg Elims + 15% Avg Damage (percentile-based, activity-scaled)
