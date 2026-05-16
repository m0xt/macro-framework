# Macro Framework — Complete Guide

## The Investment Thesis

Markets move because of two things: **fundamentals** (the actual economy) and **market dynamics** (price action, volatility, sector rotation, credit spreads). Most of the time these reinforce each other. When they don't, you get the most interesting market moves — and the highest risk of being wrong.

This framework separates the two and only acts when they agree:

- A **fast, market-derived signal** (MMI) catches turning points early.
- A **slow, economy-derived buffer** (Macro Stress) prevents over-reaction by demanding fundamental confirmation before the framework moves to cash.

The combination is **MRMI — Milk Road Macro Index** — a single composite number designed for a weekly research cadence (Tuesday meetings) and same-week execution.

---

## How To Read The Dashboard

The dashboard is a four-step walkthrough wrapped by a hero with the headline number.

### Hero — the at-a-glance read

The first thing you see, designed so anyone in a Tuesday meeting can read it in 10 seconds:

- **Big number** (e.g. `+1.14`) — the current MRMI value.
- **State** — `STAY LONG` (green) or `CASH` (red), with `100% position` or `0% position`.
- **Scale bar** — visual showing where the value sits between −3 and +5, with the `0 · threshold` line marked.
- **What's behind it** — the two pillar states side-by-side: MMI (`GREEN +0.64`) and Macro Stress (`OFF`).
- **This week's read** — AI-generated weekly brief (5–7 sentences) synthesizing the cross-pillar story.

### Step 1 — How the index has evolved

MRMI history chart. White line = MRMI value over time. Green shading = LONG regime, red = CASH. Range tabs (1Y / 2Y / 5Y / ALL). The legend lets you toggle SPX, Russell, BTC, and the underlying MMI line as overlays. Backtest stats sit in a click-to-expand panel below the chart.

This is the chart you walk into the meeting with. Everyone glances at it, sees where the regime has been, and the conversation starts.

### Step 2 — What the markets are signaling (Market pillar)

**MMI — Market Momentum Index.** The fast, market-derived half of MRMI: built entirely from price and volatility data — credit spreads, cyclical sector breadth, and financial-conditions volatility. Markets react quickly so MMI catches turning points early; the trade-off is they can also flash false alarms, which is why MMI alone never triggers a CASH call.

A single white-line chart shows MMI over time, followed by the **weekly market pillar brief** and an open drivers scorecard with the three components (GII / Breadth / FinCon). Click any driver row to expand its individual chart.

### Step 3 — What the economy is signaling (Economy pillar)

**Macro Stress.** The slow, economy-derived half of MRMI: built entirely from real-economy data and inflation trajectory. The chart shows the two underlying axes — Real Economy Score (white solid, left axis) and Inflation Direction Δ6m (amber dashed, right axis). Stress fires only when growth is weak **and** inflation is rising — that AND condition filters out the false alarms the market pillar would otherwise produce on its own.

The economy moves slowly (most data refreshes monthly), so this layer takes time to build. That's a feature: it sets the strategic backdrop, while MMI handles the tactical decision.

The **weekly economy pillar brief** sits between the chart and the drivers (PCE / Sahm / Real Income / GDPNow). The top brief in the hero builds on both pillar briefs.

### Step 4 — Reference Library

Supplementary indicators that round out the picture but aren't in the formal signal. Click any row to expand. These are kept for divergence-spotting and as candidates for promotion into the pillars as the framework evolves.

---

## How MRMI is Computed

```
Stress_intensity = min(1, max(0, −Real_Economy) × max(0, Inflation_Direction))
Macro_buffer     = buffer_size × (1 − Stress_intensity)         # buffer_size = 1.0
MRMI             = MMI + Macro_buffer − threshold                # threshold = 0.5

MRMI > 0  → LONG  (stay invested)
MRMI < 0  → CASH  (step aside)
```

The mechanics:

- When the economy is healthy (`Real_Economy ≥ 0` *or* `Inflation_Direction ≤ 0`), `Stress_intensity = 0` and the macro buffer is at full strength. MRMI ≈ MMI + 0.5, so MMI has to be deeply negative (below −0.5) before MRMI flips to CASH.
- When stress builds (both conditions adverse), `Stress_intensity` rises toward 1.0, eroding the buffer. At full stress, MRMI ≈ MMI − 0.5, so even moderately negative MMI flips the signal to CASH.

The multiplicative AND gate is what makes the system honest: stress can only build when the economy is *both* weakening and seeing rising inflation. Either alone is not enough. Markets can flash false alarms; the buffer keeps you long until fundamentals confirm.

---

## The Market Pillar — MMI

MMI is the equal-weighted (1/1/1) average of three market-derived indicators calibrated to different speeds. Equal weights were selected by drawdown-optimization grid search — they deliver stronger Calmar ratios than the prior alpha-weighted (37/35/28) scheme and survive OOS validation better.

### Growth Impulses Index (GII) — ⅓ weight

**What it measures**: A composite of 10 components reflecting the rate of change of economic momentum (priced through markets):
- HYG (high-yield bond ETF) — credit risk appetite
- HY credit spread (inverted) — credit stress
- XLY/XLP ratio — consumer discretionary vs staples (offensive vs defensive consumption)
- XLI/XLU ratio — industrials vs utilities (cyclical vs defensive sectors)
- SPHB/SPLV ratio — high-beta vs low-volatility stocks (risk appetite)
- Copper — Dr. Copper, the global growth bellwether
- VIX (inverted) — equity volatility
- Yield curve (10Y minus 2Y) — recession risk
- Weekly Economic Index (WEI) — high-frequency GDP proxy
- Baltic Dry Index proxy (BDRY) — global trade/shipping demand

Each component is converted to a 21-day rate of change, z-scored over 504 days, and clipped to ±3 sigmas. The fast composite is the equal-weighted average of these z-scores.

**Why it works**: Each component captures a different facet of risk appetite or economic activity. Credit markets often lead equities. Sector rotation reflects forward-looking economic expectations. Copper signals global industrial demand. Combined, they paint a picture of whether momentum is accelerating or decelerating across many independent dimensions.

**Why fast (21-day ROC)**: Economic momentum shifts manifest in markets within weeks, not months. A 21-day ROC catches inflection points before they become obvious in slower data.

### Sector Breadth — ⅓ weight

**What it measures**: The z-score (over 90 days) of 7 cyclical sector ETFs. Provenance: `src/macro_framework/macro_pipeline.py` has used `LOOKBACK = 90` since commit `9f124cf` ("optimized for drawdown: was 63"); docs were reconciled to production on 2026-05-15 without changing math.
- SMH — semiconductors (the AI/cycle barometer)
- IWM — small-cap stocks (most economically sensitive)
- IYT — transports (Dow Theory: transports lead the broader market)
- IBB — biotech (high-beta growth)
- XHB — homebuilders (housing leads the economy)
- KBE — banks (credit creation, NIM)
- XRT — retail (consumer health)

Equal-weighted z-score average.

**Why it works**: A healthy bull market has broad participation. When most cyclical sectors are above their historical average, demand is broad and the rally is sustainable. When only a few sectors lead while most lag, you get "narrow leadership" which historically precedes corrections (think 1999, early 2022).

**Why these 7 sectors**: They're the most cyclically sensitive parts of the market. SLX (steel) was tested and excluded — too noisy. The remaining 7 cover the key economic verticals: tech, small caps, transport, healthcare innovation, housing, financials, consumer.

### Financial Conditions (FinCon) — ⅓ weight

**What it measures**: Z-score (over 252 days) of three stress indicators:
- VIX — equity volatility (fear gauge)
- MOVE — bond market volatility
- BAML High-Yield Spread — credit risk premium

**Why it works**: Financial conditions are the "weather" in which assets trade. Tight conditions (high VIX, wide spreads) mean any negative news amplifies. Loose conditions mean even bad news gets shrugged off. This is structural — it changes slowly over months, not days.

**Why slow (252-day lookback)**: Unlike GII and Breadth which are tactical, this captures structural stress regimes. The 2018 Q4 selloff, COVID 2020, 2022 bear market — all featured persistent multi-month elevated FinCon readings. The 252-day window catches these regimes without overreacting to single events.

**Why VIX + MOVE + HY (no IG)**: We tested adding IG (investment-grade) credit spreads. They didn't add signal — too correlated with HY but with less noise reduction. The three retained capture equity vol, bond vol, and credit risk — three independent dimensions of market stress.

### Why these three together

The three indicators are calibrated to different speeds (21d / 90d / 252d) and capture different forces:
- **GII** = economic momentum (real economy + market signals)
- **Breadth** = market participation
- **FinCon** = financial stress

When all three agree, MMI is high-conviction. When they disagree, MMI is weak — signaling uncertainty. The diversification across timescales means at least one indicator typically catches a regime change while the others confirm. Weight-sensitivity testing confirms equal weights produce positive alpha across SPX/IWM/BTC, and even drop-one tests preserve the edge — no single component is carrying the result.

---

## The Economy Pillar — Macro Stress

Macro Stress is a 0–1 score capturing how deep we are inside the stagflation pocket. Two underlying axes feed the AND gate.

### Real Economy Score

**What it measures**: Equal-weighted z-score (3-year window) of:
- **Real PCE YoY** — consumer growth (~70% of GDP)
- **Sahm Rule (inverted)** — forward-looking labor stress; the rule fires (suggesting recession) when 3-month-MA unemployment rises >0.5pp from its 12-month low
- **Real Personal Income YoY** — household income trajectory in inflation-adjusted terms
- **Atlanta Fed GDPNow** — real-time nowcast of current-quarter GDP growth

**Why these four**: Each captures a different facet of real-economy health. PCE is the demand-side dominant component. Sahm flags labor-market deterioration before recessions. Real income is what consumers actually have to spend. GDPNow is the highest-frequency real-time GDP read available.

**Why z-scored**: Levels matter less than trend. A z-score over 3 years tells you whether each measure is above or below its recent norm — the signal is "is the economy weakening relative to where it's been?", not "is GDP positive?"

### Inflation Direction

**What it measures**: Δ Core CPI YoY over the last 6 months, in pp. Positive = inflation accelerating, negative = decelerating.

**Why direction, not level**: The framework is about *whether stress is building*, not whether inflation is high. Inflation can be high and falling (as in 2023), which is disinflationary and not stress-inducing. Inflation can be low and rising (as in early 2021), which is reflationary and warrants attention. The 6-month change captures the trajectory the Fed is actually responding to.

**Why Core CPI**: Excludes food and energy noise. It's the realized inflation the Fed actually targets.

### The AND gate

```
Stress_intensity = min(1, max(0, −Real_Economy) × max(0, Inflation_Direction))
```

Production locks: stress is clipped to `[0, 1]`; dashboard `stress_on` fires above 0.5; MRMI defaults are `buffer_size=1.0` and `threshold=0.5`; macro release lags are PCE/RPI 60d, unemployment 35d, Core CPI 45d, GDPNow 0d.

The two `max(0, …)` clips mean each factor only contributes when it's adversely positioned: weak growth (RE < 0) and rising inflation (Inf_Dir > 0). The product is non-zero only when *both* are adverse — that's the stagflation pocket. This is the one macro condition that overrides the buffer and pulls MRMI toward CASH.

A consequence of the AND gate: when the economy is healthy on either dimension, stress sits flat at 0 regardless of the other. The chart will look uneventful in benign regimes — that's by design. Stress firing is rare *and meaningful*.

---

## Why the Combination Makes Sense

The two pillars are deliberately complementary:

| | Market pillar (MMI) | Economy pillar (Macro Stress) |
|--|----------------------|-------------------------------|
| **Source** | Price / volatility data | Real-economy + inflation data |
| **Speed** | Fast (intraday → days) | Slow (weeks → months) |
| **Strength** | Catches turning points early | Grounded in fundamentals |
| **Weakness** | False alarms (vol spikes, single-day moves) | Lags, noisy month-to-month |
| **Role in MRMI** | Headline signal | Buffer / confirmation |

Markets can flash false alarms — a single VIX spike, a credit-spread blow-out from a single name, a sector rotation that reverses in days. The economy can't fake it: if PCE is weakening *and* core CPI is accelerating over six months, that's a real condition. Requiring both pillars to agree before flipping to CASH is what cuts whipsaw risk while preserving alpha.

The historical evidence: backtested 2016–2026, the production framework (equal-weighted MMI + macro buffer) delivers **+9.6% / +12.9% / +2.1%** OOS annual alpha on SPX / Russell / BTC, with SPX max drawdown reduced from −18.9% to −4.8%. Walk-forward shows positive SPX and IWM alpha in 10 out of 10 years (2017–2026).

**Honest caveat — MMI standalone vs MRMI in the current OOS.** Bare MMI (no buffer) posts higher OOS alpha than MRMI right now (+12.6% vs +9.6% on SPX). That's not a defect: the buffer is *designed* to keep us invested through false alarms, and the OOS window happens to contain no real stagflation event, so the buffer pays a tax for protection it wasn't asked to provide. The buffer's value shows up in 2018, 2020, and 2022 in walk-forward — those are the years it sidestepped major SPX drawdowns. The framework is built for full cycles, not calm periods.

---

## What the Framework Doesn't Do

- **Predict** — it reacts to current conditions. The signal lags economic releases by their natural cadence.
- **Asset selection** — it tells you risk-on or risk-off, not which assets to buy within a regime.
- **Position sizing** — that's a separate decision.
- **Sub-regime nuance** — it's binary (LONG / CASH). Magnitude tells you confidence, not allocation.

---

## The AI Briefs (Three-Tier, Weekly Tuesday)

The framework includes three AI-generated briefs that translate the numbers into prose for the Tuesday research meeting:

1. **Market pillar brief** — what the markets are signaling this week, focused on GII / Breadth / FinCon and their drivers.
2. **Economy pillar brief** — what the economy is signaling this week, focused on the Real Economy Score and Inflation Direction trajectories.
3. **Top brief** — synthesis. Reads both pillar briefs and writes the cross-pillar story that goes in the hero.

Generation order is **always pillar briefs first, then top brief** — the synthesis builds on fresh foundations rather than re-deriving the underlying analysis. All three are generated via the `claude` CLI (Claude Code subscription), with WebSearch enabled for current macro context.

Cadence is **lazy weekly Tuesday**: a brief is stale if its archive date is older than the most recent Tuesday on or before today. Past briefs are git-tracked under `briefs/YYYY-MM-DD/` and preserved forever — week-over-week evolution is auditable.

---

## Weekly Workflow

**Tuesday morning, before the macro-research meeting:**

1. Run `.venv/bin/python -m macro_framework.build` to refresh data, write the snapshot, and render the dashboard. Brief generation triggers automatically if any are stale.
2. Open `outputs/dashboard.html`. Skim the hero (number, state, this week's read).
4. Click into Step 1 to see how the regime has evolved over the chosen lookback.
5. Read the market pillar brief (Step 2) and economy pillar brief (Step 3) before the meeting.
6. In the meeting: project the dashboard, walk through the four steps in order. The briefs are pre-meeting prep, not slide content.

**Mid-week reviews**: skip brief regeneration (it's gated to Tuesday). Just refresh the data if you want updated charts.

**Annual review**: re-optimize MMI weights, reassess the buffer/threshold parameters, validate Real Economy Score components against any new data series.

---

## Limitations

1. **Same-week execution required.** Briefs and signal cadence are weekly. Same-day execution within Tuesday's meeting is sufficient — but a Wednesday→Friday delay erodes meaningful edge.
2. **No data before 2016.** Cannot test against 2008 or dot-com.
3. **Binary signal.** Tells you in/out, not how much.
4. **Macro can be wrong.** Markets sometimes diverge from macro for extended periods (e.g., AI-driven rally during tightening cycle 2023–2024). The framework will lag those.

The framework is designed to win over many cycles with disciplined execution, not to be right every time.
