# Macro Framework — Claude Context

## What this is
Macro regime indicator system with a 3-tier dashboard:
1. **MRMI** (top) — green = invested, red = cash. Alpha-weighted: GII 37%, Breadth 35%, FinCon 28%. Includes MRMI chart + drivers scorecard (GII, Breadth, FinCon).
2. **Market Context** (transition) — one-line bridge explaining the compass is cycle context, not a trading signal.
3. **Macro Seasons** (bottom) — 2-axis scatter showing current macro season. Vertical = Growth composite (Y-axis). Horizontal = Core CPI YoY minus 2% Fed target (X-axis). Four quadrants: Spring/Summer/Fall/Winter. Followed by a Growth & Inflation time-series chart (dual Y-axis: growth composite + Core CPI YoY), then compass input scorecards (Y-Axis: Growth, X-Axis: Core CPI).

Dashboard at `.cache/dashboard.html`.

## Key commands
- `.venv/bin/python build.py --open` — rebuild dashboard
- `.venv/bin/python build.py --no-cache --open` — force fresh data
- `.venv/bin/python optimize.py composite` — re-optimize composite
- `.venv/bin/python optimize.py gii` — re-optimize individual indicator

## Architecture
- `build.py` — single file: fetch data, calculate all indicators, generate HTML dashboard
- `optimize.py` — grid search backtester for all indicators + composite
- Data: Yahoo Finance (33 tickers) + FRED CSV (14 series, no API key)
- Dashboard: self-contained HTML with Chart.js, all data embedded as JSON

## Indicators

### Regime signals (in composite)
- **GII:** fast_roc=21, slow_roc=126, z_len=504, no EMA, fast-only mode
- **Breadth:** lookback=63, drop SLX (7 ETFs)
- **FinCon:** lookback=252, VIX+MOVE+HY (no IG)
- Composite OOS alpha: SPX +14%, IWM +22.4%, BTC +23.4%

### Macro Seasons (context only — not a trading signal)
Two axes define the current macro season:
- **Growth (Y-axis):** Real Economy (CFNAI + INDPRO/HOUST/PERMIT YoY z-scored) + Labor (inverted ICSA+CCSA). Above zero = expanding.
- **Inflation (X-axis):** Core CPI YoY minus 2% Fed target. Right of center = above target.
- Four seasons: Spring (growth↑, inflation below target), Summer (growth↑, above target), Fall (growth↓, above target), Winter (growth↓, below target)
- Hero banner shows season name + Core CPI YoY value (colored orange if above 2%, green if below) with "vs 2% target" label
- Data freshness dates shown inline next to each axis label in the scorecard sections
- 7d delta not shown for Core CPI (monthly data); 30d delta shown in pp

### What's excluded from the dashboard
- Credit & Money (Fed liquidity, yield curve, real rates, SLOOS): tested as regime signal → negative alpha OOS. Removed from display.
- Breakevens (T5YIE, T10YIE): no directional signal. Removed from display.
- Season action text (e.g. "→ Favor cyclicals"): removed — compass is context only, not a buy/sell signal.

## Key decisions
- GII uses fast-only mode (both>0 was green only 5% of time)
- IG spread and SLX dropped — noise
- Liquidity tested as regime signal: negative alpha OOS. Removed entirely.
- Business cycle tested as composite gate/modifier: hurt performance. Keep separate.
- GEI (Global Economy Index) removed — redundant, noisy
- BDI removed — no signal value
- CN10Y proxied via inverted CBON (VanEck China Bond ETF)
- Inflation kept separate from cycle composite (ambiguous directionality)
- Compass uses Core CPI YoY (not breakevens) as X-axis driver

## Dependencies
Python .venv: yfinance, pandas, numpy, requests
