# Backtest canonical signal check — 2026-05-20

## Result

**Divergence found. Do not propagate fresh full-sample numbers yet.**

`src/macro_framework/backtest_production.py` and the live dashboard build path agree on the current/latest MRMI value and on every overlapping non-null date, but they do **not** produce the same full-sample signal series. The backtest harness starts 317 rows earlier because it fills missing macro-stress inputs with zero; the production build path leaves those rows as `NaN` until the release-lagged macro context is available.

## Evidence

Fresh data check was run with `fetch_all_data(use_cache=False)` on 2026-05-20.

```text
DATA_RANGE 2016-01-01 2026-05-20 3774
LATEST 2026-05-20 pipeline=0.359068840073 prod=0.359068840073 diff=0.000000000000
PIPE_NON_NA 2017-09-01 3184
PROD_NON_NA 2016-10-19 3501
JOINT_ROWS 3184 MAX_ABS_DIFF 0.000000000000
PROD_ONLY_ROWS 317
PROD_ONLY_FIRST_LAST 2016-10-19 2017-08-31
```

Backtest impact from using the live build-path MRMI series rather than `production_mrmi`'s filled series:

```text
BACKTEST_SIGNAL prod rows 3501
  spx alpha=11.185321 strat_dd=-10.067246 green_pct=79.891460
  iwm alpha=15.512495 strat_dd=-11.796988 green_pct=79.891460
  btc alpha=14.090247 strat_dd=-68.165200 green_pct=79.891460
BACKTEST_SIGNAL pipe rows 3184
  spx alpha=11.506743 strat_dd=-10.067246 green_pct=78.674623
  iwm alpha=15.932365 strat_dd=-11.796988 green_pct=78.674623
  btc alpha=16.532867 strat_dd=-68.165200 green_pct=78.674623
```

## Code-path comparison

Live build path:

- `src/macro_framework/build.py` computes `gii = calc_growth_impulse(data)`, `fincon = calc_financial_conditions(data)`, `breadth = calc_sector_breadth(data)`, then `composite = calc_composite(gii, fincon, breadth)`.
- It computes `macro_ctx = calc_macro_context(data, lookback_years=3)` with default `apply_release_lags=True`.
- It computes `mrmi_combined = calc_milk_road_macro_index(composite, macro_ctx, buffer_size=1.0, threshold=0.5)`.
- `calc_milk_road_macro_index` leaves `stress_intensity`, `macro_buffer`, and `mrmi` as `NaN` while release-lagged macro inputs are unavailable.

Backtest harness:

- `production_mrmi` uses the same component functions and the same equal weights (`1.0/1.0/1.0`), `buffer_size=1.0`, `threshold=0.5`, release-lagged `calc_macro_context(data)` defaults, and the same invested rule (`MRMI > 0`).
- But it recomputes the MRMI formula inline and does `stress = (re_neg * inf_pos).clip(upper=1.0).fillna(0.0)`.
- That `fillna(0.0)` is not present in the live build path and effectively treats missing macro stress as `OFF`, producing an investable MRMI series from 2016-10-19 instead of 2017-09-01.

## Invariants checked

- MRMI formula on overlapping valid dates: identical (`max_abs_diff = 0`).
- Component functions: both paths call the same production functions (`calc_growth_impulse`, `calc_sector_breadth`, `calc_financial_conditions`, `calc_macro_context`, `calc_composite`).
- Sector Breadth lookback: unchanged at the locked `LOOKBACK = 90`.
- Parameters: same equal weights, `buffer_size=1.0`, `threshold=0.5`, default release lags applied.
- Invested/cash rule: same `MRMI > 0`.
- Smoke/lock tests were inspected as the invariants source; they lock formula, stress clipping, release lags, and breadth lookback.

## Phase 2 status

Phase 2 was **not executed** because Phase 1 did not pass the hard gate. No presentation or dashboard numbers were updated.

Incidental observation only: the dashboard backtest card text is currently hardcoded in `src/macro_framework/build.py`, so it will not survive refreshes as canonical data unless that source is rewired in a future follow-up. Per the hard gate, I did not change it in this run.

## Recommended decision

Martin should decide whether the canonical full-sample backtest should:

1. use the live build-path semantics and drop dates until release-lagged macro context is available, or
2. intentionally treat unavailable early macro stress as `OFF` and update the live path/docs/tests to make that policy explicit.

Until that decision is made, the fresh `backtest_production.py` full-sample numbers should not be propagated as canonical production-signal results.
