# Backtest Stats → Supabase Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Mirror the dashboard backtest card figures to Supabase in a single-row `macro_backtest` table (JSONB blob), sourced from a new structured `BACKTEST_STATS` constant that also renders the (byte-identical) card.

**Architecture:** Refactor the hardcoded backtest HTML in `build.py` into `BACKTEST_STATS` + `_render_backtest_card_html()`. A lock test guarantees the rendered card is byte-identical to today's. A new migration adds the single-row table; `sync_to_supabase.py` gains `backtest_row()` + best-effort `_upsert_backtest(client)`, wired into `cmd_latest()` after the top-brief upload.

**Tech Stack:** Python 3.12, supabase-py, pytest, Supabase Postgres + RLS.

**Spec:** `docs/superpowers/specs/2026-05-29-backtest-stats-supabase-design.md`

> **Tooling:** `uv` not on PATH. Use `.venv/bin/python -m pytest` and `PYTHONPATH=src .venv/bin/python -m ...`. `ruff` is not installed in the venv (lint gate can't run; not a logic blocker).

> **Commit hygiene:** use ONLY the explicit `git add <path>` per task. Never `git add -A`/`.`. Builds on prior commits; depends on `macro_top_brief` (schema v4) already present.

---

### Task 1: Add the `macro_backtest` migration

**Files:** Create `migrations/0005_macro_backtest.sql`

- [ ] **Step 1: Write the migration SQL** — create `migrations/0005_macro_backtest.sql` with exactly:

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

- [ ] **Step 2: Verify** — `tail -5 migrations/0005_macro_backtest.sql` ends with schema_version upsert to `'5'`; it is the highest-numbered migration. Reuses `set_updated_at()` (do not redefine).

- [ ] **Step 3: Commit**
```bash
git add migrations/0005_macro_backtest.sql
git commit -m "feat(supabase): add macro_backtest single-row table migration"
```

---

### Task 2: `BACKTEST_STATS` constant + `_render_backtest_card_html` (byte-identical lock)

**Files:** Modify `src/macro_framework/build.py`; Test `tests/test_smoke.py`

**Context:** Currently `build.py:684` does:
`backtest_card_html = preview_meta.get("backtest_card_html") or '''<literal>'''`
where `<literal>` is the multi-line card. We replace the inline literal with a render call, keeping the `preview_meta` override. The render output MUST equal the current literal exactly.

- [ ] **Step 1: Write the failing lock test.** Append to `tests/test_smoke.py`:

```python
def test_render_backtest_card_html_is_byte_identical():
    """Locks the backtest card output so the dashboard does not change when the
    hardcoded literal is refactored into BACKTEST_STATS + a renderer."""
    from macro_framework import build

    expected = '''
    <!-- Backtest figures source: reports/task-35-investor-grade-thresholds.md recommendation -->
    <details class="backtest-toggle">
      <summary>How well does this work historically? <span class="muted small">(click)</span></summary>
      <div class="backtest-toggle-body">
        <p class="muted small" style="margin-bottom: 8px;">Full-sample investor-grade posture backtest (2017–2026), no leverage:</p>
        <ul class="backtest-list">
          <li><span class="bt-asset-inline">SPX</span> +20.9% annual return · max drawdown −7.3% · Calmar 2.88</li>
          <li><span class="bt-asset-inline">Russell 2000</span> +25.6% annual return · max drawdown −10.0% · Calmar 2.57</li>
          <li><span class="bt-asset-inline">Bitcoin</span> +39.3% annual return · max drawdown −58.6% · Calmar 0.67</li>
        </ul>
        <p class="muted small" style="margin-top: 8px;">Average exposure 62.9% of the time (cash 27.9%, caution 36.6%).</p>
      </div>
    </details>'''
    assert build._render_backtest_card_html(build.BACKTEST_STATS) == expected
```

(Note: `–` = en dash, `·` = middle dot `·`, `−` = unicode minus `−`. These match the exact characters in the live card.)

- [ ] **Step 2: Run to verify it fails** — `.venv/bin/python -m pytest tests/test_smoke.py::test_render_backtest_card_html_is_byte_identical -v`
Expected: FAIL — `AttributeError: module 'macro_framework.build' has no attribute 'BACKTEST_STATS'` (or `_render_backtest_card_html`).

- [ ] **Step 3: Add the constant + renderer.** In `src/macro_framework/build.py`, add near the other module-level constants (top of file, after imports — place it just above the first function that uses preview rendering, or with the other ALL_CAPS constants):

```python
BACKTEST_STATS = {
    "window": "2017–2026",
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


def _render_backtest_card_html(stats: dict) -> str:
    """Render the 'How well does this work historically?' card from BACKTEST_STATS.

    Output is locked byte-for-byte by test_render_backtest_card_html_is_byte_identical.
    Uses unicode minus (U+2212) for drawdowns and middle dot (U+00B7) separators
    to match the original hand-written literal.
    """
    def _line(a: dict) -> str:
        return (
            f'<li><span class="bt-asset-inline">{a["name"]}</span> '
            f'+{a["annual_return_pct"]:.1f}% annual return · '
            f'max drawdown −{abs(a["max_drawdown_pct"]):.1f}% · '
            f'Calmar {a["calmar"]:.2f}</li>'
        )

    spx, russell, btc = stats["assets"]
    return f'''
    <!-- Backtest figures source: {stats["source"]} recommendation -->
    <details class="backtest-toggle">
      <summary>How well does this work historically? <span class="muted small">(click)</span></summary>
      <div class="backtest-toggle-body">
        <p class="muted small" style="margin-bottom: 8px;">Full-sample investor-grade posture backtest ({stats["window"]}), {stats["leverage"]}:</p>
        <ul class="backtest-list">
          {_line(spx)}
          {_line(russell)}
          {_line(btc)}
        </ul>
        <p class="muted small" style="margin-top: 8px;">Average exposure {stats["avg_exposure_pct"]:.1f}% of the time (cash {stats["cash_pct"]:.1f}%, caution {stats["caution_pct"]:.1f}%).</p>
      </div>
    </details>'''
```

- [ ] **Step 4: Run the lock test until it passes** — `.venv/bin/python -m pytest tests/test_smoke.py::test_render_backtest_card_html_is_byte_identical -v`
Expected: PASS. If it fails, diff the two strings character-by-character (e.g. in a scratch `python -c`) and fix whitespace/characters until exactly equal. Do NOT change `expected` to match a wrong renderer — the renderer must match `expected`.

- [ ] **Step 5: Wire the renderer into the build.** In `src/macro_framework/build.py`, replace the assignment that currently reads:
```python
    backtest_card_html = preview_meta.get("backtest_card_html") or '''
    <!-- Backtest figures source: reports/task-35-investor-grade-thresholds.md recommendation -->
    <details class="backtest-toggle">
      <summary>How well does this work historically? <span class="muted small">(click)</span></summary>
      <div class="backtest-toggle-body">
        <p class="muted small" style="margin-bottom: 8px;">Full-sample investor-grade posture backtest (2017–2026), no leverage:</p>
        <ul class="backtest-list">
          <li><span class="bt-asset-inline">SPX</span> +20.9% annual return · max drawdown −7.3% · Calmar 2.88</li>
          <li><span class="bt-asset-inline">Russell 2000</span> +25.6% annual return · max drawdown −10.0% · Calmar 2.57</li>
          <li><span class="bt-asset-inline">Bitcoin</span> +39.3% annual return · max drawdown −58.6% · Calmar 0.67</li>
        </ul>
        <p class="muted small" style="margin-top: 8px;">Average exposure 62.9% of the time (cash 27.9%, caution 36.6%).</p>
      </div>
    </details>'''
```
with this single line:
```python
    backtest_card_html = preview_meta.get("backtest_card_html") or _render_backtest_card_html(BACKTEST_STATS)
```

- [ ] **Step 6: Verify the dashboard output is unchanged.** Build and confirm the card text is present and identical:
```bash
PYTHONPATH=src .venv/bin/python -m macro_framework.build 2>&1 | tail -3
grep -c "How well does this work historically" outputs/dashboard.html
grep -o "SPX</span> +20.9% annual return · max drawdown −7.3% · Calmar 2.88" outputs/dashboard.html
```
Expected: build succeeds; first grep prints `1`; second grep echoes the exact line (confirms unicode chars intact). NOTE: this regenerates `outputs/dashboard.html` and may write a new `snapshots/<today>.json`; do NOT stage those in this task.

- [ ] **Step 7: Run the full smoke suite** — `.venv/bin/python -m pytest tests/test_smoke.py -v`
Expected: the new lock test passes; the pre-existing `test_canonical_backtest_matches_task35_investor_posture_calmar` failure (Calmar drift, unrelated) may still fail — that is acceptable and out of scope. No OTHER test should newly fail.

- [ ] **Step 8: Commit** (only the two intended files)
```bash
git add src/macro_framework/build.py tests/test_smoke.py
git commit -m "refactor(build): structure backtest card into BACKTEST_STATS + renderer"
```

---

### Task 3: `backtest_row()` + best-effort `_upsert_backtest`, wire into `cmd_latest`, bump schema version

**Files:** Modify `src/macro_framework/sync_to_supabase.py`; Test `tests/test_supabase_sync.py`

- [ ] **Step 1: Extend the fakes and write failing tests.** In `tests/test_supabase_sync.py`, extend `FakeQuery.execute` to also route `macro_backtest`. The method currently ends (after the `macro_top_brief` branch added in the prior feature) with `raise RuntimeError(f"relation {self.table} does not exist")`. Add this branch immediately before that final `raise`:

```python
        if self.table == "macro_backtest":
            if not self.client.backtest_table_exists:
                raise RuntimeError("relation macro_backtest does not exist")
            self.client.backtest_upserts.append(self.payload)
            return SimpleNamespace(data=[self.payload])
```

In `FakeClient.__init__`, after the `self.brief_upserts` line, add:
```python
        self.backtest_table_exists = True
        self.backtest_upserts: list[Any] = []
```

Append these tests:
```python
def test_backtest_row_returns_stats():
    from macro_framework import build

    row = sync_to_supabase.backtest_row()
    assert row == {"id": 1, "stats": build.BACKTEST_STATS}


def test_upsert_backtest_writes_row(capsys):
    client = FakeClient()
    sync_to_supabase._upsert_backtest(client)
    from macro_framework import build
    assert client.backtest_upserts == [{"id": 1, "stats": build.BACKTEST_STATS}]
    assert client.upsert_on_conflict == "id"


def test_upsert_backtest_best_effort_on_failure(capsys):
    client = FakeClient()
    client.backtest_table_exists = False  # simulate migration not yet applied
    sync_to_supabase._upsert_backtest(client)  # must NOT raise
    assert client.backtest_upserts == []
    assert "non-fatal" in capsys.readouterr().err
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/python -m pytest tests/test_supabase_sync.py -k backtest -v`
Expected: FAIL — no attribute `backtest_row` / `_upsert_backtest`.

- [ ] **Step 3: Implement.** In `src/macro_framework/sync_to_supabase.py`:

(a) Change `EXPECTED_SCHEMA_VERSION = 4` to `EXPECTED_SCHEMA_VERSION = 5`.

(b) Add these two functions directly below `_upsert_top_brief` (above `cmd_latest`):
```python
def backtest_row() -> dict[str, Any]:
    """Build the macro_backtest row from the static BACKTEST_STATS constant."""
    from macro_framework import build  # single source of truth for the figures

    return {"id": 1, "stats": build.BACKTEST_STATS}


def _upsert_backtest(client: Client) -> None:
    """Best-effort: mirror the dashboard backtest stats to macro_backtest.

    Supplementary to the numeric macro_snapshots row, so failures are logged and
    swallowed rather than failing the sync.
    """
    row = backtest_row()
    print("Upserting backtest stats...")
    try:
        client.table("macro_backtest").upsert(row, on_conflict="id").execute()
        print("OK (backtest)")
    except Exception as exc:  # best-effort: never fail the sync on the backtest
        print(f"Warning: backtest upload failed (non-fatal): {exc}", file=sys.stderr)
```

(c) In `cmd_latest()`, immediately after the existing `_upsert_top_brief(client)` line, add at the same indentation:
```python
    _upsert_backtest(client)
```

- [ ] **Step 4: Run targeted then full suite**
- `.venv/bin/python -m pytest tests/test_supabase_sync.py -v` → all pass.
- `.venv/bin/python -m pytest` → only the pre-existing unrelated Calmar-drift smoke test may fail; nothing else new.

- [ ] **Step 5: Commit**
```bash
git add src/macro_framework/sync_to_supabase.py tests/test_supabase_sync.py
git commit -m "feat(supabase): upload backtest stats in cmd_latest, bump schema_version to 5"
```

---

### Task 4: Docs

**Files:** Modify `AGENTS.md` ("What this does" paragraph)

- [ ] **Step 1:** In `AGENTS.md`, the sentence currently reads (after the prior feature):
`syncs hot fields and the current week's top brief (single-row \`macro_top_brief\` table) to Supabase`
Change it to:
`syncs hot fields, the current week's top brief (single-row \`macro_top_brief\` table), and backtest stats (single-row \`macro_backtest\` table) to Supabase`

- [ ] **Step 2: Verify** — `grep -n "macro_backtest" AGENTS.md` → one match.

- [ ] **Step 3: Commit**
```bash
git add AGENTS.md
git commit -m "docs: note backtest stats Supabase mirror in AGENTS.md"
```

---

### Task 5: Operational apply (manual)

- [ ] **Step 1:** Apply `migrations/0005_macro_backtest.sql` in the Supabase SQL editor (controller asks the user to run it). If unappliable from session, mark blocked; migration + bump already committed; do not weaken preflight.
- [ ] **Step 2: Verify** — `PYTHONPATH=src .venv/bin/python -m macro_framework.sync_to_supabase doctor` → `Supabase preflight OK (schema version 5)`.
- [ ] **Step 3: Live sync** — `PYTHONPATH=src .venv/bin/python -m macro_framework.sync_to_supabase latest` → after numeric + brief, prints `Upserting backtest stats... / OK (backtest)`. Read back the single `macro_backtest` row and confirm the `stats` blob.

---

## Self-Review

- **Spec coverage:** constant + renderer + preview override preserved + byte-identical lock (T2), table (T1), single-row lock + JSONB (T1), `backtest_row` (T3), best-effort `_upsert_backtest` + wiring + schema bump (T3), tests (T2/T3), docs (T4), manual apply (T5). All mapped.
- **Placeholder scan:** none — all code/tests complete.
- **Type consistency:** `backtest_row()` returns `{"id","stats"}` matching the `_upsert_backtest` upsert and the T3 tests; `BACKTEST_STATS` shape matches what `_render_backtest_card_html` indexes (`assets` list of `{name,annual_return_pct,max_drawdown_pct,calmar}`, plus `window/leverage/source/avg_exposure_pct/cash_pct/caution_pct`); fakes `backtest_table_exists`/`backtest_upserts` defined before use.
