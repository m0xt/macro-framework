# Macro Framework

A macro regime indicator system that signals when to be invested (green) vs in cash (red), with a comprehensive business cycle backdrop. Built for a portfolio manager's daily workflow: one glance tells you what to do, a scorecard tells you why, and the cycle chart tells you where you are.

## Setup

```bash
git clone https://github.com/your-org/macro-framework
cd macro-framework
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Quick Start

```bash
# Build dashboard (uses cached data if < 12h old)
.venv/bin/python build.py --open

# Force fresh data
.venv/bin/python build.py --no-cache --open
```

## Optional: AI Commentary

The dashboard can generate a daily AI brief using Claude. To enable it, set your own Anthropic API key:

```bash
export ANTHROPIC_API_KEY=your_key_here
.venv/bin/python generate_commentary.py
```

Without the key the dashboard works fully — the brief card is simply omitted.

## Presentation

Open `presentation.html` in any browser for a walkthrough of how the framework works.

## Dashboard Layout

The dashboard follows a PM's decision hierarchy:

### Tier 1: The Decision — MRMI
The primary signal. Green = invested, red = cash. Alpha-weighted average of 3 regime indicators with S&P 500, Russell, and Bitcoin price overlays. Backtest stats shown below the chart.

| Component | What it measures | Speed | Weight |
|-----------|-----------------|-------|--------|
| Growth Impulses (GII) | 10-component economic momentum | Fast (21d ROC) | 37% |
| Sector Breadth | 7 cyclical sector ETFs | Fast (63d lookback) | 35% |
| Financial Conditions | VIX + MOVE + HY spread | Slow (252d lookback) | 28% |

### Tier 2: The Why — Scorecard
Compact table showing the three MRMI drivers at a glance:
- **Value**: current z-score reading (colored positive/negative/neutral)
- **7d / 30d**: change over those windows with direction arrow
- **Signal**: green/red dot for each regime indicator

**Click any row** to expand a full chart inline. Click again to collapse.

### Tier 3: Where You Are — Macro Seasons

Two charts showing the cycle context:

1. **Macro Seasons scatter** — 2D chart with Growth composite on the Y-axis and Core CPI YoY minus 2% Fed target on the X-axis. The current dot shows which quadrant (season) the economy is in. Labeled dots show where it was 1, 3, 6, and 12 months ago.

2. **Growth & Inflation Over Time** — time-series chart with Growth composite (left axis, z-score) and Core CPI YoY (right axis, %) shown together. Dashed reference lines at zero (growth) and 2% (inflation target).

Below the charts: two scorecard sections — **Y-Axis: Growth** (Real Economy + Labor) and **X-Axis: Inflation** (Core CPI) — each with expandable charts.

| Season | Growth | Inflation |
|--------|--------|-----------|
| Spring | ↑ Expanding | Below 2% target |
| Summer | ↑ Expanding | Above 2% target |
| Fall | ↓ Contracting | Above 2% target |
| Winter | ↓ Contracting | Below 2% target |

**This is context only** — not a trading signal. Tested mixing with MRMI; it reduced alpha.

## Backtest Results (out-of-sample: 2023-2026)

**MRMI (alpha-weighted average):**

| Asset | Buy & Hold | Signal-Only | Alpha | MaxDD reduction |
|-------|-----------|-------------|-------|-----------------|
| S&P 500 | +11.6%/yr | +25.7%/yr | **+14.0%/yr** | -18.9% -> -2.9% |
| Russell 2000 | +10.3%/yr | +32.6%/yr | **+22.4%/yr** | -27.5% -> -7.5% |
| Bitcoin | +17.0%/yr | +40.5%/yr | **+23.4%/yr** | -49.7% -> -35.6% |

Green ~65-72% of the time. ~15 regime flips per year. ~17 day average regime duration.

## Optimized Parameters

All parameters optimized via grid search with 70/30 in-sample/out-of-sample split (2016-2023 / 2023-2026).

### GII (changed from PineScript original)
- `fast_roc=21` (was 42), `slow_roc=126` (was 252), `z_len=504`, no EMA (was 21)
- Mode: fast composite only (was both fast+slow > 0)

### Financial Conditions (changed from original)
- `lookback=252` (was 126), components: VIX + MOVE + HY spread (dropped IG)

### Sector Breadth (changed from original)
- `lookback=63` (was 252), dropped SLX (7 ETFs: SMH, IWM, IYT, IBB, XHB, KBE, XRT)

### Macro Seasons
- Y-Axis (Growth): CFNAI z-score + 252d z-score of YoY growth in INDPRO/HOUST/PERMIT + 252-day z-score of inverted jobless claims (ICSA + CCSA)
- X-Axis (Inflation): Core CPI YoY minus 2% Fed target

## Data Sources

**Yahoo Finance:** HYG, XLY, XLP, XLI, XLU, SPHB, SPLV, HG=F, GC=F, ^VIX, ^TNX, ^MOVE, SMH, IWM, IYT, IBB, XHB, KBE, XRT, SLX, BDRY, BTC-USD, ^GSPC, DBC, UPS, FDX, CAT, HON, DOV, FAST, IWC, DJT, CBON

**FRED (CSV, no API key):** BAMLH0A0HYM2, BAMLC0A0CM, WEI, DGS10, DGS2, DGS3MO, DTWEXBGS, WALCL, WTREGEN, RRPONTSYD, ICSA, CCSA, T5YIE, T10YIE, DFII10, CFNAI, INDPRO, HOUST, PERMIT, DRTSCILM

Data cached in `.cache/raw_data.pkl` for 12 hours.

## Re-optimizing

```bash
.venv/bin/python optimize.py fincon          # individual indicator
.venv/bin/python optimize.py gii
.venv/bin/python optimize.py breadth
.venv/bin/python optimize.py liquidity
.venv/bin/python optimize.py composite       # composite combination method
.venv/bin/python optimize.py mktcycle        # business cycle backtest
.venv/bin/python optimize.py fincon --btc    # optimize for BTC instead of SPX
.venv/bin/python optimize.py fincon --iwm    # optimize for Russell
```

## Files

```
build.py                    # Data fetch, indicator calculation, dashboard generation
optimize.py                 # Parameter grid search and backtesting
robustness.py               # Walk-forward and benchmark robustness tests
generate_report_charts.py   # Matplotlib charts for monthly report
build_report.py             # Markdown-to-HTML report builder
requirements.txt            # Python dependencies
README.md                   # This file
GUIDE.md                    # Complete framework explanation
CLAUDE.md                   # Context for Claude Code sessions
MACRO_FRAMEWORK_ROADMAP.md  # Future ideas and roadmap
.cache/
  raw_data.pkl              # Cached market data (auto-refreshes every 12h)
  dashboard.html            # Self-contained interactive dashboard
  presentation.html         # Framework presentation
  snapshots/                # Daily JSON state snapshots
  charts/                   # Generated PNG charts for reports
```
