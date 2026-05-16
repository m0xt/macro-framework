# Repo map

This is the agent-facing ownership map for `macro-framework`. The active production path is `scripts/refresh.sh` → `build.py --no-cache` → `sync_to_supabase.py latest` → commit `briefs/`, `outputs/dashboard.html`, and `snapshots/`.

## Active production files

| Path | Status | Notes |
|---|---|---|
| `AGENTS.md` | active | Canonical agent front door. |
| `CLAUDE.md` | active | One-line `@AGENTS.md` import. |
| `README.md` | active | Human front door only. |
| `DECISIONS.md` | active | Append-only why-log for skeleton deviations and parameter decisions. |
| `build.py` | active | Main dashboard build entry point. Fetches data, computes indicators, writes snapshot, renders `outputs/dashboard.html`, refreshes stale briefs. |
| `macro_pipeline.py` | active | Production Yahoo/FRED fetch, indicator math, MRMI formula, chart payload, snapshot schema. |
| `weekly_briefs.py` | active | Claude CLI market/economy/top weekly brief generation. |
| `sync_to_supabase.py` | active | Supabase doctor/latest/backfill sync; owns schema preflight and error taxonomy. |
| `scripts/refresh.sh` | active | LaunchAgent cron path and ops-wrapper integration. |
| `scripts/com.milkroad.macro-refresh.plist` | active | Tuesday 11:00 Prague pre-meeting refresh template. |
| `scripts/com.milkroad.macro-refresh-daily.plist` | active | Mon-Fri 22:30 Prague after-close refresh template. |
| `scripts/setup-mac-mini.sh` | active | Mac mini launchd bootstrap. |
| `supabase_schema.sql` | active | Remote Supabase schema contract; version must match `EXPECTED_SCHEMA_VERSION`. |
| `.env.example` | active | Safe committed env template; never add real secrets. |
| `pyproject.toml` | active | uv project metadata plus pytest/ruff/pyright config. |
| `uv.lock` | active | Locked uv dependency graph. |
| `requirements.txt` | compatibility | pip/venv fallback while uv is the primary path. |
| `.gitignore` | active | Keeps local caches/secrets out, while intentionally tracking selected output history. |
| `.claudeignore` | active | Context-filter hints for Claude-style tooling. |
| `LICENSE` | active | Project license. |

## Tests

| Path | Status | Notes |
|---|---|---|
| `tests/test_smoke.py` | active | Production imports, entrypoint guards, weekly-brief dry run, MRMI formula/parameter/release-lag locks, snapshot schema. |
| `tests/test_supabase_sync.py` | active | Supabase preflight, schema drift, missing columns, and refresh fail-soft behavior. |
| `test_sync_to_supabase.py` | compatibility | Legacy/root Supabase tests retained for now; can be consolidated later. |

## Human docs and durable artifacts

| Path | Status | Notes |
|---|---|---|
| `docs/architecture.md` | active | Human technical narrative for MRMI, pipeline, cron, integrations. |
| `docs/PRESENTATION.html` | active | Moved shareable presentation; future projects should model this durable `docs/PRESENTATION.html` shape. |
| `presentation.html` | tombstone | Compatibility pointer to `docs/PRESENTATION.html`; remove in later cleanup. |
| `GUIDE.md` | active legacy | Long-form dashboard/investment-thesis explanation; not the agent front door. |
| `MACRO_FRAMEWORK_ROADMAP.md` | active legacy | Future ideas/backlog, including cadence improvements and release-calendar work. |
| `docs/superpowers/plans/2026-05-11-supabase-sync.md` | historical plan | Supabase sync implementation plan. |
| `docs/superpowers/specs/2026-05-11-supabase-sync-design.md` | historical spec | Supabase sync design/provenance. |
| `reports/macro_update_2026_05.html` | active artifact | Shareable monthly report kept tracked pending output-home decision. |
| `briefs/YYYY-MM-DD/*.md` | active artifact | Weekly Claude brief archive, intentionally tracked. |
| `outputs/dashboard.html` | active latest deliverable | Current generated dashboard, intentionally tracked and overwritten each run. |
| `snapshots/YYYY-MM-DD.json` | active history | Point-in-time snapshots, intentionally tracked with retention policy. |

## Agent docs

| Path | Status | Notes |
|---|---|---|
| `agent_docs/repo_map.md` | active | This file. |
| `agent_docs/dispatch_runbook.md` | active | Common Bob dispatch workflows. |
| `agent_docs/cron_failure_recovery.md` | active | Failure taxonomy and recovery steps. |
| `agent_docs/secrets.md` | active | Supabase secret contract and rotation runbook. |

## Monthly report tools

| Path | Status | Notes |
|---|---|---|
| `build_report.py` | utility | Markdown-to-HTML monthly report builder; not cron path. |
| `generate_report_charts.py` | utility | Report chart generation; not cron path. |

## Backtest / optimization utilities

| Path | Status | Notes |
|---|---|---|
| `backtest_production.py` | utility | Produces presentation/report backtest numbers; manual only. |
| `optimize.py` | utility | Parameter grid search and backtesting CLI. |
| `optimize_drawdown.py` | research | Drawdown-focused optimization history. |
| `optimize_mrmi.py` | research | MRMI optimization history. |
| `optimize_stress.py` | research | Macro-stress optimization history. |
| `robustness.py` | utility | Walk-forward/benchmark robustness checks. |
| `validate_optimized.py` | utility | Validation helper for optimized parameters. |

## `analyze_*.py` triage

No `analyze_*.py` file is part of the active cron/dashboard path: none are called by `scripts/refresh.sh`, `build.py`, or `macro_pipeline.py`; all are standalone scripts with `if __name__ == "__main__"` guards. There are 14 current `analyze_*.py` files.

| File | Status | Notes |
|---|---|---|
| `analyze_alpha_strategies.py` | research / stale-keep | One-off strategy comparison (buy-and-hold, MRMI variants, regime vetoes). Keep as provenance until research archive exists. Currently xfailed in smoke tests because imports drifted. |
| `analyze_conviction_score.py` | broken / archive-candidate | Imports missing `calc_seasons_axes` and fails to import; tied to retired Macro Seasons APIs. See `~/ops/AUDIT-MACRO-FRAMEWORK.md`. |
| `analyze_drawdowns.py` | research / stale-keep | MRMI green-flip drawdown analysis by macro context. Useful risk-claim provenance, not active. |
| `analyze_flip_conviction.py` | research / stale-keep | Tests flip slope/momentum/magnitude. Not active. |
| `analyze_inflation_window.py` | research / stale-keep | Parameter research for inflation Δ windows. Keep until provenance is folded into docs/tests. |
| `analyze_lag_check.py` | research / utility candidate | Validates release-lag adjustment; conceptually important, possible future test conversion. |
| `analyze_mrmi_baseline.py` | research / stale-keep | Pure MRMI binary baseline; historical benchmark. |
| `analyze_mrmi_unified.py` | research / stale-keep | Validates unified MRMI performance; superseded by production backtest docs. |
| `analyze_multi_signal.py` | research / stale-keep | Alternative warning-signal strategy research. Currently xfailed in smoke tests because imports drifted. |
| `analyze_position_sizing.py` | research / stale-keep | Position-sizing experiments. Not active. |
| `analyze_re_lookback.py` | research / stale-keep | Real Economy lookback parameter research. Keep as parameter provenance. |
| `analyze_real_economy_conditioning.py` | research / stale-keep | Compares Real Economy + Inflation Direction conditioning vs old seasons. Useful transition history. |
| `analyze_seasons_conditioning.py` | broken / archive-candidate | Imports missing `calc_seasons_axes`, fails to import, and is tied to retired Spring/Summer/Fall/Winter model. See `~/ops/AUDIT-MACRO-FRAMEWORK.md`. |
| `analyze_walkforward.py` | research / stale-keep | Walk-forward parameter stability check; cited by `docs/architecture.md` for parameter provenance. |

## Generated/local-only caches

| Path | Status | Notes |
|---|---|---|
| `.cache/raw_data.pkl` | local cache | Data cache, not committed. |
| `.cache/` | ignored runtime | Fully gitignored local cache/log directory. |
| `.cache/launchd-refresh*.log` | local logs | Launchd stdout/stderr logs, not committed. |
| `.cache/status.json` | local status | Refresh status written by ops wrapper. |
| `.cache/presentation.html` | ignored relic | Local duplicate if present; tracked presentation now lives at `docs/PRESENTATION.html`. |
