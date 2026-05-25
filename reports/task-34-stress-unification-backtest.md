# Task 34 — Stress unification backtest spike

Generated: 2026-05-25T08:04:00Z dispatch, using the production data path (`fetch_all_data(use_cache=True)`, which refreshed the cache during this run) and the same indicator builders used by `src/macro_framework/backtest_production.py`.

Method: full-sample grid search over SPX / IWM / BTC. Objective is average Calmar across the three assets; ties break on lower average % time in cash. MRMI is still interpreted as `> 0 = long`, `<= 0 = cash`.

## Best params found by grid search

- α: `0.75`
- β: `0.5`
- λ: `10`
- buffer_size: `0.5`
- threshold: `0.75`
- stress_raw p99 for normalization: `10.008333`
- grid size: `2400` parameter sets
- objective: average Calmar `2.551`, average cash `48.43%`

For context, the best thesis-preserving point with λ > 0 and at least one single-axis term active was `{'alpha': 0.75, 'beta': 0.5, 'lambda': 10, 'buffer_size': 0.5, 'threshold': 0.75}` with average Calmar `2.551` and average cash `48.43%`.

## Headline table

| Asset | Strategy | Ann. return | Max DD | Calmar | Sharpe | Cash time | Switches |
|---|---:|---:|---:|---:|---:|---:|---:|
| SPX | Current | +20.63% | -10.07% | 2.05 | 1.97 | +21.30% | 104 |
| SPX | New best | +20.96% | -6.23% | 3.37 | 2.82 | +48.43% | 210 |
| IWM | Current | +22.62% | -11.80% | 1.92 | 1.47 | +21.30% | 104 |
| IWM | New best | +26.87% | -7.49% | 3.59 | 2.24 | +48.43% | 210 |
| BTC | Current | +40.83% | -68.17% | 0.60 | 0.96 | +21.30% | 104 |
| BTC | New best | +42.66% | -60.92% | 0.70 | 1.13 | +48.43% | 210 |

## Sensitivity around the best params

The ±20% check is one-at-a-time around the best grid point, recalculating the historical 99th-percentile normalization each run.

| Perturbation | Avg Calmar | Avg cash | SPX ann/DD | IWM ann/DD | BTC ann/DD |
|---|---:|---:|---:|---:|---:|
| alpha → 0.6 | 1.899 | 48.15% | +20.30% / -7.12% | +25.75% / -11.80% | +40.44% / -60.92% |
| alpha → 0.9 | 2.440 | 48.59% | +20.22% / -6.23% | +25.44% / -7.49% | +41.22% / -60.92% |
| beta → 0.4 | 2.515 | 48.40% | +20.84% / -6.23% | +26.30% / -7.49% | +41.90% / -60.92% |
| beta → 0.6 | 2.511 | 48.53% | +20.72% / -6.23% | +26.39% / -7.49% | +41.79% / -61.17% |
| lambda → 8 | 2.400 | 48.68% | +19.98% / -6.23% | +24.96% / -7.49% | +40.35% / -61.17% |
| lambda → 12 | 1.921 | 48.18% | +20.53% / -7.12% | +25.98% / -11.80% | +41.41% / -60.92% |
| buffer_size → 0.4 | 3.079 | 54.36% | +19.21% / -4.67% | +25.18% / -5.69% | +42.67% / -61.27% |
| buffer_size → 0.6 | 2.017 | 42.72% | +22.31% / -7.28% | +28.28% / -11.80% | +38.36% / -65.31% |
| threshold → 0.6 | 1.846 | 40.15% | +21.97% / -8.37% | +27.83% / -11.80% | +38.68% / -69.62% |
| threshold → 0.9 | 3.147 | 57.56% | +19.16% / -4.32% | +24.81% / -5.66% | +39.12% / -62.82% |

## Behavioral check — 2022 stagflation episode

First cash day in Q1-Q3 2022: old `2022-01-13`, new `2022-01-01`.

| Month | Old min MRMI | Old cash days | New min MRMI | New cash days |
|---|---:|---:|---:|---:|
| 2022-01 | -1.641 | 61.3% | -2.418 | 100.0% |
| 2022-02 | -1.180 | 96.4% | -1.976 | 100.0% |
| 2022-03 | -2.418 | 100.0% | -2.899 | 100.0% |
| 2022-04 | -2.152 | 90.0% | -2.402 | 100.0% |
| 2022-05 | -2.396 | 100.0% | -2.646 | 100.0% |
| 2022-06 | -1.430 | 76.7% | -2.049 | 100.0% |
| 2022-07 | -0.665 | 48.4% | -1.409 | 71.0% |
| 2022-08 | 0.132 | 0.0% | -0.621 | 29.0% |
| 2022-09 | -0.933 | 36.7% | -1.685 | 96.7% |

Both old and new trigger CASH in 2022. The new formula moves earlier and stays deeper because the OR terms plus λ·g·i amplifier reduce the macro buffer before the old clipped AND term fully saturates.

## Behavioral check 2 — COVID Q1 2020 recession-only episode

First cash day in Feb-Apr 2020: old `2020-02-01`, new `2020-02-01`.

| Month | Old min MRMI | Old cash days | New min MRMI | New cash days |
|---|---:|---:|---:|---:|
| 2020-02 | -2.889 | 34.5% | -3.618 | 72.4% |
| 2020-03 | -3.703 | 100.0% | -4.441 | 100.0% |
| 2020-04 | -1.116 | 23.3% | -1.942 | 96.7% |

The requested trade-off shows up as deeper/longer CASH behavior in the new MRMI. The old production MRMI still goes CASH here because market momentum collapsed, but the new α·g term makes the recession-growth shock penalize the macro buffer even without needing the old inflation AND gate to fire.

## Recommendation

**ship the new formula.** Within the requested grid, the best OR+AND parameter set preserves Martin's thesis and improves Calmar for all three assets: SPX 2.05 → 3.37, IWM 1.92 → 3.59, BTC 0.60 → 0.70. Max drawdown also improves across all three assets. The cost is material: cash time rises from 21.3% to 48.4% and switches roughly double from 104 to 210, so Phase 2 should present this as a more defensive strategy rather than a small visualization cleanup.

Before production replacement, Martin/Bob should explicitly accept the higher cash/turnover profile and consider a narrow follow-up search around buffer/threshold, since the ±20% sensitivity suggests nearby values outside the requested grid may improve Calmar further.

## Narrow grid refinement (buffer × threshold)

Generated: 2026-05-25T08:24:53Z dispatch. Fixed α=`0.75`, β=`0.5`, λ=`10`, then swept `buffer_size × threshold` across the requested 35 combinations using the same cached production data path and canonical SPX/IWM/BTC backtest objective as Phase 1.

| Buffer | Threshold | Avg Calmar | Avg cash time | Avg switches |
|---:|---:|---:|---:|---:|
| 0.30 | 0.75 | 4.027 | 60.88% | 215 |
| 0.30 | 0.80 | 3.900 | 63.83% | 221 |
| 0.30 | 0.85 | 4.024 | 66.97% | 205 |
| 0.30 | 0.90 | 3.519 | 70.39% | 204 |
| 0.30 | 0.95 | 3.362 | 74.15% | 190 |
| 0.35 | 0.75 | 3.135 | 57.18% | 217 |
| 0.35 | 0.80 | 4.026 | 60.98% | 217 |
| 0.35 | 0.85 | 3.926 | 63.99% | 219 |
| 0.35 | 0.90 | 3.969 | 67.06% | 203 |
| 0.35 | 0.95 | 3.520 | 70.64% | 208 |
| 0.40 | 0.75 | 3.079 | 54.36% | 218 |
| 0.40 | 0.80 | 3.133 | 57.25% | 215 |
| 0.40 | 0.85 | 4.017 | 61.01% | 215 |
| 0.40 | 0.90 | 3.963 | 64.12% | 215 |
| 0.40 | 0.95 | 3.966 | 67.31% | 205 |
| 0.45 | 0.75 | 2.464 | 51.29% | 206 |
| 0.45 | 0.80 | 3.081 | 54.58% | 214 |
| 0.45 | 0.85 | 3.130 | 57.43% | 213 |
| 0.45 | 0.90 | 3.994 | 61.14% | 211 |
| 0.45 | 0.95 | 3.945 | 64.30% | 211 |
| 0.50 | 0.75 | 2.551 | 48.43% | 210 |
| 0.50 | 0.80 | 2.427 | 51.54% | 202 |
| 0.50 | 0.85 | 3.069 | 54.83% | 212 |
| 0.50 | 0.90 | 3.147 | 57.56% | 211 |
| 0.50 | 0.95 | 3.990 | 61.23% | 217 |
| 0.55 | 0.75 | 1.999 | 45.04% | 218 |
| 0.55 | 0.80 | 2.451 | 48.59% | 204 |
| 0.55 | 0.85 | 2.412 | 51.69% | 202 |
| 0.55 | 0.90 | 3.070 | 54.89% | 208 |
| 0.55 | 0.95 | 3.159 | 57.69% | 217 |
| 0.60 | 0.75 | 2.017 | 42.72% | 216 |
| 0.60 | 0.80 | 2.010 | 45.17% | 216 |
| 0.60 | 0.85 | 2.400 | 48.68% | 204 |
| 0.60 | 0.90 | 2.417 | 51.88% | 208 |
| 0.60 | 0.95 | 3.060 | 54.99% | 206 |

### New best params

- α: `0.75`
- β: `0.5`
- λ: `10`
- buffer_size: `0.3`
- threshold: `0.75`
- objective: average Calmar `4.027`, average cash `60.88%`, average switches `215`

| Asset | Strategy | Ann. return | Max DD | Calmar | Sharpe | Cash time | Switches |
|---|---:|---:|---:|---:|---:|---:|---:|
| SPX | Narrow best | +18.72% | -2.72% | 6.88 | 3.06 | 60.88% | 215 |
| IWM | Narrow best | +24.81% | -5.47% | 4.53 | 2.44 | 60.88% | 215 |
| BTC | Narrow best | +40.71% | -60.75% | 0.67 | 1.19 | 60.88% | 215 |

### Narrow best vs Phase 1 best

Phase 1 best was α=`0.75`, β=`0.5`, λ=`10`, buffer_size=`0.5`, threshold=`0.75` with average Calmar `2.551`, average cash `48.43%`, and average switches `210`.

| Metric | Phase 1 best | Narrow best | Delta |
|---|---:|---:|---:|
| Avg Calmar | 2.551 | 4.027 | +1.476 |
| Avg cash time | 48.43% | 60.88% | +12.45pp |
| Avg switches | 210 | 215 | +5 |

| Asset | Metric | Phase 1 best | Narrow best | Delta |
|---|---|---:|---:|---:|
| SPX | Ann. return | +20.96% | +18.72% | -2.24pp |
| SPX | Max DD | -6.23% | -2.72% | +3.51pp |
| SPX | Calmar | 3.37 | 6.88 | +3.51 |
| SPX | Sharpe | 2.82 | 3.06 | +0.23 |
| SPX | Cash time | 48.43% | 60.88% | +12.45pp |
| SPX | Switches | 210 | 215 | +5 |
| IWM | Ann. return | +26.87% | +24.81% | -2.06pp |
| IWM | Max DD | -7.49% | -5.47% | +2.02pp |
| IWM | Calmar | 3.59 | 4.53 | +0.94 |
| IWM | Sharpe | 2.24 | 2.44 | +0.20 |
| IWM | Cash time | 48.43% | 60.88% | +12.45pp |
| IWM | Switches | 210 | 215 | +5 |
| BTC | Ann. return | +42.66% | +40.71% | -1.96pp |
| BTC | Max DD | -60.92% | -60.75% | +0.17pp |
| BTC | Calmar | 0.70 | 0.67 | -0.03 |
| BTC | Sharpe | 1.13 | 1.19 | +0.06 |
| BTC | Cash time | 48.43% | 60.88% | +12.45pp |
| BTC | Switches | 210 | 215 | +5 |

### Narrow-grid recommendation

**Ship at the new best params** if Martin accepts the substantially more defensive profile: buffer_size `0.3` / threshold `0.75` lifts average Calmar from `2.551` to `4.027`, mainly by cutting SPX/IWM drawdowns, while cash time rises another `12.45pp` and BTC Calmar is essentially flat/slightly lower.

## Pareto frontier — cash time vs Calmar

Generated: 2026-05-25T08:38:37Z dispatch. Re-ran the original Phase 1 `2400`-combo grid using `calc_milk_road_macro_index_unified_stress` and the same cached production data path / SPX-IWM-BTC full-sample backtest objective. All rows are saved in `reports/task-34-phase1-grid-all-rows.csv`.

For each cash-time target, the frontier point is the highest average Calmar available at or below that average cash-time cap; ties break toward lower cash time.

| Cash cap | Params | Avg Calmar | Avg cash time | Avg switches | SPX ann / DD / Calmar | IWM ann / DD / Calmar | BTC ann / DD / Calmar |
|---:|---|---:|---:|---:|---:|---:|---:|
| ≤25% | `α=0.25, β=0, λ=0, buffer=0.5, threshold=0` | 1.628 | 21.30% | 114 | +21.60% / -9.66% / 2.24 | +24.36% / -11.80% / 2.07 | +39.73% / -68.17% / 0.58 |
| ≤30% | `α=0.5, β=0.75, λ=10, buffer=0.5, threshold=0.25` | 1.746 | 28.07% | 130 | +22.35% / -9.60% / 2.33 | +26.31% / -11.80% / 2.23 | +41.94% / -61.55% / 0.68 |
| ≤35% | `α=0, β=0, λ=0, buffer=0.5, threshold=0.5` | 1.818 | 34.16% | 172 | +23.41% / -9.60% / 2.44 | +28.72% / -11.80% / 2.43 | +40.77% / -70.00% / 0.58 |
| ≤40% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` | 1.833 | 35.92% | 186 | +23.96% / -9.60% / 2.49 | +28.91% / -11.80% / 2.45 | +38.75% / -70.00% / 0.55 |
| ≤45% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` | 1.833 | 35.92% | 186 | +23.96% / -9.60% / 2.49 | +28.91% / -11.80% / 2.45 | +38.75% / -70.00% / 0.55 |
| ≤50% | `α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75` | 2.551 | 48.43% | 210 | +20.96% / -6.23% / 3.37 | +26.87% / -7.49% / 3.59 | +42.66% / -60.92% / 0.70 |

### Integer-cap frontier

| Cash cap | Best avg Calmar | Actual avg cash | Params |
|---:|---:|---:|---|
| ≤20% | 1.494 | 16.97% | `α=0.25, β=0, λ=0, buffer=1, threshold=0.25` ← frontier step |
| ≤21% | 1.572 | 20.51% | `α=0, β=0, λ=0, buffer=0.5, threshold=0` ← frontier step |
| ≤22% | 1.628 | 21.30% | `α=0.25, β=0, λ=0, buffer=0.5, threshold=0` ← frontier step |
| ≤23% | 1.628 | 21.30% | `α=0.25, β=0, λ=0, buffer=0.5, threshold=0` |
| ≤24% | 1.628 | 21.30% | `α=0.25, β=0, λ=0, buffer=0.5, threshold=0` |
| ≤25% | 1.628 | 21.30% | `α=0.25, β=0, λ=0, buffer=0.5, threshold=0` |
| ≤26% | 1.628 | 21.30% | `α=0.25, β=0, λ=0, buffer=0.5, threshold=0` |
| ≤27% | 1.714 | 26.76% | `α=0, β=0, λ=0, buffer=0.5, threshold=0.25` ← frontier step |
| ≤28% | 1.737 | 27.92% | `α=0, β=0.75, λ=10, buffer=0.5, threshold=0.25` ← frontier step |
| ≤29% | 1.746 | 28.07% | `α=0.5, β=0.75, λ=10, buffer=0.5, threshold=0.25` ← frontier step |
| ≤30% | 1.746 | 28.07% | `α=0.5, β=0.75, λ=10, buffer=0.5, threshold=0.25` |
| ≤31% | 1.757 | 30.96% | `α=1, β=0.25, λ=1, buffer=1, threshold=0.75` ← frontier step |
| ≤32% | 1.757 | 30.96% | `α=1, β=0.25, λ=1, buffer=1, threshold=0.75` |
| ≤33% | 1.757 | 30.96% | `α=1, β=0.25, λ=1, buffer=1, threshold=0.75` |
| ≤34% | 1.757 | 30.96% | `α=1, β=0.25, λ=1, buffer=1, threshold=0.75` |
| ≤35% | 1.818 | 34.16% | `α=0, β=0, λ=0, buffer=0.5, threshold=0.5` ← frontier step |
| ≤36% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` ← frontier step |
| ≤37% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤38% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤39% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤40% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤41% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤42% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤43% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤44% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤45% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤46% | 1.833 | 35.92% | `α=1, β=0, λ=3, buffer=0.5, threshold=0.5` |
| ≤47% | 1.977 | 46.93% | `α=0, β=0, λ=1, buffer=0.5, threshold=0.75` ← frontier step |
| ≤48% | 2.399 | 47.93% | `α=0.25, β=0, λ=3, buffer=0.5, threshold=0.75` ← frontier step |
| ≤49% | 2.551 | 48.43% | `α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75` ← frontier step |
| ≤50% | 2.551 | 48.43% | `α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75` |

### Recommendation

For the **stay-long-mostly** philosophy (production = 21% cash), the ≤25% frontier point is closest on exposure (`21.30%` cash, average Calmar `1.628`) but is not a thesis-preserving upgrade because `λ=0` removes the stagflation amplifier. The closest meaningful upgrade is the ≤30% cap: `α=0.5, β=0.75, λ=10, buffer=0.5, threshold=0.25`, with average Calmar `1.746`, cash `28.07%`, and `130` switches.

For a **more defensive** shift, the ≤40%/≤45% representative point (`α=1, β=0, λ=3, buffer=0.5, threshold=0.5`) is available at `35.92%` cash and average Calmar `1.833`, but the frontier does not find much additional payoff until cash approaches the high-40s. If Martin accepts roughly half-time cash exposure, prefer the Phase 1 best: `α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75` with average Calmar `2.551` and cash `48.43%`.

## Out-of-sample validation

Generated: 2026-05-25T08:55:39Z dispatch. Method matches `src/macro_framework/backtest_production.py`: align MRMI and SPX/IWM/BTC return rows, split the first 70% as IS and last 30% as OOS, and keep the existing walk-forward/year-by-year check. Data span after alignment: `2017-09-02` to `2026-05-25` (`3188` rows; IS `2231` rows through `2023-10-11`, OOS `957` rows from `2023-10-12`).

### Test 1 — headline IS/OOS at Phase 1 best params

Phase 1 best new params: `α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75`. Production baseline: legacy `calc_milk_road_macro_index`, `buffer=1.0`, `threshold=0.5`.

| Asset | Strategy | Split | Ann. return | Max DD | Calmar | Sharpe | Cash time | Switches |
|---|---|---|---|---|---|---|---|---|
| SPX | New Phase 1 best | IS | +19.87% | -6.23% | 3.19 | 2.65 | 51.73% | 141 |
| IWM | New Phase 1 best | IS | +25.06% | -7.49% | 3.35 | 2.23 | 51.73% | 141 |
| BTC | New Phase 1 best | IS | +39.56% | -60.92% | 0.65 | 1.02 | 51.73% | 141 |
| SPX | New Phase 1 best | OOS | +23.53% | -2.86% | 8.22 | 3.24 | 40.75% | 69 |
| IWM | New Phase 1 best | OOS | +31.20% | -6.83% | 4.57 | 2.29 | 40.75% | 69 |
| BTC | New Phase 1 best | OOS | +50.17% | -24.67% | 2.03 | 1.52 | 40.75% | 69 |
| SPX | Production | IS | +18.62% | -10.07% | 1.85 | 1.74 | 24.25% | 78 |
| IWM | Production | IS | +20.31% | -11.80% | 1.72 | 1.36 | 24.25% | 78 |
| BTC | Production | IS | +43.95% | -68.17% | 0.64 | 0.97 | 24.25% | 78 |
| SPX | Production | OOS | +25.43% | -4.73% | 5.38 | 2.60 | 14.42% | 26 |
| IWM | Production | OOS | +28.18% | -7.49% | 3.76 | 1.71 | 14.42% | 26 |
| BTC | Production | OOS | +33.82% | -46.57% | 0.73 | 1.00 | 14.42% | 26 |

Acceptance check for the new formula:

| Asset | New IS Calmar | New OOS Calmar | OOS / IS |
|---|---|---|---|
| SPX | 3.19 | 8.22 | 258% |
| IWM | 3.35 | 4.57 | 137% |
| BTC | 0.65 | 2.03 | 313% |

### Test 2 — IS-only re-optimization, then OOS evaluation

The IS-only grid reused the exact saved Phase 1 grid (`2400` combos: α ∈ {0, 0.25, 0.5, 0.75, 1}, β ∈ {0, 0.25, 0.5, 0.75, 1}, λ ∈ {0, 1, 3, 5, 10, 20}, buffer ∈ {0.5, 1.0, 1.5, 2.0}, threshold ∈ {0, 0.25, 0.5, 0.75}). For the honest IS-only application, the OOS signal uses the stress-normalization p99 fitted on IS only.

| Param set | Params | Stress p99 | IS avg Calmar | Full-sample avg Calmar |
|---|---|---|---|---|
| Full-sample Phase 1 best | α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75 | 10.008333 | 2.396 | 2.551 |
| IS-only optimum | α=1, β=0.5, λ=10, buffer=0.5, threshold=0.75 | 13.239206 | 2.434 | 2.446 |

OOS-only performance comparison:

| Asset | Strategy | Split | Ann. return | Max DD | Calmar | Sharpe | Cash time | Switches |
|---|---|---|---|---|---|---|---|---|
| SPX | Full-sample best | OOS | +23.53% | -2.86% | 8.22 | 3.24 | 40.75% | 69 |
| IWM | Full-sample best | OOS | +31.20% | -6.83% | 4.57 | 2.29 | 40.75% | 69 |
| BTC | Full-sample best | OOS | +50.17% | -24.67% | 2.03 | 1.52 | 40.75% | 69 |
| SPX | IS-optimal | OOS | +23.50% | -2.86% | 8.21 | 3.24 | 40.86% | 69 |
| IWM | IS-optimal | OOS | +30.85% | -6.83% | 4.52 | 2.27 | 40.86% | 69 |
| BTC | IS-optimal | OOS | +49.66% | -24.67% | 2.01 | 1.51 | 40.86% | 69 |

### Test 3 — walk-forward annual returns

Phase 1 best params, reported by calendar year using the existing `test_walk_forward` convention.

| Year | SPX strat ann | SPX B&H ann | IWM strat ann | IWM B&H ann | BTC strat ann | BTC B&H ann |
|---|---|---|---|---|---|---|
| 2017 | +20.82% | +17.29% | +19.14% | +20.05% | +591.96% | +814.26% |
| 2018 | +12.20% | -4.35% | +7.99% | -7.82% | -29.53% | -60.09% |
| 2019 | +18.91% | +19.14% | +22.35% | +16.91% | +0.20% | +57.00% |
| 2020 | +40.66% | +10.93% | +63.96% | +13.40% | +143.25% | +161.15% |
| 2021 | +20.58% | +17.87% | +31.14% | +9.82% | +70.22% | +38.13% |
| 2022 | +10.05% | -13.87% | +8.93% | -14.64% | +5.39% | -50.86% |
| 2023 | +20.42% | +16.16% | +34.79% | +11.34% | +44.70% | +91.06% |
| 2024 | +20.37% | +15.52% | +24.81% | +7.71% | +131.05% | +72.66% |
| 2025 | +23.53% | +11.05% | +25.38% | +8.58% | +13.98% | -4.42% |
| 2026 | +29.53% | +16.48% | +43.31% | +29.49% | -1.44% | -19.44% |

### Recommendation

**Phase 2 ready to ship, subject to Martin accepting the defensive/cash-time profile already flagged above.** Test 1 passes the mechanical OOS/IS Calmar retention threshold for all three assets: SPX `258%`, IWM `137%`, BTC `313%`. Test 2 is also reassuring: the IS-only optimum changes only α (`1.0` instead of `0.75`) while keeping β, λ, buffer, and threshold identical; its IS avg Calmar (`2.434`) is only `+0.039` above the full-sample best on IS, and the two OOS metric sets are effectively identical. Walk-forward does not show a year with strategy annual return below `-20%` while SPX buy-and-hold was up. This validation does not remove the earlier business trade-off — roughly half-time cash and higher switches — but it does not show meaningful overfitting in the canonical OOS tests.
