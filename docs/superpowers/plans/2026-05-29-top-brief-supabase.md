# Top Brief → Supabase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror the weekly top brief (`briefs/<date>/top.md`) to Supabase as raw Markdown in a new single-row `macro_top_brief` table, overwritten on every `latest` sync.

**Architecture:** A new SQL migration adds the single-row table (DB-level lock via `id check (id = 1)`). `sync_to_supabase.py` gains a `top_brief_row()` reader (reuses `build._latest_brief_dir()`) and a best-effort `_upsert_top_brief(client)` helper that `cmd_latest()` calls after the numeric `macro_snapshots` upsert. A brief failure logs a warning and never fails the sync.

**Tech Stack:** Python 3.12, `supabase-py`, pytest, Supabase Postgres + RLS.

**Spec:** `docs/superpowers/specs/2026-05-29-top-brief-supabase-design.md`

> **Tooling note:** `uv` is not on PATH in this environment. Run Python via the repo venv: `PYTHONPATH=src .venv/bin/python ...` and pytest via `.venv/bin/python -m pytest`. If `uv` is later installed, the documented `uv run ...` forms work identically.

---

### Task 1: Add the `macro_top_brief` migration

**Files:**
- Create: `migrations/0004_macro_top_brief.sql`

- [ ] **Step 1: Write the migration SQL**

Create `migrations/0004_macro_top_brief.sql` with exactly:

```sql
-- 0004_macro_top_brief.sql
-- Single-row table holding the current week's top brief as raw markdown.
-- Overwritten on every `sync_to_supabase latest` run. History is preserved in
-- git under briefs/<date>/, not in the database.

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

- [ ] **Step 2: Verify it is well-formed and consistent with conventions**

Run: `ls migrations/ && tail -5 migrations/0004_macro_top_brief.sql`
Expected: file is the highest-numbered migration; ends with the `schema_version` upsert to `'4'`. (`set_updated_at()` and the `anon read` policy pattern are reused from `0001_init_macro_snapshots.sql` — do not redefine the function.)

- [ ] **Step 3: Commit**

```bash
git add migrations/0004_macro_top_brief.sql
git commit -m "feat(supabase): add macro_top_brief single-row table migration"
```

---

### Task 2: `top_brief_row()` reader

**Files:**
- Modify: `src/macro_framework/sync_to_supabase.py`
- Test: `tests/test_supabase_sync.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_supabase_sync.py`:

```python
def test_top_brief_row_reads_latest_top_md(tmp_path, monkeypatch):
    from macro_framework import build

    briefs = tmp_path / "briefs"
    (briefs / "2026-05-20").mkdir(parents=True)
    (briefs / "2026-05-20" / "top.md").write_text("old brief\n")
    (briefs / "2026-05-27").mkdir(parents=True)
    (briefs / "2026-05-27" / "top.md").write_text("The dashboard is parked at CAUTION.\n")
    monkeypatch.setattr(build, "BRIEFS_DIR", briefs)

    row = sync_to_supabase.top_brief_row()
    assert row == {
        "id": 1,
        "brief_date": "2026-05-27",
        "body_md": "The dashboard is parked at CAUTION.",
    }


def test_top_brief_row_none_when_no_briefs(tmp_path, monkeypatch):
    from macro_framework import build

    monkeypatch.setattr(build, "BRIEFS_DIR", tmp_path / "briefs")
    assert sync_to_supabase.top_brief_row() is None


def test_top_brief_row_none_when_top_md_missing(tmp_path, monkeypatch):
    from macro_framework import build

    briefs = tmp_path / "briefs"
    (briefs / "2026-05-27").mkdir(parents=True)
    (briefs / "2026-05-27" / "market.md").write_text("only a pillar brief\n")
    monkeypatch.setattr(build, "BRIEFS_DIR", briefs)
    assert sync_to_supabase.top_brief_row() is None


def test_top_brief_row_none_when_body_blank(tmp_path, monkeypatch):
    from macro_framework import build

    briefs = tmp_path / "briefs"
    (briefs / "2026-05-27").mkdir(parents=True)
    (briefs / "2026-05-27" / "top.md").write_text("   \n\n")
    monkeypatch.setattr(build, "BRIEFS_DIR", briefs)
    assert sync_to_supabase.top_brief_row() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_supabase_sync.py -k top_brief_row -v`
Expected: FAIL — `AttributeError: module 'macro_framework.sync_to_supabase' has no attribute 'top_brief_row'`

- [ ] **Step 3: Implement `top_brief_row()`**

In `src/macro_framework/sync_to_supabase.py`, add this function directly above `def cmd_latest()` (which is near line 284):

```python
def top_brief_row() -> dict[str, Any] | None:
    """Build the macro_top_brief row from the newest briefs/<date>/top.md.

    Returns None if there is no dated brief folder, no top.md, or a blank body.
    Reuses build._latest_brief_dir() so the brief-locating logic lives in one place.
    """
    from macro_framework import build  # reuses _latest_brief_dir + BRIEFS_DIR

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

(`Any` is already imported at the top of the module via `from typing import Any`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_supabase_sync.py -k top_brief_row -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/macro_framework/sync_to_supabase.py tests/test_supabase_sync.py
git commit -m "feat(supabase): add top_brief_row reader for macro_top_brief"
```

---

### Task 3: Best-effort `_upsert_top_brief` + wire into `cmd_latest`, bump schema version

**Files:**
- Modify: `src/macro_framework/sync_to_supabase.py` (`EXPECTED_SCHEMA_VERSION` near line 33; `cmd_latest` near line 284)
- Modify: `tests/test_supabase_sync.py` (extend `FakeQuery`/`FakeClient`)

- [ ] **Step 1: Extend the fakes and write the failing tests**

In `tests/test_supabase_sync.py`, replace the `FakeQuery.execute` method (currently ends its `macro_snapshots` branch then `raise RuntimeError(f"relation {self.table} does not exist")`) so it also handles `macro_top_brief`:

```python
    def execute(self) -> SimpleNamespace:
        if self.table == "macro_meta":
            return SimpleNamespace(data=[{"key": "schema_version", "value": str(self.client.schema_version)}])
        if self.table == "macro_snapshots":
            if self.payload is not None:
                return SimpleNamespace(data=[self.payload])
            requested = {col.strip() for col in self.selected.split(",") if col.strip()}
            missing = requested - self.client.columns
            if missing:
                raise RuntimeError(f"column {sorted(missing)[0]} does not exist")
            return SimpleNamespace(data=[])
        if self.table == "macro_top_brief":
            if not self.client.brief_table_exists:
                raise RuntimeError("relation macro_top_brief does not exist")
            self.client.brief_upserts.append(self.payload)
            return SimpleNamespace(data=[self.payload])
        raise RuntimeError(f"relation {self.table} does not exist")
```

In `FakeClient.__init__`, add two attributes (after `self.upsert_on_conflict`):

```python
        self.brief_table_exists = True
        self.brief_upserts: list[Any] = []
```

Then append these tests:

```python
def _set_brief(tmp_path, monkeypatch, body="A weekly read.\n"):
    from macro_framework import build

    briefs = tmp_path / "briefs"
    (briefs / "2026-05-27").mkdir(parents=True)
    (briefs / "2026-05-27" / "top.md").write_text(body)
    monkeypatch.setattr(build, "BRIEFS_DIR", briefs)


def test_upsert_top_brief_writes_row(tmp_path, monkeypatch, capsys):
    _set_brief(tmp_path, monkeypatch)
    client = FakeClient()
    sync_to_supabase._upsert_top_brief(client)
    assert client.brief_upserts == [
        {"id": 1, "brief_date": "2026-05-27", "body_md": "A weekly read."}
    ]
    assert client.upsert_on_conflict == "id"


def test_upsert_top_brief_skips_when_no_brief(tmp_path, monkeypatch, capsys):
    from macro_framework import build

    monkeypatch.setattr(build, "BRIEFS_DIR", tmp_path / "briefs")
    client = FakeClient()
    sync_to_supabase._upsert_top_brief(client)
    assert client.brief_upserts == []
    assert "No top brief" in capsys.readouterr().out


def test_upsert_top_brief_best_effort_on_failure(tmp_path, monkeypatch, capsys):
    _set_brief(tmp_path, monkeypatch)
    client = FakeClient()
    client.brief_table_exists = False  # simulate migration not yet applied
    # Must NOT raise — best-effort.
    sync_to_supabase._upsert_top_brief(client)
    assert client.brief_upserts == []
    assert "non-fatal" in capsys.readouterr().err
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_supabase_sync.py -k upsert_top_brief -v`
Expected: FAIL — `AttributeError: module 'macro_framework.sync_to_supabase' has no attribute '_upsert_top_brief'`

- [ ] **Step 3: Bump the schema version and implement `_upsert_top_brief`**

In `src/macro_framework/sync_to_supabase.py`, change line 33:

```python
EXPECTED_SCHEMA_VERSION = 4
```

Add `_upsert_top_brief` directly below `top_brief_row()` (above `cmd_latest`):

```python
def _upsert_top_brief(client: Client) -> None:
    """Best-effort: mirror the latest top brief markdown to macro_top_brief.

    The numeric macro_snapshots row is the contract; the brief is supplementary,
    so any failure here is logged and swallowed rather than failing the sync.
    """
    row = top_brief_row()
    if row is None:
        print("No top brief found; skipping macro_top_brief.")
        return
    print(f"Upserting top brief ({row['brief_date']})...")
    try:
        client.table("macro_top_brief").upsert(row, on_conflict="id").execute()
        print("OK (top brief)")
    except Exception as exc:  # best-effort: never fail the sync on the brief
        print(f"Warning: top brief upload failed (non-fatal): {exc}", file=sys.stderr)
```

In `cmd_latest()`, after the existing success print `print(f"OK ({len(resp.data)} row)")`, add:

```python
    _upsert_top_brief(client)
```

(`sys` is already imported at the top of the module.)

- [ ] **Step 4: Run the targeted and full test suite**

Run: `.venv/bin/python -m pytest tests/test_supabase_sync.py -v`
Expected: PASS (all, including the existing preflight/version tests — they read `EXPECTED_SCHEMA_VERSION` symbolically so the bump to 4 is transparent).

Run: `.venv/bin/python -m pytest`
Expected: PASS (full suite green).

- [ ] **Step 5: Lint**

Run: `.venv/bin/python -m ruff check .`
Expected: no errors. (If `ruff` is not in the venv, run `.venv/bin/python -m ruff check .` after `.venv/bin/python -m pip install ruff`, or skip with a note — not a blocker for logic.)

- [ ] **Step 6: Commit**

```bash
git add src/macro_framework/sync_to_supabase.py tests/test_supabase_sync.py
git commit -m "feat(supabase): upload top brief in cmd_latest, bump schema_version to 4"
```

---

### Task 4: Docs

**Files:**
- Modify: `AGENTS.md` (the "What this does" paragraph)

- [ ] **Step 1: Update the AGENTS.md description**

In `AGENTS.md`, find the sentence in the "What this does" section:

> ...writes daily snapshots and a self-contained dashboard, syncs hot fields to Supabase, and lazily refreshes three Claude-generated weekly briefs...

Change "syncs hot fields to Supabase" to:

> syncs hot fields and the current week's top brief (single-row `macro_top_brief` table) to Supabase

- [ ] **Step 2: Verify**

Run: `grep -n "macro_top_brief" AGENTS.md`
Expected: one match in the "What this does" paragraph.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: note top brief Supabase mirror in AGENTS.md"
```

---

### Task 5: Operational apply (manual, may be blocked)

**Files:** none (remote Supabase change)

- [ ] **Step 1: Apply the migration**

Paste the full contents of `migrations/0004_macro_top_brief.sql` into the Supabase SQL Editor and run it. If you cannot apply SQL remotely from this session, mark this step blocked and stop here — the migration + version bump are already committed. Do NOT weaken preflight to make `doctor` pass.

- [ ] **Step 2: Verify the remote schema**

Run: `PYTHONPATH=src .venv/bin/python -m macro_framework.sync_to_supabase doctor`
Expected: `Supabase preflight OK (schema version 4)`.

- [ ] **Step 3: Smoke the live sync (optional, requires creds + applied migration)**

Run: `PYTHONPATH=src .venv/bin/python -m macro_framework.sync_to_supabase latest`
Expected: numeric upsert OK, then `Upserting top brief (<date>)...` / `OK (top brief)`. Confirm one row in `macro_top_brief` with the markdown body.

---

## Self-Review

- **Spec coverage:** table (T1), single-row lock (T1 `check (id=1)` + `on_conflict="id"` T3), raw markdown (T2 `body_md`), `brief_date` (T2), trigger during `latest` (T3), best-effort failure (T3 test + impl), schema bump + `EXPECTED_SCHEMA_VERSION` (T1 SQL + T3 code), tests (T2/T3), docs (T4), manual apply caveat (T5). All spec sections mapped.
- **Placeholder scan:** none — every code/test step is complete and runnable.
- **Type consistency:** `top_brief_row()` returns the exact dict `{"id","brief_date","body_md"}` asserted in T2 and consumed by `_upsert_top_brief` in T3; `on_conflict="id"` matches the PK; fake `brief_table_exists`/`brief_upserts` defined in T3 Step 1 before use.
