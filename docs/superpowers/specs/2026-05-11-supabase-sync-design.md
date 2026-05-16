# Supabase Sync for Macro Framework Indicators — Design

**Date:** 2026-05-11
**Status:** Approved, pending implementation plan

## Goal

Mirror the macro framework's computed indicators (MRMI, MMI, Real Economy
Score, etc.) to an existing Supabase project so other applications can
consume the daily regime signal without re-implementing the framework or
re-fetching upstream data sources (Yahoo Finance, FRED).

## Non-goals

- Mirroring raw Yahoo/FRED time series — downstream projects that need
  raw data should fetch directly from those sources.
- Mirroring AI briefs (`briefs/YYYY-MM-DD/*.md`) — out of scope for this
  pass; revisit if a downstream consumer asks for them.
- Replacing the existing offline-first file cache (`raw_data.pkl`,
  `snapshots/*.json`). Supabase is an additional sink, not a replacement.
- Writing back to Supabase from anywhere other than this repo.

## Architecture

```
build.py  →  .cache/raw_data.pkl        (Yahoo + FRED, 12h TTL)
          →  snapshots/<date>.json  (point-in-time)
                          │
                          ▼
              sync_to_supabase.py
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
        recompute full series      read today's snapshot
        from raw_data.pkl              │
        (reuses build.py funcs)        │
              │                       │
              └──────┬────────────────┘
                     ▼
        Supabase: macro_snapshots
        (upsert by date — idempotent)
                     │
                     ▼
        Downstream apps (anon key + RLS)
```

`build.py`, `macro_pipeline.py`, and `weekly_briefs.py` own the dashboard/brief pipeline; Supabase sync remains separate from dashboard rendering.
The sync is a separate script with no coupling to the dashboard build —
a Supabase outage cannot break the dashboard.

## Schema

Single table `macro_snapshots` with hot scalars + JSONB escape hatch.

```sql
create table macro_snapshots (
  date              date primary key,
  -- Headline (sourced from snapshot.mrmi_combined.*)
  mrmi              numeric,        -- mrmi_combined.value      (e.g. 1.02)
  mrmi_state        text check (mrmi_state in ('LONG','CASH')),
  mmi               numeric,        -- mrmi_combined.momentum   (e.g. 0.52)
  stress_intensity  numeric,        -- mrmi_combined.stress_intensity (0..1)
  macro_buffer      numeric,        -- mrmi_combined.macro_buffer
  -- Macro stress inputs (snapshot.macro.*)
  real_economy      numeric,        -- macro.real_economy_score
  inflation_dir_pp  numeric,        -- macro.inflation_dir_pp
  core_cpi_yoy_pct  numeric,        -- macro.core_cpi_yoy_pct
  -- MMI components (snapshot.components.*)
  gii_fast          numeric,        -- components.gii_fast
  breadth           numeric,        -- components.breadth
  fincon            numeric,        -- components.fincon
  -- Full point-in-time blob (today onward only; null for historical backfill)
  snapshot          jsonb,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);

create index macro_snapshots_state_idx on macro_snapshots(mrmi_state);
create index macro_snapshots_snapshot_idx on macro_snapshots using gin (snapshot);

create or replace function set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end;
$$ language plpgsql;

create trigger macro_snapshots_set_updated_at
before update on macro_snapshots
for each row execute function set_updated_at();
```

### Field-name pitfall (must not be repeated in implementation)

The snapshot JSON uses misleading legacy keys:

- `snapshot.mrmi.composite` is **the MMI value**, not the MRMI headline.
  `snapshot.mrmi.state` is a color string (`'green'` / etc), not LONG/CASH.
- `snapshot.mrmi_combined.value` is the **actual MRMI headline** (e.g. 1.02).
  `snapshot.mrmi_combined.state` is `'LONG'` or `'CASH'`.

The schema column mapping above resolves this — `mrmi` always means the
true MRMI composite. The implementation must source from `mrmi_combined`,
not from the misnamed `mrmi` block.

### Hot columns vs JSONB

The 10 scalar columns cover the values downstream apps will filter or
chart on. Everything else from the snapshot — underliers, raw macro
inputs (Sahm rule, real income YoY, etc.), MRCI sub-fields, build
metadata — lives in the JSONB column with a GIN index for path queries.

Adding new snapshot fields does not require migrations as long as they
go into JSONB. Promoting a JSONB field to a hot column is a deliberate
schema change.

## Backfill strategy

On first run (`sync_to_supabase.py backfill`):

1. Load `.cache/raw_data.pkl` (instruct user to run `build.py` first if
   missing).
2. Import compute functions from `build.py` to recompute the full daily
   history of: MMI, GII, Breadth, FinCon, Real Economy Score, Inflation
   Direction, Core CPI YoY.
3. Apply the buffer formula across history (`mrmi = mmi + macro_buffer −
   threshold` per CLAUDE.md) to derive MRMI value, `stress_intensity`,
   `macro_buffer`, and `mrmi_state` per date.
4. Build rows with the 10 hot columns populated; `snapshot` JSONB is
   null for historical rows (we do not reconstruct historical snapshot
   blobs — those only exist for dates from today forward).
5. Upsert in chunks of 500 via
   `client.table('macro_snapshots').upsert(rows, on_conflict='date')`.

Expected first-run row count: ~3,500 (matches the "Composite: 3493
valid rows" output from build.py on 2026-05-11).

The implementation must reuse `build.py`'s computation functions
directly — no reimplementation of indicator math in the sync script.
This avoids drift between dashboard and Supabase values.

## Daily update flow

`sync_to_supabase.py` (default subcommand `latest`):

1. Find most recent snapshot in `snapshots/`.
2. Read the JSON.
3. Build one row: pluck the 10 hot scalars, store the entire dict as
   the JSONB `snapshot` value.
4. Single upsert by `date`.

Optional chain into existing build flow:
```
.venv/bin/python build.py && .venv/bin/python sync_to_supabase.py latest
```

## Auth & access control

### Write side (this repo)
- `.env` at repo root (gitignored) holds:
  ```
  SUPABASE_URL=https://<project>.supabase.co
  SUPABASE_SERVICE_KEY=eyJ...
  ```
- `.env.example` committed for onboarding (no real values).
- `.gitignore` updated to include `.env`.
- Script loads via `python-dotenv`. Fails fast with a clear message if
  either variable is unset or empty.
- Service key is used for writes — bypasses RLS, never embedded in any
  client-facing artifact.
- The anon key is **not** a concern of this repo's `.env`; downstream
  apps obtain it from the Supabase dashboard and manage it themselves.

### Read side (downstream apps)
- RLS enabled on `macro_snapshots`.
- Policy: anon role gets `SELECT` on all rows. No `INSERT/UPDATE/DELETE`
  policy for anon → writes blocked by default.
- Downstream apps use the Supabase anon key (safe to embed in browser
  bundles).

```sql
alter table macro_snapshots enable row level security;
create policy "anon read" on macro_snapshots
  for select to anon using (true);
```

## Error handling

Sync script:

- Missing `SUPABASE_URL` or `SUPABASE_SERVICE_KEY` → exit 1 with
  "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env".
- `raw_data.pkl` missing on backfill → exit 1 with instruction to run
  `.venv/bin/python build.py` first.
- Latest snapshot missing on `latest` subcommand → exit 1, naming the
  directory it searched.
- Supabase HTTP error → log status code + response body, exit non-zero.
  No retry logic in v1; daily re-runs cover transient failures.
- During backfill, a chunk failure logs the offending date range and
  continues with the next chunk. The next `backfill` re-run picks up
  any gaps (upsert is idempotent).

## Idempotency

- Primary key on `date` + `on_conflict='date'` upsert: re-running on the
  same day overwrites the row cleanly.
- Backfill can be re-run safely; partial completions are fixed by
  running it again.
- The `updated_at` trigger gives a visible signal when a row was last
  refreshed without altering its date.

## Files added / changed

New files:
- `sync_to_supabase.py` — entry point with `backfill` and `latest` subcommands.
- `supabase_schema.sql` — table, indexes, trigger, RLS policy. Committed
  for reproducibility; running it against the project provisions the
  table.
- `.env.example` — credential template.
- `test_sync_to_supabase.py` — unit tests (see Testing). Placed at repo root to match the existing flat layout (`analyze_*.py`, `optimize_*.py`).
- Optional: short Supabase section in `README.md` with a downstream
  reader code snippet.

Changed:
- `.gitignore` — add `.env`.
- `requirements.txt` — add `supabase` and `python-dotenv`.

Untouched by sync-only changes: `build.py`, `macro_pipeline.py`, `weekly_briefs.py`,
`optimize.py`, all `analyze_*.py`, all `briefs/`.

## Testing

Unit tests (no network):
- `test_row_from_snapshot` — given a fixture snapshot dict, asserts the
  row builder produces the right column values and catches the
  `mrmi` vs `mrmi_combined` field-name trap (this test exists
  specifically to prevent that regression).
- `test_backfill_row_math` — given a tiny synthetic raw_data DataFrame,
  asserts the per-date MRMI/MMI/stress/buffer values match a hand-
  computed expectation.
- `test_missing_creds_exits` — patches environment, asserts
  `SystemExit` with the documented message.

Integration test (gated on env var, optional):
- Writes to a `macro_snapshots_test` table against the real Supabase,
  asserts upsert idempotency by upserting the same row twice and
  checking row count is 1, then truncates the test table.

Manual smoke:
- Run `sync_to_supabase.py latest` after a build, confirm row appears
  in Supabase dashboard with expected hot column values and a
  non-empty JSONB blob.

## Downstream usage example

```python
from supabase import create_client
client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Today's regime
row = (client.table('macro_snapshots')
              .select('date,mrmi,mrmi_state,mmi,real_economy')
              .order('date', desc=True).limit(1).execute()).data[0]

# Full history for backtesting
history = (client.table('macro_snapshots')
                  .select('date,mrmi,mrmi_state,mmi')
                  .order('date').execute()).data
```

## Open questions

None at design time. Decisions captured above; implementation can
proceed via writing-plans skill.
