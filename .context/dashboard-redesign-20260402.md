# Dashboard Redesign Plan

**Date:** 2026-04-02
**Status:** DESIGN IN PROGRESS
**Branch:** main (no dedicated branch yet)

---

## What We're Building

A professional trading dashboard for a discretionary trading system. Users are traders watching P&L, equity curves, and trade history. The dashboard replaces the existing `dashboard.html`.

**Who uses this:** Self-directed traders running a systematic strategy on Alpaca (paper or live).
**Primary job:** "Tell me at a glance how I'm doing today and this week."
**Secondary job:** Drill into specific trades and strategy performance.

---

## Design Direction: Bloomberg-Dense Trading Terminal

The existing dashboard is generic dark SaaS. The new dashboard is a **purpose-built trading terminal** — dense with information but visually controlled. Inspired by: Bloomberg Terminal (information density + monospace numbers), Robinhood (color-coded P&L that your brain reads instantly), and terminal UIs that traders trust.

**Not** a marketing page. Not a startup dashboard. A tool that respects the trader's time and attention.

---

## 1. Information Architecture

### Screen Structure (top to bottom — Bloomberg-dense order)

```
┌─────────────────────────────────────────────────────────┐
│  HEADER: Logo | Mode pill | Auto toggle | Last updated  │
├─────────────────────────────────────────────────────────┤
│  HERO ROW: Current Balance + Total P&L + Return %       │
│  (3 large numbers — the primary focus)                 │
├─────────────────────────────────────────────────────────┤
│  SECONDARY CHIPS: Realized | Unrealized | Best | Worst  │
│  (5 chips, horizontal scroll on mobile)                │
├─────────────────────────────────────────────────────────┤
│  OPEN POSITIONS (collapsible, LIVE prices when Alpaca)   │
│  Symbol | Side | Qty | Entry | Current | P&L           │
├─────────────────────────────────────────────────────────┤
│  EQUITY CURVE (full width, prominent)                  │
│  Line chart with drawdown shading                      │
├───────────────────────────┬───────────────────────────┤
│  DAILY P&L (30 days)      │  STRATEGY BREAKDOWN      │
│  Bar chart                │  Horizontal bars          │
├───────────────────────────┴───────────────────────────┤
│  RECENT TRADES (last 10, table format)                 │
│  Time | Symbol | Side | Qty | Entry | Exit | P&L       │
└─────────────────────────────────────────────────────────┘
```

**Navigation:** None — single-page dashboard. All data is visible or expandable inline.

---

## 2. Color & Typography

### CSS Custom Properties

```css
:root {
  /* Colors */
  --color-bg-primary: #0A0E14;
  --color-bg-surface: #111620;
  --color-bg-elevated: #1A2030;
  --color-border: #252D3D;
  --color-text-primary: #E8ECF0;
  --color-text-secondary: #6B7A8F;
  --color-text-tertiary: #3D4A5C;
  --color-accent: #00D4AA;
  --color-positive: #00E676;
  --color-negative: #FF5252;
  --color-warning: #FFB300;

  /* Spacing (8px grid) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  /* Border radius — sharp for Bloomberg feel */
  --radius-sm: 4px;
  --radius-md: 4px;  /* no large radius */

  /* Typography */
  --font-ui: 'Instrument Sans', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'Courier New', monospace;
}
```

### Color Palette

```
Background (primary):    #0A0E14  (near-black, blue undertone)
Background (surface):    #111620  (card/panel surfaces)
Background (elevated):    #1A2030  (hover, active states)
Border:                   #252D3D  (subtle separators)
Text (primary):           #E8ECF0  (off-white, easy on eyes)
Text (secondary):        #6B7A8F  (muted labels, timestamps)
Text (tertiary):         #3D4A5C  (disabled, placeholder)
Accent (brand):          #00D4AA  (teal — distinct from Twitter blue)
Positive:                #00E676  (green for profits)
Negative:                #FF5252  (red for losses)
Warning:                 #FFB300  (amber — for caution states)
```

### Typography

```
Font (headings):   "Instrument Sans" (Google Fonts) — sharp, modern, not Inter
Font (body/UI):    "Instrument Sans" — consistent throughout
Font (numbers):    "JetBrains Mono" (Google Fonts) — monospace for all P&L figures
Font (fallback):   system-ui, sans-serif

Scale:
  Balance (hero):      48px / 700 weight / letter-spacing -0.02em
  P&L (hero):         36px / 600 weight
  Section headers:    14px / 600 weight / uppercase / letter-spacing 0.08em
  Labels:             12px / 500 weight / uppercase / letter-spacing 0.06em
  Body/trades:        13px / 400 weight
  Numbers (table):    13px / 500 weight / JetBrains Mono
```

---

## 3. Component Specifications

### Header
- Left: "Trading Champs" wordmark in Instrument Sans 18px/700, accent color
- Right: Mode pill (PAPER / LIVE), Auto toggle (AUTO ON/OFF), last-updated timestamp ("Updated 2s ago")
- Height: 56px, border-bottom: 1px solid #252D3D
- Mode pill: PAPER = teal border + text, LIVE = red border + text. Active mode has filled background
- Auto toggle: ON = teal text "AUTO ON", OFF = muted text "AUTO OFF". Clicking toggles state.

### Hero Stats Row
Three cards in a row:
1. **Current Balance** — label "Balance", value in 48px JetBrains Mono. Color: --color-positive if equity > initial_balance, --color-negative if equity < initial_balance, --color-text-primary if equal.
2. **Total P&L** — label "Total P&L", 36px, --color-positive or --color-negative
3. **Return %** — label "Return", 36px, --color-positive or --color-negative with +/- prefix

Card style: no background fill, no border, just spacing. Numbers float on the dark background — this is intentional. High contrast, maximum visual weight.

### Secondary Metrics Row
Five chips (not cards — smaller, horizontal layout):
- Realized P&L
- Unrealized P&L
- Best Day (highest daily P&L in the period)
- Worst Day (lowest daily P&L in the period)
- Total Trades

Chip style: background #111620, border 1px #252D3D, border-radius 4px, padding 8px 14px, label 10px uppercase muted, value 16px JetBrains Mono. Gap between chips: 8px. Horizontal scroll on mobile.

### Open Positions Section
- Collapsible section, starts open if positions exist, closed if none
- Header: "Open Positions" + count badge + chevron
- Table: Symbol | Side badge | Qty | Entry Price | Current Price | P&L
- P&L column color-coded green/red
- Empty state: "No open positions" with a subtle checkmark icon

### Equity Curve Chart
- Full-width, 240px height
- Line color: accent teal (#00D4AA), 2px stroke
- Fill: gradient from accent at 20% opacity to transparent
- Grid lines: #252D3D (subtle)
- X-axis: dates, muted color
- Y-axis: dollar values, right side
- Hover tooltip: date + equity value + daily change

### Daily P&L Chart
- Bar chart, 30 days
- Positive bars: #00E676, negative bars: #FF5252
- Height: 200px
- Same grid/tooltip style as equity curve

### Strategy Breakdown
- Horizontal bar chart — one bar per strategy
- Bars sorted by P&L descending
- Bar color: teal accent
- Label left, P&L value right
- Height: proportional to number of strategies (min 120px)

### Recent Trades Table
- Columns: Time | Symbol | Side | Qty | Entry | Exit | P&L
- Side column: badge (LONG/SHORT), green/red background 15% opacity
- P&L column: green/red color, JetBrains Mono
- Row hover: background #1A2030
- Max 10 rows, "Show more" link if more exist
- Empty state: "No trades yet. Run your first strategy to see history."

---

## 4. Interaction States

### Loading States
Skeleton specs (replaced with real content when loaded):

**Hero stats:** Three rectangles, 48px height, widths: 160px / 100px / 80px, border-radius 4px, background #1A2030, pulsing shimmer animation (opacity 0.4→0.7→0.4, 1.5s ease-in-out infinite).

**Secondary chips:** Five rectangles, 32px height, 80px width each, border-radius 4px, background #1A2030, same shimmer.

**Open positions table:** 4 skeleton rows, 40px height each, varying content widths (60px symbol, 50px side badge, etc.), same shimmer.

**Equity curve:** Flat horizontal line at mid-height, 2px height, #252D3D color, shimmer sweeping left-to-right over 1.5s.

**Daily P&L bar placeholders:** 10 ghost bars, height 8px each at varying positions, shimmer.

**Trades table:** 5 skeleton rows, 48px height each.

**Numbers (all):** Dash "—" in JetBrains Mono, color --color-text-tertiary.

**Timeout (10s):** Error banner appears: "Connection timed out. [Retry]" — Retry button reloads data once.

### Empty States
- **No data:** Warm empty state. Not "No items found." Instead: "Your portfolio is empty. Start trading to see your P&L here."
- **No trades:** "No trades yet. Run your first strategy to see history."
- **No positions:** "All positions closed. Nice work."

### Error States
- API error banner: top of page, red border (#FF5252 at 20% opacity), text: "⚠ " + error message + " — Showing " + mode + " mode data." + " [Retry]"
- Individual chart failures: chart area shows "Chart unavailable" in --color-text-secondary
- Network timeout (10s): banner says "Connection timed out. [Retry]"
- Retry: re-fetches all data endpoints, resets polling timer

### Alpaca Disconnection State
When Alpaca was connected but disconnects mid-session:
- Open positions section header shows amber warning dot: "Open Positions ⚠"
- Tooltip on warning: "Live prices unavailable — Alpaca disconnected"
- Current prices fall back to tracker entry prices (P&L may be stale)
- No automatic reconnection — user must refresh page to reconnect

### Mode Toggle
- Two-state pill: PAPER | LIVE
- Switching mode re-fetches all data (shows skeleton states during reload)
- URL updates with ?mode= parameter

---

## 5. Responsive Behavior

### Desktop (1024px+)
Full layout as described above. Two-column for Daily P&L + Strategy Breakdown side by side.

### Tablet (768px - 1023px)
Hero stats remain large. Secondary chips wrap to 2x2. Charts stack vertically. Trades table horizontal scroll with sticky first column.

### Mobile (375px - 767px)
Hero stats: Balance large (36px), P&L and Return below (24px). Chips: horizontal scroll. Charts: full width, reduced height (180px equity, 160px others). Trades: card layout (not table) — one trade per card, stacked.

**Mobile trade card layout (top to bottom):**
1. Row 1: Symbol (bold, 16px) + Side badge (LONG/SHORT, colored) + P&L amount right-aligned (green/red, 16px JetBrains Mono)
2. Row 2: Entry price + Exit price (muted, 13px)
3. Row 3: Qty + timestamp (muted, 12px, --color-text-secondary)

No hover state on mobile (touch). No "Show more" link — all 10 trades shown.

### Mobile Navigation
No hamburger menu — single page, all content visible or expandable.

---

## 6. Technical Constraints

- Single HTML file (`dashboard.html`) — no build step, no framework
- External dependencies: Chart.js 4.x (cdn), DOMPurify (cdn), Google Fonts
- No Tailwind, no component library — pure CSS custom properties
- All data fetched from existing API endpoints: `/api/dashboard`, `/api/equity-curve`, `/api/strategy-curves`
- Mode switching: `?mode=paper|live` query param on all endpoints
- Error banner construction: "⚠ " + error message + " — Showing " + mode + " mode data."

---

## 7. Accessibility

- All charts have `aria-label` describing the data shown:
  - Equity curve: "Equity curve from {start} to {end}. Starting at ${start_val}, currently ${cur_val}. Return: {pct}%"
  - Daily P&L: "Daily P&L bar chart for the last 30 days. {positive_count} winning days, {negative_count} losing days."
  - Strategy: "Strategy performance breakdown. {n} strategies shown."
- Color is not the only indicator — P&L values have +/- prefix, green/red color AND ▲/▼ triangle icons
- Keyboard navigable: Mode toggle (Tab), Auto toggle (Tab), collapsible sections (Enter/Space to expand), trade table (arrow keys)
- Touch targets: minimum 44px height for all interactive elements
- Reduced motion: `prefers-reduced-motion` — disable Chart.js animations, no shimmer

---

## 8. Performance

- Charts render after all data is fetched (no layout shift)
- `loading="lazy"` on below-fold charts
- DOMPurify sanitizes all HTML from API
- 30s auto-polling by default. Auto toggle in header lets user disable it.

---

## 9. Not in Scope

- Historical backtest comparison (vs live)
- Multiple portfolio support
- Trade execution from dashboard
- Notifications/alerts
- Export to CSV/PDF

---

## 10. What Already Exists

- `dashboard.html` — current implementation (to be replaced)
- `pl/dashboard.py` — `DashboardProvider` class providing all required data
- API endpoints: `/api/dashboard`, `/api/equity-curve`, `/api/strategy-curves` — no changes needed
- Chart.js 4.x and DOMPurify already in use — can continue

---

## 11. Implementation Phases

### Phase 1: Skeleton + Typography (foundation)
- CSS custom properties (colors, fonts)
- Google Fonts loaded (Instrument Sans, JetBrains Mono)
- HTML structure (header, hero stats, secondary chips)
- No data yet — all values show "—"

### Phase 2: Data + Charts
- Wire up API endpoints
- Render metric values
- Equity curve + Daily P&L charts
- Strategy breakdown chart
- Recent trades table

### Phase 3: Polish
- Open positions section
- Error/loading/empty states
- Mode toggle with URL sync
- Responsive layout
- Accessibility audit

---

## Design Decisions Log

All decisions made during design review. This is the authoritative reference for implementation.

### DECISION 1: Aesthetic Direction — LOCKED ✓
**Bloomberg-Dense** wins. The design now follows these constraints:
- Tight spacing (16px between sections)
- Sharp edges (4px radius only — no rounded "app" feel)
- JetBrains Mono for all numeric values, Instrument Sans for labels/headings
- Muted surfaces — no card elevation/shadows
- Trades table is the data-dense centerpiece
- Color palette: teal accent (#00D4AA), green positive (#00E676), red negative (#FF5252)
- No decorative elements — every pixel earns its place

### DECISION 2: Open Positions Above Charts — LOCKED ✓
Open positions section moves above the equity curve. Order is now:
1. Header
2. Hero stats (Balance, Total P&L, Return %)
3. Secondary chips (Realized, Unrealized, Best Day, Worst Day)
4. Open Positions ← above charts
5. Equity Curve
6. Daily P&L + Strategy Breakdown side by side
7. Recent Trades

### DECISION 3: Secondary Metrics — LOCKED ✓
Win Rate replaced with **Best Day** and **Worst Day** (highest and lowest daily P&L in the period). These are more actionable than win rate. Final secondary chips: Realized P&L | Unrealized P&L | Best Day | Worst Day | Total Trades (5 chips, horizontal scroll on mobile).

### DECISION 4: Open Positions Live Prices — LOCKED ✓
Open positions show live Alpaca prices when connected. Falls back to tracker entry price when Alpaca is disconnected. Live P&L recalculates on every poll cycle.

### DECISION 5: Auto-Refresh — LOCKED ✓
30s polling is the default. No manual refresh button. An auto-toggle pill in the header (next to mode toggle) lets users disable polling: "AUTO | ON/OFF". When OFF, data loads once on page load and never again until page refresh.

### DECISION 6: Number Format — LOCKED ✓
Full format always: $10,523.47. No abbreviation. Traders need precision. JetBrains Mono handles the visual density of full numbers.

### DECISION 7: Header Controls — LOCKED ✓
Header: Logo wordmark | Mode pill (PAPER/LIVE) | Auto toggle (AUTO ON/OFF) | Last updated timestamp
No settings icon. No refresh button. Mode and auto-toggle are the only controls.
