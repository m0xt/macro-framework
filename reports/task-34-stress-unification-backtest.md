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
