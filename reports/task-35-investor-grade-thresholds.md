# Task 35a — Investor-grade MRMI thresholds and caution zones

Generated: 2026-05-26T08:14:38Z dispatch. Scope was research/backtest only; production MRMI math, dashboard behavior, snapshots, Supabase sync, and docs were not changed.

Method: use the current production unified-stress MRMI series from `fetch_all_data(use_cache=True)` and `calc_milk_road_macro_index` with task-34 locked params (`α=0.75`, `β=0.50`, `λ=10`, `buffer_size=0.5`, `threshold=0.75`). Reinterpret the already-computed MRMI signal only:

- Binary variants: `LONG` when `MRMI > cash_cut`, otherwise full cash.
- Symmetric caution-zone variants: `MRMI > +band` = 100% long; `MRMI < -band` = 0% long; within the band = partial exposure.
- Asymmetric variants: `MRMI < -0.50` = full cash; `-0.50 ≤ MRMI ≤ +0.25` = caution/partial exposure; `MRMI > +0.25` = full long.

Metrics are full-sample daily backtests over the canonical SPX/IWM/BTC setup. `Turnover` is the sum of absolute exposure changes, so a binary 0↔1 flip counts as `1.0` and a 50%→100% exposure step counts as `0.5`. `State changes` counts any non-zero exposure-state transition. Cash/caution/exposure percentages are identical across assets for a given interpretation layer because the MRMI signal is shared.

## Baselines

Current production interpretation is the shipped task-34 unified-stress signal with `MRMI > 0 = LONG`, `MRMI ≤ 0 = CASH`. The old pre-task-34 production baseline below is copied from the task-34 report for comparison.

| Strategy | Avg ann. | Avg max DD | Avg Calmar | Avg Sharpe | Full cash | Caution | Avg exposure | Switches/turnover | Notes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Old pre-task-34 production baseline | +28.03% | -30.01% | 1.52 | 1.47 | 21.30% | 0.00% | 78.70% | 104 | From `reports/task-34-stress-unification-backtest.md`; old stress interpretation. |
| Current task-34 production interpretation | +30.16% | -24.88% | 2.55 | 2.06 | 48.43% | 0.00% | 51.57% | 210 | Same as `Binary cash_cut +0.00` below. |

## Recommendation

Recommend the **asymmetric investor-friendly zone with 75% caution exposure** as the default interpretation candidate:

- Rule: `MRMI < -0.50` → full cash; `-0.50 ≤ MRMI ≤ +0.25` → caution / 75% long; `MRMI > +0.25` → 100% long.
- Product fit: full-cash time drops from `48.4%` to `27.9%`, inside the desired `20–35%` range; effective average exposure rises from `51.6%` to `62.9%`; turnover proxy drops from `210.0` to `147.8`.
- Trade-off: average Calmar falls from current production `2.55` to `2.04`, but remains above the old pre-task-34 baseline `1.52`; average annual return remains strong at `+28.6%`.
- Latest live classification: `CAUTION 75%` at MRMI `+0.1343` on `2026-05-25`, which is more investor-readable than forcing a binary long/cash decision around zero.

If Martin/DGal prefer maximum drawdown control over the “mostly invested” feel, the **same asymmetric zone with 50% caution** is the defensive alternative: full-cash time is also `27.9%`, average Calmar is `2.61`, and drawdown improves, but effective exposure is only `53.8%`, so it still reads closer to an active allocation overlay than an investor-grade index.

DGal's objection is materially solved by the recommended 75% caution variant: historical full-cash time falls by about `20.5pp` (`48.4% → 27.9%`) and the around-zero region becomes a caution state rather than a whipsaw-prone tactical cash trigger. It is not a free lunch — the current binary zero trigger has the strongest drawdown-adjusted score — but the asymmetric caution layer better matches the intended product semantics while keeping the unified-stress formula intact.

Generated from cached production data: 2017-09-02 to 2026-05-25 (3188 aligned daily rows).
Latest MRMI: +0.1343 on 2026-05-25.

## Average across SPX/IWM/BTC
| Variant | Live | Ann. | Max DD | Calmar | Sharpe | Full cash | Caution | Avg exposure | Turnover | State changes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Binary cash_cut +0.00 | LONG | +30.2% | -24.9% | 2.55 | 2.06 | 48.4% | 0.0% | 51.6% | 210.0 | 210 |
| Binary cash_cut -0.10 | LONG | +29.8% | -28.1% | 2.04 | 2.01 | 42.6% | 0.0% | 57.4% | 214.0 | 214 |
| Binary cash_cut -0.25 | LONG | +30.2% | -30.7% | 1.78 | 1.87 | 35.5% | 0.0% | 64.5% | 174.0 | 174 |
| Binary cash_cut -0.50 | LONG | +29.3% | -27.7% | 1.71 | 1.67 | 27.9% | 0.0% | 72.1% | 126.0 | 126 |
| Binary cash_cut -0.75 | LONG | +27.5% | -30.0% | 1.55 | 1.49 | 21.5% | 0.0% | 78.5% | 108.0 | 108 |
| Binary cash_cut -1.00 | LONG | +29.8% | -32.7% | 1.43 | 1.47 | 16.3% | 0.0% | 83.7% | 110.0 | 110 |
| Band ±0.10, 50% caution | LONG | +29.7% | -25.0% | 2.58 | 2.14 | 42.6% | 12.3% | 51.3% | 213.0 | 379 |
| Band ±0.25, 50% caution | CAUTION 50% | +27.9% | -24.9% | 2.67 | 2.17 | 35.5% | 29.0% | 50.0% | 193.5 | 379 |
| Band ±0.50, 50% caution | CAUTION 50% | +24.2% | -20.1% | 2.17 | 1.96 | 27.9% | 52.4% | 45.9% | 148.0 | 296 |
| Band ±0.75, 50% caution | CAUTION 50% | +17.8% | -18.9% | 1.73 | 1.68 | 21.5% | 72.0% | 42.5% | 95.0 | 190 |
| Band ±0.10, 75% caution | LONG | +29.8% | -26.5% | 2.32 | 2.09 | 42.6% | 12.3% | 54.4% | 213.5 | 379 |
| Band ±0.25, 75% caution | CAUTION 75% | +29.2% | -27.9% | 2.10 | 2.03 | 35.5% | 29.0% | 57.2% | 183.8 | 379 |
| Band ±0.50, 75% caution | CAUTION 75% | +27.0% | -23.7% | 1.88 | 1.81 | 27.9% | 52.4% | 59.0% | 137.0 | 296 |
| Band ±0.75, 75% caution | CAUTION 75% | +22.9% | -24.5% | 1.61 | 1.57 | 21.5% | 72.0% | 60.5% | 101.5 | 190 |
| Asym -0.50/+0.25, 50% caution | CAUTION 50% | +27.6% | -22.9% | 2.61 | 2.05 | 27.9% | 36.6% | 53.8% | 169.5 | 338 |
| Asym -0.50/+0.25, 75% caution | CAUTION 75% | +28.6% | -25.3% | 2.04 | 1.86 | 27.9% | 36.6% | 62.9% | 147.8 | 338 |

## Asset-level details
| Variant | Asset | Ann. | Max DD | Calmar | Sharpe | Full cash | Caution | Avg exposure | Turnover |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Binary cash_cut +0.00 | SPX | +21.0% | -6.2% | 3.37 | 2.82 | 48.4% | 0.0% | 51.6% | 210.0 |
| Binary cash_cut +0.00 | IWM | +26.9% | -7.5% | 3.59 | 2.24 | 48.4% | 0.0% | 51.6% | 210.0 |
| Binary cash_cut +0.00 | BTC | +42.7% | -60.9% | 0.70 | 1.13 | 48.4% | 0.0% | 51.6% | 210.0 |
| Binary cash_cut -0.10 | SPX | +22.5% | -7.3% | 3.09 | 2.78 | 42.6% | 0.0% | 57.4% | 214.0 |
| Binary cash_cut -0.10 | IWM | +28.9% | -11.8% | 2.45 | 2.25 | 42.6% | 0.0% | 57.4% | 214.0 |
| Binary cash_cut -0.10 | BTC | +37.9% | -65.3% | 0.58 | 1.01 | 42.6% | 0.0% | 57.4% | 214.0 |
| Binary cash_cut -0.25 | SPX | +23.1% | -9.6% | 2.41 | 2.60 | 35.5% | 0.0% | 64.5% | 174.0 |
| Binary cash_cut -0.25 | IWM | +28.1% | -11.8% | 2.38 | 2.02 | 35.5% | 0.0% | 64.5% | 174.0 |
| Binary cash_cut -0.25 | BTC | +39.4% | -70.8% | 0.56 | 1.00 | 35.5% | 0.0% | 64.5% | 174.0 |
| Binary cash_cut -0.50 | SPX | +22.0% | -9.6% | 2.29 | 2.27 | 27.9% | 0.0% | 72.1% | 126.0 |
| Binary cash_cut -0.50 | IWM | +25.8% | -11.8% | 2.19 | 1.76 | 27.9% | 0.0% | 72.1% | 126.0 |
| Binary cash_cut -0.50 | BTC | +40.1% | -61.6% | 0.65 | 0.98 | 27.9% | 0.0% | 72.1% | 126.0 |
| Binary cash_cut -0.75 | SPX | +20.9% | -10.1% | 2.08 | 2.01 | 21.5% | 0.0% | 78.5% | 108.0 |
| Binary cash_cut -0.75 | IWM | +23.7% | -11.8% | 2.01 | 1.54 | 21.5% | 0.0% | 78.5% | 108.0 |
| Binary cash_cut -0.75 | BTC | +37.9% | -68.2% | 0.56 | 0.92 | 21.5% | 0.0% | 78.5% | 108.0 |
| Binary cash_cut -1.00 | SPX | +22.2% | -12.0% | 1.85 | 1.96 | 16.3% | 0.0% | 83.7% | 110.0 |
| Binary cash_cut -1.00 | IWM | +23.5% | -12.8% | 1.84 | 1.45 | 16.3% | 0.0% | 83.7% | 110.0 |
| Binary cash_cut -1.00 | BTC | +43.7% | -73.4% | 0.59 | 0.99 | 16.3% | 0.0% | 83.7% | 110.0 |
| Band ±0.10, 50% caution | SPX | +20.9% | -5.6% | 3.76 | 2.95 | 42.6% | 12.3% | 51.3% | 213.0 |
| Band ±0.10, 50% caution | IWM | +26.9% | -8.2% | 3.30 | 2.36 | 42.6% | 12.3% | 51.3% | 213.0 |
| Band ±0.10, 50% caution | BTC | +41.2% | -61.2% | 0.67 | 1.12 | 42.6% | 12.3% | 51.3% | 213.0 |
| Band ±0.25, 50% caution | SPX | +20.3% | -4.9% | 4.16 | 3.02 | 35.5% | 29.0% | 50.0% | 193.5 |
| Band ±0.25, 50% caution | IWM | +26.4% | -8.2% | 3.24 | 2.39 | 35.5% | 29.0% | 50.0% | 193.5 |
| Band ±0.25, 50% caution | BTC | +37.0% | -61.5% | 0.60 | 1.09 | 35.5% | 29.0% | 50.0% | 193.5 |
| Band ±0.50, 50% caution | SPX | +15.6% | -4.9% | 3.19 | 2.58 | 27.9% | 52.4% | 45.9% | 148.0 |
| Band ±0.50, 50% caution | IWM | +20.7% | -8.2% | 2.54 | 2.12 | 27.9% | 52.4% | 45.9% | 148.0 |
| Band ±0.50, 50% caution | BTC | +36.3% | -47.2% | 0.77 | 1.18 | 27.9% | 52.4% | 45.9% | 148.0 |
| Band ±0.75, 50% caution | SPX | +12.0% | -5.1% | 2.36 | 2.20 | 21.5% | 72.0% | 42.5% | 95.0 |
| Band ±0.75, 50% caution | IWM | +15.5% | -6.9% | 2.25 | 1.80 | 21.5% | 72.0% | 42.5% | 95.0 |
| Band ±0.75, 50% caution | BTC | +26.0% | -44.6% | 0.58 | 1.03 | 21.5% | 72.0% | 42.5% | 95.0 |
| Band ±0.10, 75% caution | SPX | +21.7% | -6.1% | 3.53 | 2.89 | 42.6% | 12.3% | 54.4% | 213.5 |
| Band ±0.10, 75% caution | IWM | +27.9% | -10.0% | 2.80 | 2.32 | 42.6% | 12.3% | 54.4% | 213.5 |
| Band ±0.10, 75% caution | BTC | +39.7% | -63.3% | 0.63 | 1.07 | 42.6% | 12.3% | 54.4% | 213.5 |
| Band ±0.25, 75% caution | SPX | +21.7% | -7.3% | 2.99 | 2.82 | 35.5% | 29.0% | 57.2% | 183.8 |
| Band ±0.25, 75% caution | IWM | +27.3% | -10.0% | 2.74 | 2.21 | 35.5% | 29.0% | 57.2% | 183.8 |
| Band ±0.25, 75% caution | BTC | +38.5% | -66.4% | 0.58 | 1.05 | 35.5% | 29.0% | 57.2% | 183.8 |
| Band ±0.50, 75% caution | SPX | +18.8% | -7.3% | 2.59 | 2.42 | 27.9% | 52.4% | 59.0% | 137.0 |
| Band ±0.50, 75% caution | IWM | +23.3% | -10.0% | 2.33 | 1.93 | 27.9% | 52.4% | 59.0% | 137.0 |
| Band ±0.50, 75% caution | BTC | +38.8% | -53.8% | 0.72 | 1.08 | 27.9% | 52.4% | 59.0% | 137.0 |
| Band ±0.75, 75% caution | SPX | +16.4% | -7.6% | 2.16 | 2.09 | 21.5% | 72.0% | 60.5% | 101.5 |
| Band ±0.75, 75% caution | IWM | +19.6% | -9.3% | 2.09 | 1.64 | 21.5% | 72.0% | 60.5% | 101.5 |
| Band ±0.75, 75% caution | BTC | +32.7% | -56.6% | 0.58 | 0.96 | 21.5% | 72.0% | 60.5% | 101.5 |
| Asym -0.50/+0.25, 50% caution | SPX | +19.8% | -4.9% | 4.06 | 2.83 | 27.9% | 36.6% | 53.8% | 169.5 |
| Asym -0.50/+0.25, 50% caution | IWM | +25.3% | -8.2% | 3.10 | 2.23 | 27.9% | 36.6% | 53.8% | 169.5 |
| Asym -0.50/+0.25, 50% caution | BTC | +37.7% | -55.7% | 0.68 | 1.09 | 27.9% | 36.6% | 53.8% | 169.5 |
| Asym -0.50/+0.25, 75% caution | SPX | +20.9% | -7.3% | 2.88 | 2.54 | 27.9% | 36.6% | 62.9% | 147.8 |
| Asym -0.50/+0.25, 75% caution | IWM | +25.6% | -10.0% | 2.57 | 1.99 | 27.9% | 36.6% | 62.9% | 147.8 |
| Asym -0.50/+0.25, 75% caution | BTC | +39.3% | -58.6% | 0.67 | 1.04 | 27.9% | 36.6% | 62.9% | 147.8 |

## Candidate filter: 20–35% full-cash time, then sorted by average Calmar
| Variant | Live | Avg Calmar | Avg ann. | Avg DD | Full cash | Caution | Avg exposure | Turnover |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Asym -0.50/+0.25, 50% caution | CAUTION 50% | 2.61 | +27.6% | -22.9% | 27.9% | 36.6% | 53.8% | 169.5 |
| Band ±0.50, 50% caution | CAUTION 50% | 2.17 | +24.2% | -20.1% | 27.9% | 52.4% | 45.9% | 148.0 |
| Asym -0.50/+0.25, 75% caution | CAUTION 75% | 2.04 | +28.6% | -25.3% | 27.9% | 36.6% | 62.9% | 147.8 |
| Band ±0.50, 75% caution | CAUTION 75% | 1.88 | +27.0% | -23.7% | 27.9% | 52.4% | 59.0% | 137.0 |
| Band ±0.75, 50% caution | CAUTION 50% | 1.73 | +17.8% | -18.9% | 21.5% | 72.0% | 42.5% | 95.0 |
| Binary cash_cut -0.50 | LONG | 1.71 | +29.3% | -27.7% | 27.9% | 0.0% | 72.1% | 126.0 |
| Band ±0.75, 75% caution | CAUTION 75% | 1.61 | +22.9% | -24.5% | 21.5% | 72.0% | 60.5% | 101.5 |
| Binary cash_cut -0.75 | LONG | 1.55 | +27.5% | -30.0% | 21.5% | 0.0% | 78.5% | 108.0 |
