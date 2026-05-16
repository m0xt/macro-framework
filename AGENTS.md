# macro-framework

## What this does

`macro-framework` ingests Yahoo/FRED macro and market data, computes the MRMI regime signal from market momentum plus macro stress (growth impulse, financial conditions, sector breadth, macro context, stress buffer), writes daily snapshots and a self-contained dashboard, syncs hot fields to Supabase, and lazily refreshes three Claude-generated weekly briefs on the first successful build on/after Tuesday.

## Repo map

| Path | Purpose |
|---|---|
| `build.py` | Main dashboard build: data fetch, indicator compute, snapshot write, brief refresh, HTML render. |
| `macro_pipeline.py` | Production data fetch, indicator math, MRMI formula, chart payload, snapshot schema. |
| `weekly_briefs.py` | Claude CLI weekly market/economy/top brief generator. |
| `sync_to_supabase.py` | Supabase doctor/latest/backfill sync with schema-version preflight. |
| `scripts/refresh.sh` | LaunchAgent refresh entry point via `~/ops/lib/cron-wrapper.sh`. |
| `scripts/com.milkroad.macro-refresh*.plist` | Tuesday pre-meeting and weekday end-of-close launchd jobs. |
| `supabase_schema.sql` | Remote schema contract; version must match `EXPECTED_SCHEMA_VERSION`. |
| `tests/test_smoke.py` | Import/entrypoint smoke tests and MRMI parameter/invariant locks. |
| `tests/test_supabase_sync.py` | Supabase preflight/failure-isolation tests. |
| `test_sync_to_supabase.py` | Legacy/root Supabase tests kept for compatibility. |
| `briefs/` | Git-tracked weekly Claude brief archive. |
| `.cache/dashboard.html` | Current generated dashboard, tracked for review. |
| `.cache/snapshots/` | Git-tracked point-in-time JSON snapshots; see `DECISIONS.md`. |
| `docs/PRESENTATION.html` | Shareable human explainer; moved from top-level `presentation.html`. |
| `docs/architecture.md` | Human technical narrative and MRMI provenance. |
| `agent_docs/` | Agent-facing runbooks, repo map, cron recovery, secrets contract. |
| `analyze_*.py` | Standalone research/provenance scripts; full triage in `agent_docs/repo_map.md`. |
| `optimize*.py`, `robustness.py`, `validate_optimized.py` | Manual optimization/backtest utilities, not cron path. |
| `backtest_production.py` | Manual backtest numbers used by presentation/report docs. |
| `build_report.py`, `generate_report_charts.py` | Monthly report tooling, not cron path. |
| `reports/` | Tracked monthly report artifact; output-home decision deferred. |
| `GUIDE.md`, `MACRO_FRAMEWORK_ROADMAP.md` | Long-form guide and future ideas. |

## How to run

- Install/update deps: `uv sync --extra dev`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Build dashboard from cache: `uv run python build.py`
- Force fresh data: `uv run python build.py --no-cache`
- Open after build: `uv run python build.py --open`
- Force briefs: `uv run python weekly_briefs.py --force`
- Supabase preflight: `uv run python sync_to_supabase.py doctor`
- Supabase latest sync: `uv run python sync_to_supabase.py latest`
- Cron path: `scripts/refresh.sh`

## Conventions

- Python style/tooling is encoded in `pyproject.toml` (`ruff`, lenient `pyright`, `pytest`). Do not restate formatting rules in docs.
- Keep the flat root-module layout until a dedicated `src/` migration dispatch.
- Do not change MRMI math, constants, release lags, or dashboard semantics without updating `docs/architecture.md`, `DECISIONS.md` when relevant, and the lock tests.
- Brief cadence is lazy weekly Tuesday: the first successful build on/after Tuesday regenerates stale briefs; later builds skip until the next Tuesday cutoff.
- Supabase failures are isolated from local dashboard/snapshot commits by `scripts/refresh.sh`.

## Testing

- Fast gate: `uv run pytest`.
- Lint gate: `uv run ruff check .`.
- Smoke tests cover production imports and dry-run entry points.
- MRMI tests lock formula invariants, stress clipping, release lags, snapshot schema, and documented parameter drift.
- Sector Breadth `LOOKBACK = 90` is intentional and locked after the 2026-05-15 reconciliation; do not revert to stale 63-day docs.

## Security

- Required Supabase vars: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
- Target secret location: `~/ops/secrets/macro-framework/.env` under git-crypt.
- Current state: code still reads project-root `.env` or process environment via `python-dotenv`; ops-secret migration is pending.
- Never commit real `.env` or service-role keys. `.env.example` is the only committed template.
- Full contract: `agent_docs/secrets.md`.

## When something breaks

Start with `agent_docs/cron_failure_recovery.md`, then use `agent_docs/dispatch_runbook.md` for task-specific workflows. If recovery is unsafe or unclear, write an incident note under `~/ops/incidents/` and stop before changing production math or forcing pushes.
