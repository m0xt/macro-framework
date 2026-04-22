# Macro Framework — Complete Guide

## The Investment Thesis

Markets move because of two things: **fundamentals** (the actual economy and corporate earnings) and **liquidity/sentiment** (how much money is chasing how many assets, and how risk-tolerant people are). Most of the time, these reinforce each other. When they don't, you get the most interesting market moves.

This dashboard separates these forces into three layers:

1. **Regime layer** — fast-moving signals (volatility, credit spreads, sector breadth, growth momentum) that tell you whether the market is currently in a risk-on or risk-off mode. This is the trading decision.

2. **Cycle layer** — slow-moving fundamentals (real economy, monetary policy, labor) that tell you whether the macro backdrop is supportive or hostile. This is the context.

3. **Inflation context** — the price level dimension that's separate from cycle direction because it's interpretation-dependent (good or bad depending on level and regime).

The dashboard is designed for daily checks (60 seconds) and monthly deep dives. Same-day execution on regime changes is required to capture the alpha — the backtest shows a 1-day delay erases most of the edge.

---

## How To Read The Dashboard

### Top: The Regime Banner

The first thing you see. Big, bold, unambiguous.

- **RISK-ON (green)**: composite > 0. Stay invested in risk assets. Historical average return during green regimes: +25.7%/yr on SPX vs +11.6% buy-and-hold.
- **RISK-OFF (red)**: composite < 0. Move to cash or defensives. Historical max drawdown reduced from -18.9% to -2.9%.

The number next to the banner is the composite value. Magnitude matters:
- +0.1 = barely positive, low conviction
- +0.5 to +1.0 = solid positive
- +1.5+ = strong conviction

### Middle: Milk Road Momentum Index (MRMI) Chart

Visualizes the regime over time. Background colors show historical regimes. The white dashed line is the composite value. The yellow line is S&P 500 (toggle Russell and BTC if needed).

You should see that periods of red background often coincide with market declines, and green backgrounds with rallies. The signal isn't perfect but the historical edge is meaningful.

### Indicator Scorecard

Compact table showing every underlying indicator. For each row:
- **Value**: current z-score reading
- **7d / 30d**: percentage change over those windows with direction arrow
- **Signal**: green/red dot for regime indicators

Two groups:
- **MRMI Drivers** (Regime): GII, Sector Breadth, Financial Conditions
- **Macro Seasons**: Y-Axis — Growth (Real Economy + Labor); X-Axis — Inflation (Core CPI)

Click any row to expand the chart with description.

### Bottom: Macro Seasons

Two charts showing where the economy sits on the growth and inflation axes. The scatter chart positions the current reading across four quadrants (Spring / Summer / Fall / Winter). The time-series chart shows Growth composite and Core CPI YoY over time.

This is context only — not a trading decision input.

---

## The Regime Indicators (What Drives the Decision)

### Growth Impulses Index (GII) — Weight: 37%

**What it measures**: A composite of 10 components reflecting the rate of change of economic momentum:
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

**Economic interpretation**: When GII is rising and positive, the economy is in an acceleration phase — credit is flowing, cyclicals are bid, copper is up, vol is contained. This is the environment where risk assets perform best. When GII is falling and negative, the opposite is happening: credit tightening, defensive rotation, copper falling, vol spiking.

### Sector Breadth — Weight: 35%

**What it measures**: The z-score (over 63 days) of 7 cyclical sector ETFs:
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

**Economic interpretation**: This is the market's collective vote on whether the cycle is expanding. When XHB is rising, builders are seeing demand. When KBE is rising, banks are lending profitably. When IYT is rising, goods are moving. Their combined trend is a real-time poll of cyclical health.

### Financial Conditions — Weight: 28%

**What it measures**: Z-score (over 252 days) of three stress indicators:
- VIX — equity volatility (fear gauge)
- MOVE — bond market volatility
- BAML High-Yield Spread — credit risk premium

When these are elevated, financial markets are stressed. When they're compressed, markets are calm and risk-taking is rewarded.

**Why it works**: Financial conditions are the "weather" in which assets trade. Tight conditions (high VIX, wide spreads) mean any negative news amplifies. Loose conditions mean even bad news gets shrugged off. This is structural — it changes slowly over months, not days.

**Why slow (252-day lookback)**: Unlike GII and Breadth which are tactical, this captures structural stress regimes. The 2018 Q4 selloff, COVID 2020, 2022 bear market — all featured persistent multi-month elevated FinCon readings. The 252-day window catches these regimes without overreacting to single events.

**Why VIX + MOVE + HY (no IG)**: We tested adding IG (investment-grade) credit spreads. They didn't add signal — too correlated with HY but with less noise reduction. The three retained capture equity vol, bond vol, and credit risk — three independent dimensions of market stress.

**Economic interpretation**: When this is below zero (loose conditions), the financial plumbing is healthy. Capital flows freely, hedging is cheap, risk premia are compressed. When it's above zero (tight conditions), the opposite — investors are paying up for protection, credit is harder, risk premia are elevated.

### Why these three together?

The three indicators are calibrated to different speeds (21d / 63d / 252d) and capture different forces:
- **GII** = economic momentum (real economy + market signals)
- **Breadth** = market participation
- **FinCon** = financial stress

When all three agree, you have high-conviction signals. When they disagree, the composite gets weaker — signaling uncertainty. The diversification across timescales means at least one indicator typically catches a regime change while the others confirm.

The weights (37/35/28) come from each indicator's historical out-of-sample alpha on SPX. GII works across all assets. Breadth is strongest standalone. FinCon adds structural stability but is SPX-focused.

---

## The Macro Seasons Inputs (Growth Axis — Y)

### Real Economy

**Components**: CFNAI (Chicago Fed National Activity Index) + Industrial Production + Housing Starts + Building Permits.

**Why these**:
- **CFNAI** is a weighted composite of 85 monthly economic indicators (production, employment, sales, consumption). It's effectively a "super-PMI." When CFNAI is below -0.7, the economy is likely in or entering recession.
- **Industrial Production** measures the physical output of factories, mines, utilities. It's the most direct measure of "real" economic activity.
- **Housing Starts** are the leading indicator of construction activity. Housing is the most rate-sensitive sector and turns 6-12 months before the broader economy.
- **Building Permits** lead housing starts by a few months — they're an even earlier signal.

We z-score year-over-year growth (not levels) so trends matter, not absolute size.

**Economic interpretation**: This is the answer to "is the actual economy growing or shrinking?" When all four are positive, real activity is expanding. When housing rolls over (often the first signal), it's an early warning that the broader economy may follow.

### Labor

**Components**: Initial jobless claims + continuing claims (both inverted, so positive z-score = strong labor market).

**Why jobless claims**: This is the most reliable leading recession indicator in the US. Initial claims rise 3-6 months before recessions begin. Weekly data, no revisions, hard to manipulate. Continuing claims confirm whether layoffs are temporary or persistent.

**Why labor is in cycle, not Fed Watch**: Labor data IS economic data — it tells you whether companies are hiring or firing, which directly reflects economic activity. The Fed cares about it because of their dual mandate, but functionally it's a growth/cycle indicator.

**Economic interpretation**: When claims are below average (positive z-score), companies are hiring, the economy is healthy. When claims start rising even modestly, it's an early warning. Recessions are essentially defined by widespread job losses.

---

## The Macro Seasons Input (Inflation Axis — X)

### Inflation (Core CPI)

**What it measures**: Core CPI year-over-year % change (excludes food & energy), expressed as the deviation from the Fed's 2% target. This is the X-axis driver for the Macro Seasons chart.

**Why Core CPI, not breakevens**: Breakevens reflect forward market expectations and are interpretation-dependent depending on level and cycle phase — not useful as a mechanical axis input. Core CPI is the realized inflation the Fed actually responds to.

**Why it's separate from cycle**: Inflation is interpretation-dependent. High inflation can signal strong demand (good) or Fed tightening ahead (bad). The right interpretation depends on context. Adding it to a growth composite that mechanically averages would lose this nuance.

**Economic interpretation**: Combined with the growth reading, Core CPI tells you which macro season you're in — Spring (growth up, below target), Summer (growth up, above target), Fall (growth down, above target), Winter (growth down, below target).

---

## Why This Framework Makes Sense As A Whole

### The hierarchy mirrors how decisions actually get made

Portfolio managers don't ask "is GII at +0.7 with FinCon at -0.3?" They ask three questions:

1. **Should I be invested?** (Yes/No) — answered by the MRMI
2. **What's the macro backdrop?** (Supportive/Hostile) — answered by the business cycle
3. **What kind of regime is this?** (Spring/Summer/Fall/Winter) — answered by combining cycle + inflation

The dashboard is structured to answer exactly these three questions in order.

### Different speeds capture different forces

A common failure of macro frameworks is using indicators at the same speed. They become correlated and you lose diversification. We deliberately mixed:
- **Fast** (21d ROC): GII catches momentum shifts
- **Medium** (63d): Sector Breadth reflects rotation
- **Slow** (252d): FinCon captures structural stress
- **Slow** (252d, monthly data): Cycle indicators reflect fundamentals

This means when one indicator is noisy, others are stable. False signals from one rarely propagate through all.

### We test what we include

Every indicator in the framework was backtested. Things we tested and rejected:
- IG credit spread (no signal improvement over HY)
- SLX steel ETF (too noisy, hurt breadth signal)
- Baltic Dry Index as a standalone (negative alpha out-of-sample)
- GII "both fast and slow positive" mode (too restrictive, only green 5% of time)
- Combining business cycle with MRMI (cuts alpha by 60-75%)

This means everything that's IN the framework earned its place by improving signal quality.

### The framework is honest about what it doesn't do

- It doesn't predict — it reacts to current conditions.
- It doesn't tell you which assets to buy within a regime — it tells you risk-on or risk-off.
- It doesn't size positions — that's a separate decision.
- It doesn't work without same-day execution — short regimes (~17 days) require fast action.

These limitations are documented and the backtest accounts for them.

### The framework is robust, not optimized

Walk-forward testing (rolling 1-year out-of-sample windows) shows positive SPX alpha every year from 2021-2026. Equal weights perform within 0.6% of the optimized weights. This means the result isn't a fluke of one specific parameter set — the underlying signal is real.

### What it doesn't replace

This framework helps with the **timing** decision (when to be invested). It doesn't replace:
- **Stock/asset selection** (what to buy within risk-on)
- **Position sizing** (how much to bet)
- **Risk management** (stops, hedges)
- **Investment thesis** (long-term views)

It's one input — arguably the most important macro input — but only one input.

---

## Daily and Monthly Workflow

### Daily routine (60 seconds)

1. Open dashboard. Read the banner.
2. If regime is unchanged from yesterday → done.
3. If regime changed → act today (same-day execution matters).
4. Scan the scorecard for any indicators changing direction. 7d arrows that diverge from 30d trends signal turning points.
5. Note the cycle backdrop and inflation direction for context.

### Monthly review (10-15 minutes)

1. Look at the 1-year time range on the composite chart. What were the major regime shifts?
2. Review each scorecard category. Which indicators are trending up/down?
3. Identify the macro quadrant: cycle direction × inflation direction.
4. Use this for monthly reports: "We're in [cycle phase], with [inflation regime], MRMI is [green/red] driven primarily by [strongest indicator]."

### When to re-optimize

Parameters were last optimized April 2026 on 2016-2026 data. Consider re-optimizing annually or after a major regime change that the framework failed to capture. Robustness tests show low sensitivity to exact parameters, so minor drift is unlikely to break it.

---

## Limitations (Important)

1. **Same-day execution required.** A 1-day delay erases most of the edge (tested).
2. **Whipsaw risk.** ~15 regime flips per year, some are false signals lasting only a few days.
3. **Backtest is 2016-2026.** No data before that. Cannot test against 2008 or dot-com crash.
4. **Binary signal.** Tells you in/out, not how much. Doesn't size positions.
5. **Not asset selection.** Risk-on/off across all assets, not within-asset rotation.
6. **Macro can be wrong.** Markets sometimes diverge from macro for extended periods (e.g., AI-driven rally during tightening cycle 2023-2024).

The framework is designed to win over many cycles with disciplined execution, not to be right every time.
