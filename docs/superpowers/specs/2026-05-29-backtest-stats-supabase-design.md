# Backtest stats → Supabase (single-row table)

Date: 2026-05-29
Status: approved (design)

## Goal

Mirror the dashboard's "How well does this work historically?" backtest figures
(SPX / Russell 2000 / Bitcoin annual return, max drawdown, Calmar, plus the
average-exposure breakdown) to Supabase as a single-row table holding a JSON
blob, overwritten on every `latest` sync — same pattern as `macro_top_brief`.

## Key fact driving the design

These numbers are **not computed per build**. They are hardcoded HTML in
`build.py:684-697`, sourced from one-time Task 35 research
(`reports/task-35-investor-grade-thresholds.md`). The live engine
`backtest_production.py::backtest_signal()` can recompute them but only runs
manually, and currently yields a slightly different Calmar (~2.90 vs the
displayed 2.88).

## Decisions

- **Source:** sync the existing static figures (do NOT recompute live). Refactor
  the hardcoded HTML into a structured constant so render + sync share one
  source of truth. Displayed values and dashboard semantics are unchanged.
- **Schema:** single-row table `macro_backtest`, one `stats jsonb` column.
- **Trigger:** written during `cmd_latest()`, right after `_upsert_top_brief`.
- **Failure mode:** best-effort — warn to stderr, never fail the sync (matches
  `_upsert_top_brief`). The numeric `macro_snapshots` row stays the contract.
- **Snapshot schema:** untouched. The constant is consumed directly by both the
  renderer and the sync, so the snapshot lock tests are not affected.

## The structured constant (`build.py`)

```python
BACKTEST_STATS = {
    "window": "2017–2026",          # en dash, matches displayed text
    "leverage": "no leverage",
    "source": "reports/task-35-investor-grade-thresholds.md",
    "assets": [
        {"name": "SPX",          "annual_return_pct": 20.9, "max_drawdown_pct": -7.3,  "calmar": 2.88},
        {"name": "Russell 2000", "annual_return_pct": 25.6, "max_drawdown_pct": -10.0, "calmar": 2.57},
        {"name": "Bitcoin",      "annual_return_pct": 39.3, "max_drawdown_pct": -58.6, "calmar": 0.67},
    ],
    "avg_exposure_pct": 62.9,
    "cash_pct": 27.9,
    "caution_pct": 36.6,
}
```

`_render_backtest_card_html(stats)` rebuilds the exact current card. The render
path becomes:

```python
backtest_card_html = preview_meta.get("backtest_card_html") or _render_backtest_card_html(BACKTEST_STATS)
```

The `preview_meta` override is preserved. A lock test asserts
`_render_backtest_card_html(BACKTEST_STATS)` is **byte-identical** to the current
literal (unicode minus `−` U+2212 in drawdowns, en dash in the window, `· `
separators, `+NN.N%` returns, `Calmar N.NN`, exact indentation), guaranteeing
the dashboard output does not change.

## Schema

`migrations/0005_macro_backtest.sql`:

```sql
-- 0005_macro_backtest.sql
-- Single-row table holding the dashboard backtest stats as a JSON blob.
-- Overwritten on every `sync_to_supabase latest` run. Source of truth is the
-- static BACKTEST_STATS constant in build.py (Task 35 research figures).

create table if not exists macro_backtest (
  id          smallint primary key default 1 check (id = 1),  -- single-row lock
  stats       jsonb not null,
  updated_at  timestamptz default now()
);

drop trigger if exists macro_backtest_set_updated_at on macro_backtest;
create trigger macro_backtest_set_updated_at
before update on macro_backtest
for each row execute function set_updated_at();

alter table macro_backtest enable row level security;

drop policy if exists "anon read" on macro_backtest;
create policy "anon read" on macro_backtest
  for select to anon using (true);

insert into macro_meta (key, value)
values ('schema_version', '5')
on conflict (key) do update set value = excluded.value, updated_at = now();
```

## Code changes (`sync_to_supabase.py`)

- `EXPECTED_SCHEMA_VERSION` 4 → 5.
- `backtest_row()` → `{"id": 1, "stats": build.BACKTEST_STATS}` (lazy
  `from macro_framework import build`).
- `_upsert_backtest(client)`: best-effort upsert to `macro_backtest`
  `on_conflict="id"`; print "Upserting backtest stats..." / "OK (backtest)";
  on any exception print a stderr warning containing "non-fatal" and do not
  raise.
- `cmd_latest()` calls `_upsert_backtest(client)` immediately after
  `_upsert_top_brief(client)`.

No change to `row_from_snapshot` or `REQUIRED_MACRO_SNAPSHOTS_COLUMNS`.

## Tests

- `_render_backtest_card_html(BACKTEST_STATS)` equals the captured current
  literal exactly (byte-identical lock).
- `backtest_row()` returns `{"id": 1, "stats": <BACKTEST_STATS>}`.
- `_upsert_backtest` writes the row with `on_conflict="id"`; best-effort on a
  simulated missing table (no raise, "non-fatal" on stderr). Reuse the
  `FakeQuery`/`FakeClient` pattern, extended for `macro_backtest`.

## Docs

- `AGENTS.md`: extend the "What this does" sentence to also mention the backtest
  stats single-row `macro_backtest` table.

## Operational apply step

`migrations/0005_macro_backtest.sql` applied manually in the Supabase SQL editor;
then `doctor` must report schema version 5. If unappliable from session, commit
migration + bump and mark blocked; do not weaken preflight.

## Out of scope (YAGNI)

- Live recomputation of the backtest each build.
- Fixing the pre-existing Calmar-drift smoke test.
- Per-asset flat columns (chose a single JSONB blob).
- Embedding backtest stats in the snapshot JSON.
