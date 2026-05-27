# Engineer progress — macro-framework

Append a structured entry at the bottom on every dispatch. Format:

```
## <UTC timestamp> — <short title>
- What: <1-2 line summary>
- Files touched: <list>
- Commit: <SHA or "none">
- Status: completed | partial | blocked
- Open thread for next dispatch: <if any, else "none">
```

Keep entries terse — this file is read by every stateless dispatch.

## 2026-05-18T08:29:14Z — LAN dashboard serve
- What: Added launchd-backed static HTTP serve for outputs/dashboard.html on 0.0.0.0:8001 and documented the LAN URL.
- Files touched: AGENTS.md; scripts/com.milkroad.macro-framework-serve.plist; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Bob 13b webloc delivery after serve verification

## 2026-05-19T11:04:07Z — Macro stress display simplification
- What: Collapsed the economy pillar macro-stress display to an OFF/BUILDING/ELEVATED badge with plain-English growth and inflation axis labels; rebuilt dashboard from cached data.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-19.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-19T11:24:23Z — Macro stress value + trend chart
- What: Restored the current macro-stress 0–1 intensity beside the OFF/BUILDING/ELEVATED badge and added a 90-day stress-intensity line chart with BUILDING/ELEVATED thresholds from snapshots.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-19.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-19T11:39:54Z — Macro stress chart polish
- What: Rewired macro-stress intensity to the shared timeframe selector, matched the small-chart styling to the dashboard pattern, and added a separate Stress inputs chart for Real Economy Score + Inflation Direction Δ6m.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-19.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-19T11:52:40Z — Economy pillar visual parity
- What: Removed redundant Growth/Inflation text rows and restructured Macro Stress into the same chart-card + drivers-panel pattern as the market pillar, with OFF/BUILDING/ELEVATED chip plus 0–1 intensity retained.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-19.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-20T08:12:29Z — Full backtest rerun comparison
- What: Refreshed inputs with no-cache build, ran canonical production backtest, and wrote a dated report comparing fresh results to dashboard and presentation figures; dashboard backtest card is stale while presentation OOS headline matches within rounding/current-data drift.
- Files touched: reports/backtest-2026-05-20.txt; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin decision on whether/how to update dashboard backtest card

## 2026-05-20T08:26:51Z — Backtest canonical gate divergence
- What: Verified production_mrmi against the live build-path MRMI on fresh inputs; latest and overlapping values match, but production_mrmi starts 317 rows earlier because it fills missing macro stress to 0.0 while the build path leaves MRMI NaN until release-lagged macro context exists. Stopped before dashboard/presentation propagation per hard gate.
- Files touched: reports/backtest-2026-05-20-canonical-check.md; .engineer/progress.md
- Commit: pending (this commit)
- Status: blocked
- Open thread for next dispatch: Martin decision on whether early missing macro stress should be treated as OFF or excluded to match live build-path semantics.

## 2026-05-20T08:37:11Z — Backtest aligned to live MRMI semantics
- What: Replaced backtest inline MRMI stress math with the live calc_milk_road_macro_index path, verified exact live/backtest series equality, reran aligned canonical backtest, and propagated aligned numbers into the presentation and dashboard card.
- Files touched: src/macro_framework/backtest_production.py; reports/backtest-2026-05-20-aligned.txt; docs/PRESENTATION.html; src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-20.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-20T11:15:39Z — Onchain pulse Phase A bootstrap
- What: Bootstrapped fresh local `~/Projects/onchain-pulse-index/` repo with PROJECT_SKELETON docs/config, salvaged the prototype data-fetch layer into `src/onchain_pulse_index/data.py`, relocated BMP_API_KEY runtime file to ops secrets, and verified fresh fetch/test gates.
- Files touched: ~/Projects/onchain-pulse-index/*; ~/ops/secrets/onchain-pulse-index/.env; .engineer/progress.md
- Commit: onchain-pulse-index 758686c; macro progress commit pending
- Status: partial
- Open thread for next dispatch: ops git-crypt setup is blocked by current `~/ops/.gitignore` (`secrets/**`) and missing git-crypt command/config; plaintext secret was not force-added.

## 2026-05-23T00:44:45Z — Continuous macro stress score
- What: Added continuous 0-10 stress_score alongside unchanged 0-1 stress_intensity, wired snapshot/chart/Supabase row builders and dashboard stress panel; calibrated k1=1.03, k2=0.005 on cached full backfill history (3186 rows): Calm 50.3%, Watch 17.0%, Building 28.1%, Elevated 4.7%; today stress_score=7.9831 (Building), stress_intensity=0.0303.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; src/macro_framework/sync_to_supabase.py; migrations/0003_macro_stress_score.sql; tests/test_smoke.py; tests/test_sync_to_supabase.py; outputs/dashboard.html; snapshots/2026-05-23.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: partial
- Open thread for next dispatch: Apply migrations/0003_macro_stress_score.sql in Supabase SQL editor, then run doctor + full backfill; current doctor fails because remote macro_snapshots.stress_score column does not exist.

## 2026-05-23T07:01:46Z — Stress score calibration infeasible under fixed formula
- What: Ran binding k1/k2 optimization over the full cached backfill daily history (3186 rows, 2017-09-02..2026-05-23): coarse log grid 30×30 plus dense linear/log/focused grids within k1 ∈ [0.5, 5.0], k2 ∈ [0.005, 0.5]. Best remains k1=1.03, k2=0.005 with Calm 50.3%, Watch 17.0%, Building 28.1%, Elevated 4.7%; no grid point hit ±2pp, so constants/dashboard were left unchanged. Today: stress_score=7.9831, growth_pressure=6.6397, inflation_pressure=9.9982, bucket=building; legacy stress_intensity=0.0303.
- Files touched: .engineer/progress.md
- Commit: pending (this commit)
- Status: blocked
- Open thread for next dispatch: Formula structure cannot hit the 60/20/15/5 bucket target with fixed 0.6/0.4 weighting and 0-4/4-6/6-8/8-10 boundaries; Bob/Martin should decide whether to relax weighting, bucket boundaries, or k2 lower bound.

## 2026-05-23T07:07:38Z — Percentile-pegged stress buckets
- What: Locked stress score bucket cutoffs to historical percentiles: Calm/Watch 5.55, Watch/Building 6.95, Building/Elevated 7.97; achieved distribution Calm 59.95%, Watch 20.03%, Building 15.10%, Elevated 4.93% over 3186 cached daily rows. Today stress_score=7.9831 → elevated. Bucket boundaries are now percentile-pegged against historical distribution; will not auto-update as new data arrives. Re-fit annually.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-23.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Supabase backfill still blocked on manual migrations/0003_macro_stress_score.sql apply; no schema change needed for this bucket cutoff update.

## 2026-05-23T19:25:55Z — Smooth stress sigmoid retune
- What: Re-tuned stress-score sigmoid constants for smoothness from full release-lagged backfill std(): k1=0.97 (RE_score std=0.9736), k2=0.89 (inflation_dir_pp std=0.8944). Re-derived percentile cutoffs 5.33 / 6.01 / 6.77; achieved Calm 59.95%, Watch 20.21%, Building 14.75%, Elevated 5.08% over 3186 rows.
- What: Smoothness check: 2026-05-15 inflation_pressure=4.7252, stress_score=6.0414, bucket=building; 2026-05-16 inflation_pressure=5.1214, stress_score=6.1857, bucket=building; inflation_pressure delta=0.3962 (<2.0). Today 2026-05-23: stress_score=6.0884, growth_pressure=6.7331, inflation_pressure=5.1214, bucket=building, legacy stress_intensity=0.0303.
- Files touched: src/macro_framework/macro_pipeline.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-23.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-23T20:42:19Z — Percentile-rank stress headline
- What: Rank-transformed headline stress_score from raw sigmoid weighted sum via locked 101-point ECDF table; cutoffs are now fixed percentile ranks 6.0/8.0/9.5 while sub-pressures remain raw. CDF checksum sha256=95d24412b04e41e5961f63bc32558f416f37b54bf28faef8213d366507cb4a94; anchors p0=2.254996, p25=4.323916, p50=5.125875, p75=5.798006, p95=6.771069, p100=8.044328. Today raw_score=6.088398 → stress_score=8.183153 (81.83rd percentile), bucket=building; percentile assertion passed.
- What: Verified history span/distribution/smoothness on 3186 cached release-lagged rows: score min=0.0 max=10.0; buckets calm=1911 (59.98%), watch=637 (19.99%), building=478 (15.00%), elevated=160 (5.02%); May 15 stress_score=8.063170 vs May 16=8.424226, delta=0.361055 (<2.0).
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-23.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Bob should rerun Supabase backfill so historical stress_score values update to the rank-transformed scale; no schema change.

## 2026-05-25T08:08:02Z — OR+AND stress backtest spike
- What: Added an experimental non-production MRMI helper for Martin's OR+AND stress formula and wrote the task-34 comparison report. Requested grid best was α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75; avg Calmar improved 1.522 → 2.551, with cash time rising 21.3% → 48.4% and switches 104 → 210. Recommendation: ship the new formula if Martin accepts the more defensive/higher-turnover profile; consider a narrow buffer/threshold follow-up before Phase 2.
- Files touched: src/macro_framework/macro_pipeline.py; reports/task-34-stress-unification-backtest.md; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin/Bob review of Phase 1 report; Phase 2 remains blocked until sign-off, with possible narrow buffer/threshold search suggested by sensitivity.

## 2026-05-25T08:24:53Z — Task 34 narrow buffer/threshold grid
- What: Ran the requested 35-combo buffer_size × threshold refinement with α=0.75, β=0.5, λ=10 locked. New best is buffer_size=0.3, threshold=0.75: avg Calmar 4.027, avg cash 60.88%, avg switches 215; SPX/IWM/BTC Calmar 6.88/4.53/0.67.
- Files touched: reports/task-34-stress-unification-backtest.md; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin/Bob sign-off on whether to ship the more defensive buffer_size=0.3 / threshold=0.75 profile; Phase 2 implementation remains separate.

## 2026-05-25T08:38:37Z — Task 34 cash-time Pareto frontier
- What: Re-ran the original 2400-combo Phase 1 unified-stress grid, saved all rows, and appended a cash-time vs Calmar Pareto frontier with six representative caps. Closest thesis-preserving stay-long upgrade is ≤30% cash (α=0.5, β=0.75, λ=10, buffer=0.5, threshold=0.25): avg Calmar 1.746, cash 28.07%, switches 130; Phase 1 best remains avg Calmar 2.551 at 48.43% cash.
- Files touched: reports/task-34-stress-unification-backtest.md; reports/task-34-phase1-grid-all-rows.csv; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin/Bob decision on whether to prefer stay-long ≤30% cash, intermediate defensive ≤40/45%, Phase 1 best ≤50%, or the prior narrow-grid >50% defensive profile.

## 2026-05-25T08:59:30Z — Task 34 OOS validation
- What: Ran canonical 70/30 IS/OOS validation, IS-only 2400-combo re-optimization, and walk-forward annual-return sanity for Phase 1 best. OOS Calmar for Phase 1 best: SPX 8.22, IWM 4.57, BTC 2.03 vs production 5.38/3.76/0.73; IS-only optimum changed only α to 1.0 and had near-identical OOS metrics, so report recommends Phase 2 ready subject to cash-time sign-off.
- Files touched: reports/task-34-stress-unification-backtest.md; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin/Bob sign-off on Phase 2 implementation despite roughly half-time cash exposure and higher switches.

## 2026-05-25T09:16:21Z — Task 34 preview dashboard
- What: Rendered `outputs/dashboard-preview.html` as a read-only Phase 1 preview using `calc_milk_road_macro_index_unified_stress` with α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75 and full-history stress p99=10.0083. Stress display uses round buckets (Calm 0–3, Watch 3–5, Building 5–7, Elevated 7–10) for visual cleanliness rather than percentile buckets; today's preview reading is MRMI +0.13 → LONG and stress 0.8 → calm.
- What: Preview rendered the unified-stress MRMI headline/history strip, normalized `stress_raw` chart, raw `growth_weakness` + `inflation_pressure` inputs panel, 7-day stress momentum chip (`→ steady`), and preview-only Phase 1/IS-OOS backtest card; production `outputs/dashboard.html`, snapshots, presentation, Supabase sync, and production MRMI math were left unchanged.
- Files touched: src/macro_framework/build.py; scripts/build_preview.py; outputs/dashboard-preview.html; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin review of `outputs/dashboard-preview.html` shape before deciding whether to ship Phase 2.

## 2026-05-25T10:23:48Z — Task 34 unified stress production ship
- What: Promoted Martin's unified-stress formula to production MRMI end-to-end with locked α=0.75, β=0.50, λ=10, buffer_size=0.5, threshold=0.75, stress_p99=10.0083; retired the task-33 rank/sigmoid visualization layer, updated Supabase value semantics, rebuilt dashboard/snapshots, and deleted the preview-only build artifacts. Today's reading after cached build: MRMI +0.13 → LONG, stress_score 0.83 → calm.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; src/macro_framework/sync_to_supabase.py; src/macro_framework/backtest_production.py; src/macro_framework/weekly_briefs.py; tests/test_smoke.py; tests/test_sync_to_supabase.py; README.md; GUIDE.md; docs/architecture.md; docs/PRESENTATION.html; outputs/dashboard.html; snapshots/2026-05-23.json; snapshots/2026-05-25.json; outputs/dashboard-preview.html; scripts/build_preview.py; .engineer/progress.md
- Commit: 4519bc0
- Status: completed
- Open thread for next dispatch: Bob should run `uv run python -m macro_framework.sync_to_supabase backfill` after pulling this commit; no SQL migration was added.

## 2026-05-26T08:14:38Z — Task 35a investor-grade threshold backtests
- What: Backtested current unified-stress MRMI interpretation alternatives across binary lower cash cuts, symmetric caution bands, and asymmetric investor-friendly caution zones; recommended asymmetric -0.50/+0.25 with 75% caution as the product-default candidate because it cuts full-cash time from 48.4% to 27.9% while keeping the formula unchanged.
- Files touched: reports/task-35-investor-grade-thresholds.md; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin/DGal decision on whether to implement the recommended asymmetric caution interpretation in production dashboard/snapshot/Supabase semantics.

## 2026-05-26T09:00:33Z — Task 35b investor-grade caution posture
- What: Finished the asymmetric investor-grade MRMI posture implementation without changing the unified-stress formula: MRMI < -0.50 = CASH/0%, -0.50..+0.25 = CAUTION/75%, > +0.25 = LONG/100%; updated dashboard scale/hero/chart framing, snapshot JSON fields, backtest exposure semantics, Supabase backward-compatible state handling, weekly brief context, docs, and tests. Verified 2026-05-25 MRMI +0.1343 now maps to CAUTION/75% in snapshot JSON; cached 2026-05-26 dashboard/snapshot reads MRMI +0.0738 → CAUTION/75%.
- Gates: `uv run ruff check .` passed; `uv run pytest` passed (41 passed, 4 xfailed); `uv run python -m macro_framework.build` passed from cache and wrote outputs/dashboard.html + snapshots/2026-05-26.json; `uv run python -m macro_framework.backtest_production` passed from cache (full-sample SPX/IWM/BTC Calmar 2.88/2.57/0.67, avg exposure 62.9%).
- Files touched: DECISIONS.md; README.md; GUIDE.md; docs/PRESENTATION.html; docs/architecture.md; src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; src/macro_framework/backtest_production.py; src/macro_framework/sync_to_supabase.py; src/macro_framework/weekly_briefs.py; tests/test_smoke.py; tests/test_sync_to_supabase.py; outputs/dashboard.html; snapshots/2026-05-25.json; snapshots/2026-05-26.json; briefs/2026-05-26/*; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Supabase `mrmi_state` hot column remains backward-compatible LONG/CASH (`CAUTION` maps to `LONG`) because no migration was necessary or added; three-state posture/exposure lives in snapshot JSON until Martin approves a native schema change.

## 2026-05-26T09:37:26Z — Growth Impulses drill-down prototype
- What: Added the Growth Impulses research drill-down under the existing MMI drivers panel: collapsed by default, full 10-input evidence stack grouped by credit/risk appetite, growth/commodities, and vol/rates, with current readings, 21d/126d changes, z contributions, and a deterministic 3-sentence mini-brief. The pattern is compact enough to replicate for Sector Breadth and Financial Conditions, but those should be added one at a time after Martin/Bob review the Growth UX.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: 627503b
- Status: completed
- Open thread for next dispatch: Review Growth Impulses drill-down UX before copying the pattern to Sector Breadth and Financial Conditions.

## 2026-05-26T11:55:00Z — Task 37a Growth Impulses drill-down UX polish
- What: Polished Growth Impulses drill-down per Martin's review. Sorted rows by |contribution_7d| (proxy = per-input 7d fast-z change divided by the 10 growth-impulse components). Simplified columns to Input / Group / 7d zΔ / 30d zΔ / Current z (dropped the raw absolute-value columns and redundant direction chip). Added a per-input raw-history chart inside the drilldown body with a `<select>` dropdown, lazy-build on first `<details>` open, click-to-select on table rows, and rebuild on range-tab switch. Mini-brief now names the top 7-day mover plus the leading supporter/drag. Snapshot stays lean: `growth_impulse_drilldown` continues to live in JSON but `values` arrays are only emitted into the chart payload via `include_values=True`.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Gates: `git diff --check` clean; `uv run ruff check .` passed; `uv run pytest -q` passed (42 passed, 4 xfailed); `uv run python -m macro_framework.build --use-cache` rebuilt outputs/dashboard.html + snapshots/2026-05-26.json from cache.
- UX summary: drilldown summary now reads "sorted by 7-day contribution"; intro paragraph carries an inline sort-note; the chart panel sits below the table with a labelled select, title row, 180px canvas, and a sub-line showing source + current z + 7d zΔ. Today's snapshot ranks WEI / SPHB/SPLV / BDRY first by |contribution|, brief reads "WEI is lifting the latest 7-day GII move; current support is led by WEI, while HYG is the biggest drag."
- Pattern readiness: Growth Impulses drilldown is now the reference pattern. Sector Breadth and Financial Conditions can follow once Martin signs off on this iteration; the helper API is `<pillar>_drilldown(data, comp, include_values=...)` returning `{intro, sort_note, score, supportive_count, drag_count, rows, brief}` with `values` reserved for chart payloads only.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Martin to review the Growth Impulses UX iteration before replicating the drill-down pattern to Sector Breadth and Financial Conditions.

## 2026-05-26T10:53:22Z — Task 38a Growth Impulses input tooltips
- What: Added compact keyboard-focusable info icons beside each Growth Impulses input name, backed by concise per-input explanations in the drill-down payload; rebuilt dashboard/snapshot from cached data.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-26T10:58:24Z — Task 39a Growth Impulses tooltip fix
- What: Replaced native `title`-only Growth Impulses input hints with a custom CSS tooltip driven by `data-tooltip`, visible on hover and keyboard focus; icons remain compact `i` badges and row click-to-select skips icon clicks. Rebuilt dashboard/snapshot from cached data and confirmed HYG, HY spread inverted, WEI, and Yield curve explanations are present in outputs/dashboard.html.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-26T11:08:50Z — Task 40 MMI driver drill-downs
- What: Replicated the approved Growth Impulses drill-down pattern for Sector Breadth and Financial Conditions: compact contribution-sorted z-score tables, custom input tooltips, raw input history charts with select/click-row UX, deterministic mini-briefs, and backward-compatible lean snapshot payloads.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-26T11:18:50Z — Task 41a MMI drill-down placement
- What: Moved the Growth Impulses, Sector Breadth, and Financial Conditions input drill-downs into each indicator's expanded chart row, directly below the matching driver chart. Kept the drill-down bodies as reusable templates and switched input-chart handlers to delegated events so select changes and row-click chart selection still work after scorecard rebuilds.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Gates: `git diff --check` passed; `uv run pytest -q` passed (43 passed, 4 xfailed); `uv run ruff check .` passed; `uv run python -m macro_framework.build --use-cache` passed from cache and rebuilt outputs/dashboard.html + snapshots/2026-05-26.json.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-26T11:36:28Z — Task 42a MMI driver mini-brief depth
- What: Deepened Growth Impulses, Sector Breadth, and Financial Conditions mini-briefs into deterministic 6-sentence bottom-up reads: latest top mover, current MMI support/drag, leading supporters, leading drags, breadth/fragility classification, and next-watch conditions. Dashboard now renders the full generated brief instead of truncating at four sentences.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Gates: `git diff --check` passed; `uv run pytest -q` passed (43 passed, 4 xfailed); `uv run ruff check .` passed; `uv run python -m macro_framework.build --use-cache` passed from cache and rebuilt outputs/dashboard.html + snapshots/2026-05-26.json.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-26T11:44:31Z — Task 43a MMI drill-down sort and brief placement
- What: Updated Growth Impulses, Sector Breadth, and Financial Conditions drill-downs to sort inputs by absolute current z-score, kept 7d/30d zΔ as context columns, and moved mini-briefs directly below each expanded driver chart before the input toggle. Rebuilt dashboard/snapshot from cached data.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Gates: `git diff --check` passed; `uv run pytest -q` passed (43 passed, 4 xfailed); `uv run ruff check .` passed; `uv run python -m macro_framework.build --use-cache` passed from cache and rebuilt outputs/dashboard.html + snapshots/2026-05-26.json.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-26T11:57:28Z — Task 44a Reference Library ISM/CPI/PPI
- What: Added Reference Library official inflation charts for headline CPI, core CPI, and broad PPI (PPIACO) as YoY rates; added PPIACO to the FRED fetch set and made cache use refresh if a cached payload is missing expected series. Verified FRED's legacy NAPM/ISM Manufacturing PMI CSV endpoint is unavailable, so ISM remains an explicit unavailable row unless an official NAPM series exists in local data.
- Files touched: src/macro_framework/build.py; src/macro_framework/macro_pipeline.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Gates: `git diff --check` passed; `uv run pytest -q` passed (44 passed, 4 xfailed); `uv run ruff check .` passed; `uv run python -m macro_framework.build --no-cache` refreshed PPIACO; `uv run python -m macro_framework.build --use-cache` passed from refreshed cache.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: Official ISM Manufacturing PMI/NAPM data is not currently available via FRED CSV (NAPM returns 404); use an ISM-licensed feed or approve a clearly-labeled proxy if Martin needs this chart populated.

## 2026-05-26T12:07:26Z — Task 45a Reference Library ISM PMI source
- What: Added DBnomics ISM/pmi/pm fetch for ISM Manufacturing PMI as `ISM_PMI`, wired cache expected-series refresh and the Reference Library row/chart, and filtered DBnomics' suspicious Sep-Dec 2025 low-teens tail so the dashboard charts the last plausible PMI value instead of bad mirror data. Fresh build shows ISM Manufacturing PMI 48.70 from the DBnomics mirror; latest valid source month is 2025-08 before the filtered tail.
- Files touched: src/macro_framework/macro_pipeline.py; src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: DBnomics currently exposes suspicious 2025-09..2025-12 values (11.1/10.0/10.0/10.3), so the helper filters out-of-range PMI values and carries forward 2025-08=48.7 until the mirror is corrected or a better licensed ISM feed is available.

## 2026-05-26T12:16:09Z — Task 46a ISM reference chart history
- What: Fixed the Reference Library ISM Manufacturing PMI chart to render recovered monthly observation points instead of the daily forward-filled tail; payload now carries per-library dates, preserves the 50 reference line, and stops ISM at the latest valid DBnomics observation (2025-08=48.7 after suspicious Sep-Dec tail filtering). Verified dashboard payload has 63 non-null ISM chart values, 49 distinct values, 2020-05-01=43.1 through 2025-08-01=48.7.
- Files touched: src/macro_framework/build.py; tests/test_smoke.py; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: DBnomics still exposes suspicious 2025-09..2025-12 low-teens ISM values, so they remain filtered until the mirror is corrected or a better licensed ISM feed is available.

## 2026-05-26T12:29:03Z — Task 47a high-level brief simplification
- What: Reworked the weekly brief generation prompts for the top, market, and economy dashboard briefs toward plain-English explanations for non-macro colleagues, then force-regenerated the 2026-05-26 briefs and rebuilt the dashboard/snapshot from cache.
- Files touched: src/macro_framework/weekly_briefs.py; briefs/2026-05-26/top.md; briefs/2026-05-26/market.md; briefs/2026-05-26/economy.md; outputs/dashboard.html; snapshots/2026-05-26.json; .engineer/progress.md
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-27T07:40:52Z — Task 48 fresh dashboard and briefs
- What: Force-regenerated the 2026-05-27 market/economy/top weekly briefs after a fresh no-cache data build, rebuilt outputs/dashboard.html and snapshots/2026-05-27.json, and kept MRMI/MMI math/UI/Supabase schema unchanged. Latest read: MRMI +0.18 → CAUTION / 75% exposure, MMI +0.47, macro buffer +0.46, stress score 0.8 Calm.
- Files touched: briefs/2026-05-27/market.md; briefs/2026-05-27/economy.md; briefs/2026-05-27/top.md; outputs/dashboard.html; snapshots/2026-05-27.json; tests/test_smoke.py; .engineer/progress.md
- Gates: `git diff --check` passed; `uv run ruff check .` passed; `uv run pytest -q` passed (46 passed, 4 xfailed); `uv run python -m macro_framework.build --no-cache` passed; `uv run python -m macro_framework.build --use-cache` passed; `uv run python -m macro_framework.sync_to_supabase doctor` passed (schema version 3). Supabase latest sync was not run because this task was dashboard/brief refresh only.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-27T07:54:19Z — Task 49 input column order
- What: Reordered all input drill-down tables (Growth Impulses, Sector Breadth, Financial Conditions) to show Input / Group / Current z / 7d zΔ / 30d zΔ while preserving the existing |current z| sort. Rebuilt dashboard from cache; no MRMI/MMI math or brief content changed.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-27.json; .engineer/progress.md
- Gates: `uv run python -m macro_framework.build --use-cache` passed; `git diff --check` passed; `uv run ruff check .` passed; `uv run pytest -q` passed (46 passed, 4 xfailed); direct HTML check verified the requested column order in Growth Impulses, Sector Breadth, and Financial Conditions.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none

## 2026-05-27T07:58:08Z — Task 50 scale label overlap fix
- What: Fixed the MRMI hero scale-bar label collision by anchoring the close cash/long threshold labels outward from their ticks (`−0.50 · cash` left-aligned to the left side, `+0.25 · long` right-side start), with nowrap labels. Threshold positions, MRMI math, posture, and data are unchanged.
- Files touched: src/macro_framework/build.py; outputs/dashboard.html; snapshots/2026-05-27.json; .engineer/progress.md
- Gates: `uv run python -m macro_framework.build --use-cache` passed; `git diff --check` passed; `uv run ruff check .` passed; `uv run pytest -q` passed (46 passed, 4 xfailed); direct HTML check confirmed scale tick classes and outward anchoring CSS are rendered.
- Commit: pending (this commit)
- Status: completed
- Open thread for next dispatch: none
