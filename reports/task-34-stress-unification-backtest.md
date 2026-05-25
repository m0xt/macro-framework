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
