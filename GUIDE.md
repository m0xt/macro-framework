# Macro Framework — Complete Guide

## The Investment Thesis

Markets move because of two things: **fundamentals** (the actual economy) and **market dynamics** (price action, volatility, sector rotation, credit spreads). Most of the time these reinforce each other. When they don't, you get the most interesting market moves — and the highest risk of being wrong.

This framework separates the two and only cuts risk aggressively when they agree:

- A **fast, market-derived signal** (MMI) catches turning points early.
- A **slow, economy-derived buffer** (Macro Stress) prevents over-reaction by demanding fundamental confirmation before the framework moves all the way to cash.

The combination is **MRMI — Milk Road Macro Index** — a single composite number designed for a weekly research cadence and same-week execution. The output is an investor-grade allocation posture: LONG, CAUTION, or CASH.

---

## How To Read The Dashboard

The dashboard is a four-step walkthrough wrapped by a hero with the headline number.

### Hero — the at-a-glance read

The first thing you see, designed so anyone in a Tuesday meeting can read it in 10 seconds:

- **Big number** — the current MRMI value.
- **State** — `LONG` (100% exposure), `CAUTION` (75% exposure), or `CASH` (0% exposure).
- **Scale bar** — subtle visual showing where the value sits between −3 and +5, with `−0.50 · cash` and `+0.25 · long` threshold lines marked and labels anchored outward so they don't collide.
- **What's behind it** — the two pillar states side-by-side: MMI (`GREEN`/`RED`) and Macro Stress (`CALM`/`WATCH`/`BUILDING`/`ELEVATED`).
- **This week's read** — a plain-English weekly brief synthesizing the cross-pillar story.

### Step 1 — How the index has evolved

MRMI history chart. White line = MRMI value over time. Green zone = LONG, amber = CAUTION, red = CASH. The CAUTION band is intentionally more visible than the other background zones because that is the investor-grade middle posture. Range tabs (1Y / 2Y / 5Y / ALL) and legend toggles let you overlay SPX, Russell, BTC, and the underlying MMI line. Backtest stats sit in a click-to-expand panel below the chart.

This is the chart you walk into the meeting with. Everyone glances at it, sees where the regime has been, and the conversation starts.

### Step 2 — What the markets are signaling (Market pillar)

**MMI — Market Momentum Index.** The fast, market-derived half of MRMI: built entirely from price and volatility data — credit spreads, cyclical sector breadth, and financial-conditions volatility. Markets react quickly so MMI catches turning points early; the trade-off is they can also flash false alarms, which is why MMI alone never triggers a CASH call.

A single white-line chart shows MMI over time, followed by the **weekly market pillar brief** and an open drivers scorecard with the three components (Growth Impulses / Sector Breadth / Financial Conditions). Click any driver row to expand its individual chart. The mini-brief sits directly below that driver chart, followed by the input drill-down.

Each input drill-down uses the same pattern:

- deterministic mini-brief explaining the latest top mover, current support/drag, breadth, and next-watch condition;
- table columns: Input / Group / Current z / 7d zΔ / 30d zΔ;
- rows sorted by absolute current z-score so the strongest positive and negative signals rise first;
- compact keyboard-focusable `i` tooltips explaining each input;
- raw input history chart controlled by either the dropdown or row click.

### Step 3 — What the economy is signaling (Economy pillar)

**Macro Stress.** The slow, economy-derived half of MRMI: built from real-economy data and inflation trajectory. The dashboard shows a unified 0–10 stress score plus the two underlying axes — Real Economy Score and Inflation Direction Δ6m. Stress is calm by default, can start building when either growth weakens or inflation rises, and builds fastest when both hit together.

The economy moves slowly (most data refreshes monthly), so this layer takes time to build. That's a feature: it sets the strategic backdrop, while MMI handles the tactical decision.

The **weekly economy pillar brief** sits between the stress input chart and the real-economy driver rows (PCE / Sahm / Real Income / GDPNow). The top brief in the hero builds on both pillar briefs.

### Step 4 — Reference Library

Supplementary indicators that round out the picture but aren't in the formal signal. Click any row to expand its chart. The current library includes:

- liquidity: US M2 Money Supply;
- activity: ISM Manufacturing PMI, GDPNow, CFNAI, Industrial Production, Housing Starts, Building Permits;
- inflation: official headline CPI, official core CPI, official PPI all commodities;
- labor: initial and continuing jobless claims.

These are kept for divergence-spotting and as candidates for future promotion into the pillars as the framework evolves. ISM Manufacturing PMI is sourced from the DBnomics ISM mirror, charted as recovered monthly observations, and filters the mirror's suspicious 2025 low-teens tail until a cleaner feed exists.

---

## How MRMI is Computed

```text
g                = max(0, −Real_Economy)
i                = max(0, Inflation_Direction)
Stress_raw       = 0.75 × g + 0.50 × i + 10 × g × i
Stress_intensity = clip(Stress_raw / 10.0083, 0, 1)
Stress_score     = 10 × Stress_intensity
Macro_buffer     = buffer_size × (1 − Stress_intensity)         # buffer_size = 0.5
MRMI             = MMI + Macro_buffer − threshold                # threshold = 0.75

MRMI < -0.50           → CASH    (0% exposure / capital preservation)
-0.50 <= MRMI <= +0.25 → CAUTION (75% exposure / stay invested but less aggressive)
MRMI > +0.25           → LONG    (100% exposure / full risk exposure)
```

The mechanics:

- When the economy is healthy and stress is calm, the macro buffer is near full strength. MRMI ≈ MMI + 0.5 − 0.75, so MMI has to be meaningfully negative before posture falls all the way to CASH.
- When stress builds, `Stress_intensity` rises toward 1.0 and erodes the buffer. At full stress, MRMI ≈ MMI − 0.75, so weak MMI can move the posture through CAUTION and into CASH.
- CAUTION is the deliberately wide middle state. It keeps the framework invested but less aggressive when the headline value is between the cash and long thresholds.

The unified OR+AND stress formula is what makes the system honest: stress can build when either growth weakens or inflation rises, and it builds fastest when both hit together. Markets can flash false alarms; the posture layer keeps the index investor-grade instead of forcing a binary trading call around zero.

---

## The Market Pillar — MMI

MMI is the equal-weighted (1/1/1) average of three market-derived indicators calibrated to different speeds. Equal weights were selected by drawdown-optimization grid search — they deliver stronger Calmar ratios than the prior alpha-weighted (37/35/28) scheme and survive OOS validation better.

### Growth Impulses Index — ⅓ weight

**What it measures**: A composite of 10 components reflecting the rate of change of economic momentum (priced through markets):

- HYG — high-yield bond ETF / credit risk appetite
- HY credit spread (inverted) — credit stress
- XLY/XLP ratio — consumer discretionary vs staples
- XLI/XLU ratio — industrials vs utilities
- SPHB/SPLV ratio — high-beta vs low-volatility stocks
- Copper — global growth bellwether
- VIX (inverted) — equity volatility
- Yield curve (10Y minus 2Y) — recession/rate-cycle risk
- Weekly Economic Index (WEI) — high-frequency GDP proxy
- Baltic Dry Index proxy (BDRY) — global trade/shipping demand

Each component is converted to a 21-day rate of change, z-scored over 504 days, clipped to ±3 sigmas, and averaged. The dashboard drill-down explains each input and shows current z, 7d zΔ, 30d zΔ, and raw input history.

### Sector Breadth — ⅓ weight

**What it measures**: The z-score (over 90 days) of 7 cyclical sector ETFs. Provenance: `src/macro_framework/macro_pipeline.py` has used `LOOKBACK = 90` since commit `9f124cf` ("optimized for drawdown: was 63"); docs were reconciled to production on 2026-05-15 without changing math.

- SMH — semiconductors
- IWM — small caps
- IYT — transports
- IBB — biotech
- XHB — homebuilders
- KBE — banks
- XRT — retail

A healthy bull market has broad participation. When most cyclicals are above their historical average, demand is broad and the rally is sustainable. When only a few sectors lead while most lag, leadership is narrow.

### Financial Conditions — ⅓ weight

**What it measures**: Z-score (over 252 days) of three stress indicators, inverted so looser conditions are positive for MMI:

- VIX — equity volatility
- MOVE — bond-market volatility
- BAML High-Yield Spread — credit risk premium

Financial conditions are the weather in which assets trade. Tight conditions mean any negative news amplifies; loose conditions mean bad news is easier to absorb.

### Why these three together

The three indicators are calibrated to different speeds (21d / 90d / 252d) and capture different forces:

- **Growth Impulses** = economic momentum and risk appetite
- **Breadth** = market participation
- **FinCon** = financial stress

When all three agree, MMI is high-conviction. When they disagree, MMI is weaker and more ambiguous. The dashboard's mini-briefs make the attribution mechanical rather than interpretive: which input drove the latest move, which inputs currently support or drag, and what to watch next.

---

## The Economy Pillar — Macro Stress

Macro Stress is a 0–10 score derived from a clipped 0–1 stress intensity. It captures how deep we are inside the stagflation pocket.

### Real Economy Score

**What it measures**: Equal-weighted z-score (3-year window) of:

- **Real PCE YoY** — consumer growth (~70% of GDP)
- **Sahm Rule (inverted)** — labor stress; the rule fires when 3-month-MA unemployment rises >0.5pp from its 12-month low
- **Real Personal Income YoY** — household income trajectory in inflation-adjusted terms
- **Atlanta Fed GDPNow** — real-time nowcast of current-quarter GDP growth

Levels matter less than trend. A z-score over 3 years asks whether each measure is above or below its recent norm.

### Inflation Direction

**What it measures**: Δ Core CPI YoY over the last 6 months, in pp. Positive = inflation accelerating, negative = decelerating.

The framework is about *whether stress is building*, not whether inflation is high. Inflation can be high and falling, which is disinflationary and not stress-inducing. Inflation can be low and rising, which is reflationary and warrants attention. The 6-month change captures the trajectory the Fed and markets are responding to.

### Unified stress

```text
g = max(0, −Real_Economy)
i = max(0, Inflation_Direction)
Stress_raw       = 0.75 × g + 0.50 × i + 10 × g × i
Stress_intensity = clip(Stress_raw / 10.0083, 0, 1)
Stress_score     = 10 × Stress_intensity
```

Production locks: `buffer_size=0.5`, `threshold=0.75`, `stress_p99=10.0083`; macro release lags are PCE/RPI 60d, unemployment 35d, Core CPI 45d, GDPNow 0d.

The two `max(0, …)` clips mean each factor contributes only when adversely positioned: weak growth (RE < 0) and rising inflation (Inf_Dir > 0). The single-axis terms let stress build when either side worsens; the `g × i` term amplifies the true stagflation pocket when both are adverse.

---

## Why the Combination Makes Sense

The two pillars are deliberately complementary:

| | Market pillar (MMI) | Economy pillar (Macro Stress) |
|--|----------------------|-------------------------------|
| **Source** | Price / volatility data | Real-economy + inflation data |
| **Speed** | Fast (intraday → days) | Slow (weeks → months) |
| **Strength** | Catches turning points early | Grounded in fundamentals |
| **Weakness** | False alarms | Lags, noisy month-to-month |
| **Role in MRMI** | Headline signal | Buffer / confirmation |

Markets can flash false alarms — a single VIX spike, a credit-spread blow-out from a single name, a sector rotation that reverses in days. The economy can't fake it as easily: if real activity is weakening and core CPI is accelerating over six months, that's a real condition. Requiring both pillars to agree before flipping to CASH cuts whipsaw risk while preserving upside participation.

The historical evidence: backtested 2016–2026, the production framework (equal-weighted MMI + macro buffer + investor-grade three-state posture) reduces major drawdowns while preserving upside. The backtest card in the dashboard is the canonical current user-facing number set.

**Honest caveat — MMI standalone vs MRMI in calm windows.** Bare MMI can outperform MRMI when there are no real stress events, because the buffer keeps the framework invested through false alarms and pays a protection tax. That is intentional. The buffer is built for full cycles, not just calm periods.

---

## What the Framework Doesn't Do

- **Predict** — it reacts to current conditions. The signal lags economic releases by their natural cadence.
- **Pick assets** — it tells you risk-on / cautious / risk-off, not which assets to buy within a regime.
- **Do final portfolio construction** — LONG/CAUTION/CASH is the posture overlay; implementation is separate.
- **Provide short-term trading precision** — it is an allocation posture index, not an intraday trading signal.

---

## The AI Briefs (Three-Tier, Weekly Tuesday)

The framework includes three AI-generated briefs that translate the numbers into prose for the Tuesday research meeting:

1. **Market pillar brief** — what the markets are signaling this week, focused on Growth Impulses / Breadth / FinCon and their drivers.
2. **Economy pillar brief** — what the economy is signaling this week, focused on Macro Stress, Real Economy Score, and Inflation Direction trajectories.
3. **Top brief** — synthesis. Reads both pillar briefs and writes the cross-pillar story that goes in the hero.

Generation order is always pillar briefs first, then top brief. All three are generated via the `claude` CLI (Claude Code subscription), with prompts tuned for plain-English explanations that non-macro colleagues can use in a meeting.

Cadence is **lazy weekly Tuesday**: a brief is stale if its archive date is older than the most recent Tuesday on or before today. Past briefs are git-tracked under `briefs/YYYY-MM-DD/` and preserved forever — week-over-week evolution is auditable.

---

## Weekly Workflow

**Tuesday morning, before the macro-research meeting:**

1. Run `uv run python -m macro_framework.build` to refresh data, write the snapshot, and render the dashboard. Brief generation triggers automatically if any are stale.
2. Open `outputs/dashboard.html`. Skim the hero (number, state, exposure, this week's read).
3. Review Step 1 to see how MRMI has evolved and how close it is to the next threshold.
4. Read the market pillar brief and inspect any MMI driver mini-brief whose chart changed meaningfully.
5. Read the economy pillar brief and Macro Stress input chart.
6. Use the Reference Library for context/divergences, especially inflation and activity rows.
7. In the meeting: project the dashboard and walk through the four steps in order.

**Mid-week reviews**: skip brief regeneration unless forced. Refresh the data if you want updated charts.

**Annual review**: re-optimize MMI weights, reassess the buffer/threshold parameters, validate Real Economy Score components against any new data series, and decide whether any Reference Library indicator deserves promotion.

---

## Limitations

1. **Same-week execution required.** Briefs and signal cadence are weekly. Same-day execution within Tuesday's meeting is sufficient, but delays erode edge.
2. **No data before 2016 for the full production stack.** Cannot test the exact current framework through 2008 or dot-com.
3. **Three-state posture is still an overlay.** It gives 100% / 75% / 0% exposure, not detailed portfolio weights.
4. **Macro can be wrong.** Markets sometimes diverge from macro for extended periods. The framework will lag those.
5. **Reference Library is context, not signal.** Library charts explain narrative shifts and future candidates, but they do not change MRMI unless promoted through a separate research decision.

The framework is designed to win over many cycles with disciplined execution, not to be right every time.
