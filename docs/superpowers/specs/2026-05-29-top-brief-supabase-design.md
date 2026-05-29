# Top brief → Supabase (single-row table)

Date: 2026-05-29
Status: approved (design)

## Goal

Persist the weekly **top brief** ("THIS WEEK'S READ" in the dashboard hero) to
Supabase as raw Markdown, in a new table that holds exactly one row and is
overwritten on every `latest` sync. This makes the current week's read
available to remote consumers (e.g. the public site / API) alongside the
numeric `macro_snapshots` data.

## Decisions

- **Scope:** top brief only (`briefs/<date>/top.md`). Not the market/economy
  pillar briefs.
- **Replace mode:** single latest row only. The table holds exactly one row;
  each sync overwrites it. No history in the DB (git already tracks the
  per-week `briefs/<date>/` archive forever).
- **Trigger:** written during the existing Supabase sync — appended to
  `cmd_latest()` in `sync_to_supabase.py`, after the `macro_snapshots` upsert.
  Runs inside `refresh.sh`'s already-isolated Supabase step.
- **Format:** raw Markdown, stored verbatim from `top.md` (inline links and the
  trailing `Sources:` list preserved). Consumers render it; we do not store
  pre-rendered HTML.
- **Failure mode:** best-effort. If the brief upload fails after the numeric
  row already synced, log a warning and exit success — the numeric
  `macro_snapshots` row is the contract; the brief is supplementary. A brief
  hiccup never marks the sync run as failed.

## Schema

New migration `migrations/0004_macro_top_brief.sql`:

```sql
-- 0004_macro_top_brief.sql
-- Single-row table holding the current week's top brief as raw markdown.
-- Overwritten on every `sync_to_supabase latest` run.

create table if not exists macro_top_brief (
  id          smallint primary key default 1 check (id = 1),  -- single-row lock
  brief_date  date not null,        -- the brief's own date, e.g. 2026-05-27
  body_md     text not null,        -- raw markdown from briefs/<date>/top.md
  updated_at  timestamptz default now()
);

drop trigger if exists macro_top_brief_set_updated_at on macro_top_brief;
create trigger macro_top_brief_set_updated_at
before update on macro_top_brief
for each row execute function set_updated_at();

alter table macro_top_brief enable row level security;

drop policy if exists "anon read" on macro_top_brief;
create policy "anon read" on macro_top_brief
  for select to anon using (true);

insert into macro_meta (key, value)
values ('schema_version', '4')
on conflict (key) do update set value = excluded.value, updated_at = now();
```

- `set_updated_at()` already exists (migration 0001); reused, not redefined.
- RLS matches existing tables: public read, no public write.
- `id default 1 check (id = 1)` enforces the single-row invariant at the DB
  level; the writer always upserts `on_conflict="id"`.
- `brief_date` exposes which week the markdown is from. It lags the dashboard
  date by design (the brief regenerates on the weekly Tuesday cadence, so a
  Thursday dashboard build shows Tuesday's brief).

## Code changes (`src/macro_framework/sync_to_supabase.py`)

1. Bump `EXPECTED_SCHEMA_VERSION` from `3` to `4`.

2. New helper:
   ```python
   def top_brief_row() -> dict | None:
       """Build the macro_top_brief row from the newest briefs/<date>/top.md.

       Returns None if no dated brief folder or no top.md exists.
       """
       from macro_framework import build  # reuses _latest_brief_dir
       latest_dir, latest_date = build._latest_brief_dir()
       if not latest_dir:
           return None
       path = latest_dir / "top.md"
       if not path.exists():
           return None
       body = path.read_text().strip()
       if not body:
           return None
       return {"id": 1, "brief_date": latest_date, "body_md": body}
   ```

3. In `cmd_latest()`, after the existing `macro_snapshots` upsert succeeds,
   append a best-effort brief upload:
   ```python
   row = top_brief_row()
   if row is None:
       print("No top brief found; skipping macro_top_brief.")
   else:
       print(f"Upserting top brief ({row['brief_date']})...")
       try:
           client.table("macro_top_brief").upsert(row, on_conflict="id").execute()
           print("OK (top brief)")
       except Exception as exc:  # best-effort: never fail the sync on the brief
           print(f"Warning: top brief upload failed (non-fatal): {exc}",
                 file=sys.stderr)
   ```

No change to `row_from_snapshot` or `REQUIRED_MACRO_SNAPSHOTS_COLUMNS` (the
brief lives in a separate table, not `macro_snapshots`).

## Tests

- `top_brief_row()` builds the expected dict from a temp `briefs/<date>/top.md`
  (monkeypatch `build.BRIEFS_DIR`).
- Returns `None` when the briefs dir is empty / `top.md` missing / body blank.
- Update the schema-version lock to expect `4` wherever it asserts `3`.

## Docs

- `AGENTS.md`: extend the "syncs hot fields to Supabase" sentence to note the
  top brief is mirrored to a single-row `macro_top_brief` table.
- The Supabase migrations section is already generic; the new file follows the
  documented authoring steps (bump sentinel + `EXPECTED_SCHEMA_VERSION`).

## Operational apply step

`migrations/0004_macro_top_brief.sql` must be applied manually in the Supabase
SQL editor (no automated runner). If it cannot be applied from this session,
commit the migration + version bump and mark the apply step as blocked; do not
weaken preflight to make `doctor` pass.

## Out of scope (YAGNI)

- Market/economy pillar briefs in the DB.
- DB-side brief history (git covers it).
- Rendering Markdown to HTML before storage.
- Backfilling past briefs into the table.
