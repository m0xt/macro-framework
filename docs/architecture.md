# Architecture

`macro-framework` is a macro-regime dashboard and data pipeline. It ingests Yahoo Finance, FRED CSV, and selected supplementary sources, computes market and economy indicators, writes daily JSON snapshots, renders `outputs/dashboard.html`, optionally syncs hot fields to Supabase, and refreshes three Claude-generated weekly briefs on a lazy Tuesday cadence.

## MRMI formula

MRMI (Milk Road Macro Index) is the headline allocation posture index. It combines fast market momentum with a slow macro-stress buffer:

```text
g                = max(0, -Real_Economy)
i                = max(0, Inflation_Direction)
Stress_raw       = 0.75*g + 0.50*i + 10*g*i
Stress_intensity = clip(Stress_raw / stress_p99, 0, 1)     # stress_p99=10.0083
Stress_score     = 10 * Stress_intensity                   # 0–10 dashboard score
Macro_buffer     = buffer_size * (1 - Stress_intensity)    # buffer_size=0.5
MRMI             = MMI + Macro_buffer - threshold          # threshold=0.75

MRMI < -0.50 -> CASH (0% exposure)
-0.50 <= MRMI <= +0.25 -> CAUTION (75% exposure)
MRMI > +0.25 -> LONG (100% exposure)
```

- `MMI` is the equal-weighted Market Momentum Index: Growth Impulses, Sector Breadth, and Financial Conditions.
- `Real_Economy` is an equal-weighted z-score of real PCE YoY, Sahm Rule inverted, real personal income YoY, and Atlanta Fed GDPNow.
- `Inflation_Direction` is the 6-month change in core CPI YoY, in percentage points.
- `stress_intensity` is clipped to `[0, 1]`; `stress_score` is the same signal shown on a 0–10 dashboard scale with fixed buckets: CALM < 3, WATCH 3–5, BUILDING 5–7, ELEVATED >= 7.
- The default `buffer_size=0.5`, `threshold=0.75`, and `stress_p99=10.0083` live in `src/macro_framework/macro_pipeline.py` and are locked by `tests/test_smoke.py`.

The buffer is intentionally pro-risk by default: MMI weakness alone is not enough to trigger CASH unless macro stress also builds. This is why MMI standalone can outperform MRMI in calm periods; the buffer is insurance against false market alarms and stagflation-style drawdowns. The posture layer is investor-grade rather than binary: CAUTION keeps 75% exposure between the CASH and LONG thresholds.

### Parameter provenance

- Sector Breadth uses `lookback=90` over 90 days. Production had already used that value since commit `9f124cf`; the 2026-05-15 safety dispatch reconciled stale docs/tests to code instead of changing math.
- Financial Conditions uses a 252-day lookback across VIX, MOVE, and high-yield spreads.
- Growth Impulses uses `fast_roc=21`, `slow_roc=126`, `z_len=504`, fast-composite mode.
- Macro context applies release lags by default: PCE/RPI 60d, unemployment 35d, Core CPI 45d, GDPNow 0d.
- `research/analyze_walkforward.py`, `research/analyze_re_lookback.py`, `research/analyze_inflation_window.py`, `research/optimization/optimize.py`, and `src/macro_framework/backtest_production.py` preserve the research trail behind the current parameter set. They are not cron entry points.

## Indicator pipeline

1. `src/macro_framework/build.py` calls `macro_framework.macro_pipeline.fetch_all_data()`.
2. `fetch_all_data()` downloads Yahoo Finance series, FRED CSV series, and supplementary DBnomics ISM PMI data, then writes/reads `.cache/raw_data.pkl` for the 12-hour cache window unless `--no-cache` is used.
3. `src/macro_framework/macro_pipeline.py` computes:
   - `calc_growth_impulse()` for Growth Impulses.
   - `calc_financial_conditions()` for FinCon.
   - `calc_sector_breadth()` for cyclical sector breadth.
   - `calc_composite()` for MMI.
   - `calc_macro_context()` for release-lagged real economy and inflation context.
   - `calc_milk_road_macro_index()` for MRMI, macro buffer, stress intensity, 0–10 stress score, posture, and exposure.
4. `save_snapshot()` writes `snapshots/YYYY-MM-DD.json` with the current MRMI, components, macro fields, drill-down payloads, underliers, and full nested snapshot.
5. `prepare_chart_data()` serializes dashboard chart payloads for `src/macro_framework/build.py`.
6. `src/macro_framework/build.py` embeds the payload and briefs into `outputs/dashboard.html`.
7. `python -m macro_framework.sync_to_supabase latest` converts the newest snapshot into one `macro_snapshots` row for downstream apps.

## Dashboard structure

The dashboard is a four-step walkthrough wrapped by a hero:

1. Hero: headline MRMI value, LONG/CAUTION/CASH posture, exposure weight, subtle scale bar, pillar states, and the top weekly brief.
2. MRMI history: LONG / CAUTION / CASH regime shading, strengthened CAUTION band, range tabs, and SPX/Russell/BTC/MMI overlays.
3. Market pillar: MMI history, weekly market brief, and an open MMI driver scorecard for Growth Impulses, Sector Breadth, and Financial Conditions.
4. Economy pillar: Macro Stress 0–10 history, Real Economy Score + Inflation Direction input chart, weekly economy brief, and real-economy driver cards.
5. Reference Library: supplementary context indicators with expandable charts.

The MMI driver rows expand in place below the matching driver chart. Each driver has a deterministic mini-brief, an input table sorted by absolute current z-score, tooltip-backed input explanations, 7d/30d z-score deltas, and a raw input history chart selectable by dropdown or row click. The current table column order is Input / Group / Current z / 7d zΔ / 30d zΔ.

The Reference Library is not part of the headline math. It currently includes liquidity (US M2), activity (ISM Manufacturing PMI via DBnomics, GDPNow, CFNAI, Industrial Production, Housing Starts, Building Permits), inflation (official headline CPI, official core CPI, official PPI all commodities), and labor (initial/continuing claims). ISM Manufacturing PMI charts recovered monthly observation points and filters DBnomics' suspicious 2025 low-teens tail until a cleaner official feed is available.

The retired Macro Seasons/Spring/Summer/Fall/Winter model should not be reintroduced into new briefs or docs. The current vocabulary is MRMI, MMI, Macro Stress, growth, inflation direction, and Reference Library.

## Cron path

`launchd` runs `scripts/refresh.sh` through two checked-in plist templates:

- `scripts/com.milkroad.macro-refresh.plist`: Tuesday 11:00 Prague, before the research meeting.
- `scripts/com.milkroad.macro-refresh-daily.plist`: Monday-Friday 22:30 Prague, after the US close.

`refresh.sh` does the end-to-end production path:

1. Source `~/ops/lib/cron-wrapper.sh`.
2. `cron_wrapper_pull` to fast-forward the repo.
3. Run `python -m macro_framework.build --no-cache`.
4. Run `python -m macro_framework.sync_to_supabase latest`.
5. Commit tracked outputs: `briefs/`, `outputs/dashboard.html`, and `snapshots/`.
6. Write `.cache/status.json` through the ops wrapper.

Supabase failures are fail-soft: if the local dashboard build succeeds but sync fails with `supabase-auth`, `supabase-network`, or `supabase-schema-drift`, `refresh.sh` still commits local deliverables and records `refresh ok, supabase sync failed (<type>)`.

Weekly briefs are not strict “only Tuesdays.” `src/macro_framework/weekly_briefs.py` implements lazy Tuesday freshness: a brief is stale if the latest dated archive containing that brief is older than the most recent Tuesday on or before today. Therefore the first successful build on or after Tuesday regenerates the week’s briefs; later builds skip until the next Tuesday cutoff unless forced.

## External integrations

### Yahoo Finance, FRED, and DBnomics

Yahoo Finance supplies market/ETF/commodity/volatility inputs through `yfinance`. FRED series are read via public CSV endpoints; no FRED API key is required. DBnomics supplies the ISM Manufacturing PMI mirror because FRED's legacy NAPM CSV endpoint is unavailable. Transient failures usually surface during `fetch_all_data()` or cache refresh.

### Supabase

`src/macro_framework/sync_to_supabase.py` requires `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. Before writing, it validates:

- `macro_meta` contains the expected schema sentinel.
- Remote version matches `EXPECTED_SCHEMA_VERSION`.
- `macro_snapshots` exposes every required hot column.

The ordered files under `migrations/` are the checked-in contract: `0001_init_macro_snapshots.sql` creates the table/trigger/RLS, `0002_macro_meta.sql` adds the `macro_meta` sentinel, and later migrations expand the three-state MRMI posture/exposure fields. Apply them in order in the Supabase SQL editor before running `doctor`, `latest`, or `backfill`.

### Claude CLI

`src/macro_framework/weekly_briefs.py` subprocess-calls the `claude` CLI. It uses the Claude Code subscription; there is no Anthropic SDK dependency and no `ANTHROPIC_API_KEY` requirement. Missing CLI/auth or timeouts affect brief generation, not raw indicator math. Current prompts target plain-English meeting prep for non-macro colleagues; the generated top brief appears in the hero, with market/economy briefs under their pillar charts.
