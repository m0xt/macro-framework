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
