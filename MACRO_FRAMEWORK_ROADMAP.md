# Macro Framework — Roadmap

Forward-looking ideas for the macro framework project (`~/Projects/macro-framework/`). Current focus: the daily brief (V1: once/day at 18:00 ET, 5 sections, mechanical-first). Over time this doc will grow to cover other framework improvements — new indicators, backtest tooling, release calendar, etc.

Each section lists ideas roughly in priority order. Not every idea should ship — this is an inventory, not a plan.

Scope note: this roadmap covers the macro framework only. Other projects have their own docs and stay separate.

---

## V1 baseline (for reference)

- Regenerates once daily at 18:00 ET
- Card at top of `dashboard.html`
- Sections: headline, what moved, LLM context (2–3 sentences), on-watch (48h), freshness footer
- Saved to `.cache/daily_briefs/YYYY-MM-DD.md` for history

Everything below assumes V1 is in place.

---

## 1. Cadence & delivery

### Event-driven regeneration
Rebuild the brief whenever an input indicator refreshes, rather than at a fixed time. Best approximation of "always current." Cost: more complexity, more LLM calls, noisier history. Worth it if we find V1's single snapshot misses moves during the day.

### Pre-market + post-market briefs
Two daily runs: 06:30 ET (pre-market, for the overnight/Asia/Europe story) and 18:00 ET (post-close, for the US session). Cleaner than fully event-driven. Good for a morning reviewer.

### Push delivery
Email or Slack/iMessage the brief when it generates — or only when regime flips or an indicator crosses a threshold. Pulls the dashboard into the day instead of requiring an open tab. Low-effort, high-value once the brief quality is trusted.

### Weekly digest + monthly retro
- **Weekly (Sun 18:00 ET):** summarize the 7 briefs, flag multi-day arcs ("Breadth down 5 sessions running")
- **Monthly retro:** take the monthly report and the 30 daily briefs, grade the calls — which signals flipped, did the framework call the regime correctly

---

## 2. Narrative quality

### Multi-day arcs
V1 only sees today vs yesterday. V2 should spot streaks ("MRCI has declined 4 of last 5 days") and inflections ("Breadth flipped green→red today after 3w in green"). Rule-based, not LLM.

### Historical analogs
"MRMI at current level was last seen Oct 2023; following 60 days, SPX +7%, IWM +12%." Two flavors: (a) exact level match, (b) similar regime shape (e.g. "Cycle rising, Inflation falling, MRMI > 0.5"). Requires backtest corpus.

### Component attribution
When FinCon moves, say *why* mechanically: which of VIX / MOVE / HY contributed. Today's brief can say "FinCon +0.4, MOVE +0.3 drove it." Pure math, no LLM.

### Inflation-season transitions
Flag when the framework is close to crossing from one macro season (Spring/Summer/Fall/Winter) to another. High leverage for allocation decisions.

---

## 3. Confidence / completeness

This is the category most tightly tied to the original goal: "give me confidence I'm tracking everything."

### Pre-release watchlist
Each morning, list the day's scheduled releases, which indicator each one feeds, and what move would flip a signal. Example: "CPI Thu 08:30 — feeds inflation context. A +0.2% MoM surprise would push breakevens above neutral for first time since Feb."

### Threshold proximity
Scorecard shows signal state; brief should show *distance to next flip*. "Breadth 0.18 from neutral→red. 2 of 7 ETFs would need to roll over."

### Data sanity checks
Automated anomaly detection on input series — stale feeds, impossible prints, unit mismatches. When an indicator refreshes with a value >3σ from recent mean, flag for review before the brief publishes.

### Model self-check
Before publishing, verify every number claimed in the LLM narrative exists in the indicator data (simple string/regex check). If the LLM hallucinates a value, kill the narrative and fall back to mechanical-only.

### "Why we didn't publish" log
If any guard trips (stale data, failed LLM call, sanity check), log the reason and publish the mechanical sections anyway. Never silently fail — opaque failures erode confidence fast.

---

## 4. Actionable layer

### Portfolio implications
Given current MRMI / MRCI / Season, show allocation biases that apply. Not stock picks — regime overlays. "Spring + RISK-ON → long bias, cyclical tilt, duration neutral."

### Custom alert rules
User-defined triggers on top of the framework. "Ping me if MRMI drops >1σ in 1d" or "Alert if Cycle flips Contracting." Stored in a simple YAML, checked at brief generation.

---

## 5. Historical & review

### Searchable brief archive
`.cache/daily_briefs/` becomes a searchable corpus. Web UI or CLI to grep by ticker, regime, date range.

### Call tracking
Each brief's implicit calls (via regime state + season) get scored against realized returns over 5d / 20d / 60d. Running hit rate, shown at the top of the dashboard.

### "What changed since last review"
If the user hasn't opened the dashboard in N days, the brief shows a delta summary spanning the gap, not just the latest day.

---

## 6. UX / dashboard

### Delta-colored scorecard
The existing scorecard shows signal state. Add small 1d/7d change coloring (green/red background intensity by % change). Visually faster than reading the numbers.

### Brief mode vs Detail mode
Toggle to collapse the charts and show only the brief + scorecard. For quick morning reviews.

### Mobile view
The current dashboard is dense-desktop. A phone-friendly brief-only view (just the card, no charts) is low effort and high value for checking from anywhere.

### Share-as-image
Export the brief card as a PNG for publishing (e.g. Milk Road). One-click, templated. Adjacent to the newsletter business, not a personal-use feature.

---

## 7. Integration opportunities

### Truflation / on-chain inflation
Supplement official CPI/breakevens with real-time inflation indices. Surfaces inflection points 2–6 weeks before official data.

### FOMC / CPI release transcripts
On release days, pull the transcript + first 30m of reaction and feed into the LLM context section. Higher-quality narrative than macro moves alone.

### Milk Road Newsletter crossover
If specific brief patterns make for publishable takes, tag them. Closes the loop between personal framework and published content.

---

## 8. Production quality

### A/B narrative quality
Keep a sample of brief sections each week, human-grade them (1–5). Watch for drift — LLM outputs degrade subtly over time.

### Cost budget
LLM calls aren't free. Track cost/day, alert if it spikes (likely signal of a bug — retry loop, oversized context).

### Graceful degradation
Every non-mechanical section needs a fallback. API down → skip narrative. Data stale → mark as stale, don't hide. Never publish a brief that *looks* complete but silently dropped a failed component.

---

## Deferred / rejected for now

- **Real-time streaming brief (intraday ticker).** Over-engineered for a framework whose inputs mostly update once/day. Most indicators don't move on a 1h scale — streaming would be noise.
- **Mobile push notifications.** See "Push delivery" above, but native push (APNs) is too much infra. Email/Slack achieves 90% of it.
- **Chat interface on the dashboard.** Nice demo, but you already have this conversation thread for deeper questions. Not worth building a second surface.

---

## How to decide what to build next

After V1 ships, the prioritization question is: *what would most increase confidence that nothing is slipping through?* That points first to Section 3 (completeness/sanity checks), then Section 2 (narrative quality — especially multi-day arcs and component attribution), then Section 1 (cadence — only if V1's single daily snapshot is demonstrably insufficient).

Sections 4–6 are nice-to-have. Section 7 is speculative until V1+V2 are stable.
