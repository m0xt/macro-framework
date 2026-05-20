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
