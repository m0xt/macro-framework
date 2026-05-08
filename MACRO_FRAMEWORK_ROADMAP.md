# Macro Framework — Roadmap

Forward-looking ideas for the macro framework project (`~/Desktop/macro-framework/`). Current state: three-tier weekly briefs (top + market pillar + economy pillar), generated each Tuesday via the `claude` CLI subscription, archived under `briefs/YYYY-MM-DD/`. Over time this doc will grow to cover other framework improvements — new indicators, backtest tooling, release calendar, etc.

Each section lists ideas roughly in priority order. Not every idea should ship — this is an inventory, not a plan.

Scope note: this roadmap covers the macro framework only. Other projects have their own docs and stay separate.

---

## Current baseline (for reference)

- Three weekly briefs in a tiered hierarchy: market → economy → top (synthesis)
- Lazy Tuesday cadence — regenerates if the latest archive is older than the most recent Tuesday on or before today
- Generated via the `claude` CLI (Claude Code subscription), WebSearch enabled
- Saved to `briefs/YYYY-MM-DD/{top,market,economy}.md` and git-tracked
- Top brief sits in the dashboard hero; pillar briefs sit between each pillar's chart and its drivers

Everything below assumes this baseline is in place.

---

## 1. Cadence & delivery

### Twice-weekly cadence
A second mid-week run (e.g. Friday) for situations where Tuesday's read is materially out of date by week's end. Cleaner than fully event-driven. Cost is minor — three more brief calls per week.

### Event-driven regeneration
Rebuild the briefs whenever an input indicator refreshes, rather than weekly. Best approximation of "always current." Cost: more complexity, more LLM calls, noisier history. Worth it if we find weekly briefs miss intra-week regime changes.

### Push delivery
Email or Slack/iMessage the top brief when it generates — or only when the regime flips or stress crosses a threshold. Pulls the dashboard into the day instead of requiring an open tab. Low-effort once brief quality is trusted.

### Monthly retro
Take the four weekly briefs and the daily snapshots, grade the calls — which signals flipped, did the framework call the regime correctly, did the briefs flag what mattered.

---

## 2. Narrative quality

### Multi-week arcs
The top brief currently sees this week's pillar briefs in isolation. V2 should also see the prior week's archived top brief and flag continuity / change ("two consecutive weeks of MMI deterioration without macro confirmation"). Cheap — just include the prior brief in the prompt.

### Historical analogs
"MRMI at current level was last seen Oct 2023; following 60 days, SPX +7%, IWM +12%." Two flavors: (a) exact level match, (b) similar regime shape (e.g. "MMI > 0.5, Stress 0, breakeven path falling"). Requires backtest corpus.

### Component attribution
When MMI moves week-over-week, mechanically attribute the move to GII / Breadth / FinCon. The brief can say "MMI +0.4 driven by FinCon +0.3 (MOVE collapse)." Pure math, no LLM.

### Stress-pocket proximity
Flag when the framework is approaching the stagflation pocket even if stress hasn't fired. "Real Economy at +0.3 but trending down; Inflation Direction at +0.2 and rising — stress fires if RE crosses zero." High leverage for early warning.

---

## 3. Confidence / completeness

This is the category most tightly tied to the original goal: "give me confidence I'm tracking everything."

### Pre-release watchlist
Each Tuesday, list the week's scheduled releases, which indicator each one feeds, and what move would flip a signal. Example: "CPI Wed 08:30 — feeds Inflation Direction. A +0.3pp surprise would push the 6m delta above zero for the first time since Feb."

### Threshold proximity
Scorecard shows signal state; brief should show *distance to next flip*. "MMI at +0.18, would need −0.5 to flip CASH absent a stress event. With current macro buffer eroded to 0.6, MMI only needs −0.1."

### Data sanity checks
Automated anomaly detection on input series — stale feeds, impossible prints, unit mismatches. When an indicator refreshes with a value >3σ from recent mean, flag for review before the brief publishes.

### Model self-check
Before publishing, verify every number claimed in the brief exists in the indicator data (simple regex check). If the LLM hallucinates a value, kill the narrative and fall back to mechanical-only.

### "Why we didn't publish" log
If any guard trips (stale data, failed CLI call, sanity check), log the reason and surface it in the dashboard. Never silently fail — opaque failures erode confidence fast.

---

## 4. Actionable layer

### Portfolio implications
Given current MRMI / MMI / Stress-intensity, show allocation biases that apply. Not stock picks — regime overlays. "MRMI strong + MMI rising + Stress 0 → cyclical tilt, duration neutral, EM tilt."

### Custom alert rules
User-defined triggers on top of the framework. "Ping me if MRMI drops >0.3 in 1d" or "Alert if Stress crosses 0.3." Stored in a simple YAML, checked at brief generation.

---

## 5. Historical & review

### Searchable brief archive
`briefs/` is already a corpus. Add a small CLI / dashboard view to grep by ticker, regime, date range. The git history already gives us week-over-week diffs for free.

### Call tracking
Each brief's implicit calls (via regime state) get scored against realized returns over 5d / 20d / 60d. Running hit rate, shown at the top of the dashboard.

### "What changed since last review"
If the user hasn't opened the dashboard in N weeks, the brief shows a delta summary spanning the gap, not just the latest week.

---

## 6. UX / dashboard

### Delta-colored scorecard
The existing scorecard shows signal state. Add small 1d/7d change coloring (green/red background intensity by % change). Visually faster than reading the numbers.

### Brief mode vs Detail mode
Toggle to collapse the charts and show only the briefs + scorecards. For quick morning reviews.

### Mobile view
The current dashboard is dense-desktop. A phone-friendly brief-only view (just the three briefs, no charts) is low effort and high value for checking from anywhere.

### Share-as-image
Export the top brief as a PNG for publishing (e.g. Milk Road newsletter). One-click, templated. Adjacent to the newsletter business, not a personal-use feature.

---

## 7. Integration opportunities

### Truflation / on-chain inflation
Supplement official CPI with real-time inflation indices in the Inflation Direction calculation. Surfaces inflection points 2–6 weeks before official data.

### FOMC / CPI release transcripts
On release days, pull the transcript + first 30m of reaction and feed into the brief context. Higher-quality narrative than macro moves alone.

### Milk Road Newsletter crossover
If specific brief patterns make for publishable takes, tag them. Closes the loop between personal framework and published content.

---

## 8. Production quality

### A/B narrative quality
Keep a sample of brief sections each week, human-grade them (1–5). Watch for drift — LLM outputs degrade subtly over time, especially when the underlying model is updated.

### Cost / quota tracking
Subscription calls aren't free in budget terms even if not metered per-token. Track briefs generated per week, alert if it spikes (likely signal of a bug — repeated retries, force-flag stuck on).

### Graceful degradation
Every non-mechanical section needs a fallback. CLI down → skip brief, show stale archive with explicit "(cached, last refreshed YYYY-MM-DD)" note. Never publish a brief that *looks* current but is silently stale.

---

## Deferred / rejected for now

- **Real-time streaming brief (intraday ticker).** Over-engineered for a framework whose inputs mostly update once per day-or-week. Most indicators don't move on a 1h scale — streaming would be noise.
- **Mobile push notifications.** See "Push delivery" above, but native push (APNs) is too much infra. Email/Slack achieves 90% of it.
- **Chat interface on the dashboard.** Nice demo, but the conversation thread for deeper questions already exists. Not worth building a second surface.

---

## How to decide what to build next

The prioritization question is: *what would most increase confidence that nothing is slipping through?* That points first to Section 3 (completeness/sanity checks), then Section 2 (narrative quality — especially multi-week arcs and stress-pocket proximity), then Section 1 (cadence — only if the weekly snapshot is demonstrably insufficient).

Sections 4–6 are nice-to-have. Section 7 is speculative until 1–3 are stable.
