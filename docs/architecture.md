# Architecture

`macro-framework` is a macro-regime dashboard and data pipeline. It ingests Yahoo Finance and FRED data, computes market and economy indicators, writes daily JSON snapshots, renders `.cache/dashboard.html`, optionally syncs hot fields to Supabase, and refreshes three Claude-generated weekly briefs on a lazy Tuesday cadence.

## MRMI formula

MRMI (Milk Road Macro Index) is the headline LONG/CASH signal. It combines fast market momentum with a slow macro-stress buffer:

```text
Stress_intensity = min(1, max(0, -Real_Economy) * max(0, Inflation_Direction))
Macro_buffer     = buffer_size * (1 - Stress_intensity)   # buffer_size=1.0
MRMI             = MMI + Macro_buffer - threshold          # threshold=0.5

MRMI > 0 -> LONG
MRMI < 0 -> CASH
```

- `MMI` is the equal-weighted Market Momentum Index: Growth Impulse Index, Sector Breadth, and Financial Conditions.
- `Real_Economy` is an equal-weighted z-score of real PCE YoY, Sahm Rule inverted, real personal income YoY, and Atlanta Fed GDPNow.
- `Inflation_Direction` is the 6-month change in core CPI YoY, in percentage points.
- `stress_intensity` is clipped to `[0, 1]`; the dashboard `stress_on` flag fires when intensity is above 0.5.
- The default `buffer_size=1.0` and `threshold=0.5` live in `macro_pipeline.py` and are locked by `tests/test_smoke.py`.

The buffer is intentionally pro-risk by default: MMI weakness alone is not enough to trigger CASH unless macro stress also builds. This is why MMI standalone can outperform MRMI in calm periods; the buffer is insurance against false market alarms and stagflation-style drawdowns.

### Parameter provenance

- Sector Breadth uses `lookback=90` over 90 days. Production had already used that value since commit `9f124cf`; the 2026-05-15 safety dispatch reconciled stale docs/tests to code instead of changing math.
- Financial Conditions uses a 252-day lookback across VIX, MOVE, and high-yield spreads.
- GII uses `fast_roc=21`, `slow_roc=126`, `z_len=504`, fast-composite mode.
- Macro context applies release lags by default: PCE/RPI 60d, unemployment 35d, Core CPI 45d, GDPNow 0d.
- `analyze_walkforward.py`, `analyze_re_lookback.py`, `analyze_inflation_window.py`, `optimize.py`, and `backtest_production.py` preserve the research trail behind the current parameter set. They are not cron entry points.

## Indicator pipeline

1. `build.py` calls `macro_pipeline.fetch_all_data()`.
2. `fetch_all_data()` downloads Yahoo Finance series and FRED CSV series, then writes/reads `.cache/raw_data.pkl` for the 12-hour cache window unless `--no-cache` is used.
3. `macro_pipeline.py` computes:
   - `calc_growth_impulse()` for GII.
   - `calc_financial_conditions()` for FinCon.
   - `calc_sector_breadth()` for cyclical sector breadth.
   - `calc_composite()` for MMI.
   - `calc_macro_context()` for release-lagged real economy and inflation context.
   - `calc_milk_road_macro_index()` for MRMI, macro buffer, and stress intensity.
4. `save_snapshot()` writes `.cache/snapshots/YYYY-MM-DD.json` with the current MRMI, components, macro fields, underliers, and full nested snapshot.
5. `prepare_chart_data()` serializes dashboard chart payloads for `build.py`.
6. `build.py` embeds the payload and briefs into `.cache/dashboard.html`.
7. `sync_to_supabase.py latest` converts the newest snapshot into one `macro_snapshots` row for downstream apps.

## Dashboard structure

The dashboard is a four-step walkthrough wrapped by a hero:

1. Hero: headline MRMI value, LONG/CASH state, scale bar, pillar states, and the top weekly brief.
2. MRMI history: regime shading plus SPX/Russell/BTC overlays.
3. Market pillar: MMI history, weekly market brief, and GII/Breadth/FinCon driver cards.
4. Economy pillar: Real Economy Score and Inflation Direction chart, weekly economy brief, and driver cards.
5. Reference library: supplementary indicators kept for context and future promotion candidates.

The retired Macro Seasons/Spring/Summer/Fall/Winter model should not be reintroduced into new briefs or docs. The current vocabulary is MRMI, MMI, Macro Stress, growth, and inflation direction.

## Cron path

`launchd` runs `scripts/refresh.sh` through two checked-in plist templates:

- `scripts/com.milkroad.macro-refresh.plist`: Tuesday 11:00 Prague, before the research meeting.
- `scripts/com.milkroad.macro-refresh-daily.plist`: Monday-Friday 22:30 Prague, after the US close.

`refresh.sh` does the end-to-end production path:

1. Source `~/ops/lib/cron-wrapper.sh`.
2. `cron_wrapper_pull` to fast-forward the repo.
3. Run `build.py --no-cache`.
4. Run `sync_to_supabase.py latest`.
5. Commit tracked outputs: `briefs/`, `.cache/dashboard.html`, and `.cache/snapshots/`.
6. Write `.cache/status.json` through the ops wrapper.

Supabase failures are fail-soft: if the local dashboard build succeeds but sync fails with `supabase-auth`, `supabase-network`, or `supabase-schema-drift`, `refresh.sh` still commits local deliverables and records `refresh ok, supabase sync failed (<type>)`.

Weekly briefs are not strict “only Tuesdays.” `weekly_briefs.py` implements lazy Tuesday freshness: a brief is stale if the latest dated archive containing that brief is older than the most recent Tuesday on or before today. Therefore the first successful build on or after Tuesday regenerates the week’s briefs; later builds skip until the next Tuesday cutoff unless forced.

## External integrations

### Yahoo Finance and FRED

Yahoo Finance supplies market/ETF/commodity/volatility inputs through `yfinance`. FRED series are read via public CSV endpoints; no FRED API key is required. Transient failures usually surface during `fetch_all_data()` or cache refresh.

### Supabase

`sync_to_supabase.py` requires `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. Before writing, it validates:

- `macro_meta` contains the expected schema sentinel.
- Remote version matches `EXPECTED_SCHEMA_VERSION`.
- `macro_snapshots` exposes every required hot column.

`supabase_schema.sql` is the checked-in contract. Apply it remotely before running `doctor`, `latest`, or `backfill`. Current known blocker: a remote missing `public.macro_meta` fails `doctor` with `supabase-schema-drift` until the SQL is applied.

### Claude CLI

`weekly_briefs.py` subprocess-calls the `claude` CLI. It uses the Claude Code subscription; there is no Anthropic SDK dependency and no `ANTHROPIC_API_KEY` requirement. Missing CLI/auth or timeouts affect brief generation, not raw indicator math.
