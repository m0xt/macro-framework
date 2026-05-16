# Research scripts

These scripts are standalone research/provenance tools. They are **not** imported by the cron path (`scripts/refresh.sh` → `src/macro_framework/build.py` → `src/macro_framework/macro_pipeline.py`). Run from the repo root with `uv run python research/<script>.py` unless a script says otherwise.

| File | Status | Notes |
|---|---|---|
| `analyze_alpha_strategies.py` | research / stale-keep | One-off strategy comparison; currently known import drift in smoke tests. |
| `analyze_drawdowns.py` | research / stale-keep | MRMI green-flip drawdown analysis by macro context. |
| `analyze_flip_conviction.py` | research / stale-keep | Flip slope/momentum/magnitude research. |
| `analyze_inflation_window.py` | research / stale-keep | Inflation Δ window parameter provenance. |
| `analyze_lag_check.py` | research / utility candidate | Release-lag validation; possible future test conversion. |
| `analyze_mrmi_baseline.py` | research / stale-keep | Pure MRMI binary historical baseline. |
| `analyze_mrmi_unified.py` | research / stale-keep | Unified MRMI performance validation; superseded by production docs. |
| `analyze_multi_signal.py` | research / stale-keep | Alternative warning-signal strategy; currently known import drift in smoke tests. |
| `analyze_position_sizing.py` | research / stale-keep | Position-sizing experiments. |
| `analyze_re_lookback.py` | research / stale-keep | Real Economy lookback parameter provenance. |
| `analyze_real_economy_conditioning.py` | research / stale-keep | Real Economy + Inflation Direction conditioning transition history. |
| `analyze_walkforward.py` | research / stale-keep | Walk-forward parameter stability; cited by `docs/architecture.md`. |
| `archive/analyze_conviction_score.py` | broken / archive | Retired Macro Seasons API; imports missing `calc_seasons_axes`; kept for history, will not reproduce. |
| `archive/analyze_seasons_conditioning.py` | broken / archive | Retired Spring/Summer/Fall/Winter model; imports missing `calc_seasons_axes`; kept for history, will not reproduce. |

## Optimization provenance

`optimization/` contains historical/manual optimization helpers: `optimize.py`, `optimize_drawdown.py`, `optimize_mrmi.py`, `optimize_stress.py`, `robustness.py`, and `validate_optimized.py`. They are useful as provenance, not production entry points.
