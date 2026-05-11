# Supabase Indicator Sync — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mirror macro framework's computed indicators to existing Supabase project via a separate `sync_to_supabase.py` script with backfill + daily modes.

**Architecture:** Hybrid schema (hot scalars + JSONB blob) in a single `macro_snapshots` table. Service-key writes from this repo; anon-key reads via RLS for downstream apps. Sync script reuses compute functions from `build.py` for backfill — no math duplication.

**Tech Stack:** Python 3.12, `supabase-py` client, `python-dotenv`, pytest. Existing repo deps: pandas, numpy, yfinance, requests.

**Spec:** `docs/superpowers/specs/2026-05-11-supabase-sync-design.md`

---

## File Structure

- **Create:** `sync_to_supabase.py` — entry point, argparse subcommands (`latest`, `backfill`), row builders, Supabase client wrapper.
- **Create:** `supabase_schema.sql` — table DDL, indexes, `updated_at` trigger, RLS policy. Run once against the Supabase project.
- **Create:** `.env.example` — credential template (committed, no real values).
- **Create:** `test_sync_to_supabase.py` — unit tests at repo root, matches flat layout (`analyze_*.py`, `optimize_*.py`).
- **Modify:** `requirements.txt` — append `supabase` and `python-dotenv`.
- **No change:** `.gitignore` already excludes `.env`.
- **No change:** `build.py`, `build_v2.py`, `generate_commentary.py`.

Each file has one responsibility. Sync logic stays in one focused module (~200 lines). Schema lives in SQL so it can be applied via Supabase SQL editor or `psql`.

---

## Task 1: Add dependencies and `.env.example`

**Files:**
- Modify: `requirements.txt`
- Create: `.env.example`

- [ ] **Step 1: Append new deps to `requirements.txt`**

The file currently ends after `matplotlib==3.10.8`. Append two lines:

```
supabase==2.21.0
python-dotenv==1.0.1
```

- [ ] **Step 2: Install the new deps**

Run: `.venv/bin/pip install -r requirements.txt`
Expected: `Successfully installed supabase-2.21.0 python-dotenv-1.0.1` (plus transitive deps like httpx, gotrue, postgrest).

- [ ] **Step 3: Create `.env.example`**

```
# Supabase credentials for sync_to_supabase.py
# Copy this file to .env and fill in real values (do not commit .env).
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGc...your-service-role-key...
```

- [ ] **Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "Add Supabase + dotenv deps, .env.example template"
```

---

## Task 2: Write the schema SQL

**Files:**
- Create: `supabase_schema.sql`

- [ ] **Step 1: Write the schema file**

```sql
-- macro_snapshots: daily computed indicators from Macro Framework.
-- Apply via Supabase SQL editor or `psql`. Idempotent for fresh projects only.

create table if not exists macro_snapshots (
  date              date primary key,
  -- Headline (from snapshot.mrmi_combined.*)
  mrmi              numeric,
  mrmi_state        text check (mrmi_state in ('LONG','CASH')),
  mmi               numeric,
  stress_intensity  numeric,
  macro_buffer      numeric,
  -- Macro stress inputs (snapshot.macro.*)
  real_economy      numeric,
  inflation_dir_pp  numeric,
  core_cpi_yoy_pct  numeric,
  -- MMI components (snapshot.components.*)
  gii_fast          numeric,
  breadth           numeric,
  fincon            numeric,
  -- Full point-in-time blob; null for historical backfilled rows.
  snapshot          jsonb,
  created_at        timestamptz default now(),
  updated_at        timestamptz default now()
);

create index if not exists macro_snapshots_state_idx on macro_snapshots(mrmi_state);
create index if not exists macro_snapshots_snapshot_idx on macro_snapshots using gin (snapshot);

create or replace function set_updated_at() returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists macro_snapshots_set_updated_at on macro_snapshots;
create trigger macro_snapshots_set_updated_at
before update on macro_snapshots
for each row execute function set_updated_at();

-- RLS: public read, no public write.
alter table macro_snapshots enable row level security;

drop policy if exists "anon read" on macro_snapshots;
create policy "anon read" on macro_snapshots
  for select to anon using (true);
```

- [ ] **Step 2: Verify the file parses (syntax sanity check, no live DB needed)**

Run: `head -1 supabase_schema.sql`
Expected: `-- macro_snapshots: daily computed indicators from Macro Framework.`

- [ ] **Step 3: Commit**

```bash
git add supabase_schema.sql
git commit -m "Add Supabase schema for macro_snapshots table + RLS"
```

---

## Task 3: Test-first — row builder from snapshot JSON

This is the highest-risk function — the `mrmi` vs `mrmi_combined` field-name pitfall lives here. Test catches the regression.

**Files:**
- Create: `test_sync_to_supabase.py`
- Create: `sync_to_supabase.py`

- [ ] **Step 1: Write the failing test**

```python
# test_sync_to_supabase.py
import pytest
from sync_to_supabase import row_from_snapshot


SAMPLE_SNAPSHOT = {
    "date": "2026-05-11",
    "build_time_utc": "2026-05-11T10:00:00Z",
    "mrmi": {"composite": 0.5227, "state": "green"},  # legacy: this is MMI, NOT headline
    "mrmi_combined": {
        "value": 1.0227,
        "state": "LONG",
        "momentum": 0.5227,
        "stress_intensity": 0.0,
        "macro_buffer": 1.0,
        "buffer_size": 1.0,
    },
    "components": {"gii_fast": 0.2712, "fincon": 0.4821, "breadth": 0.8149},
    "macro": {
        "real_economy_score": -0.8924,
        "inflation_dir_pp": -0.4178,
        "core_cpi_yoy_pct": 2.6022,
        "real_economy_components": {},
        "raw": {},
    },
    "underliers": {"^GSPC": 5000.0},
}


def test_row_from_snapshot_maps_headline_to_mrmi_combined():
    """Regression test: `mrmi` column must come from `mrmi_combined.value`,
    NOT from `mrmi.composite` (which is the MMI value)."""
    row = row_from_snapshot(SAMPLE_SNAPSHOT)

    assert row["date"] == "2026-05-11"
    assert row["mrmi"] == pytest.approx(1.0227)             # not 0.5227
    assert row["mrmi_state"] == "LONG"                      # not 'green'
    assert row["mmi"] == pytest.approx(0.5227)              # from mrmi_combined.momentum
    assert row["stress_intensity"] == pytest.approx(0.0)
    assert row["macro_buffer"] == pytest.approx(1.0)
    assert row["real_economy"] == pytest.approx(-0.8924)
    assert row["inflation_dir_pp"] == pytest.approx(-0.4178)
    assert row["core_cpi_yoy_pct"] == pytest.approx(2.6022)
    assert row["gii_fast"] == pytest.approx(0.2712)
    assert row["breadth"] == pytest.approx(0.8149)
    assert row["fincon"] == pytest.approx(0.4821)


def test_row_from_snapshot_embeds_full_blob():
    row = row_from_snapshot(SAMPLE_SNAPSHOT)
    assert row["snapshot"] == SAMPLE_SNAPSHOT
    assert row["snapshot"]["underliers"]["^GSPC"] == 5000.0
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
Expected: `ImportError: cannot import name 'row_from_snapshot' from 'sync_to_supabase'` (file doesn't exist yet).

- [ ] **Step 3: Implement minimal `row_from_snapshot` in `sync_to_supabase.py`**

```python
# sync_to_supabase.py
"""
Sync computed macro indicators to Supabase.

Subcommands:
  latest   — upsert today's snapshot (default)
  backfill — recompute and upsert full daily history

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in .env or environment.
See docs/superpowers/specs/2026-05-11-supabase-sync-design.md for design.
"""
from __future__ import annotations

from typing import Any


def row_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a macro_snapshots row from a daily snapshot dict.

    IMPORTANT: snapshot['mrmi'] is the MMI value (misnamed legacy field).
    The true MRMI headline is snapshot['mrmi_combined']['value'].
    """
    mrmi_c = snapshot["mrmi_combined"]
    macro = snapshot["macro"]
    components = snapshot["components"]
    return {
        "date": snapshot["date"],
        "mrmi": mrmi_c["value"],
        "mrmi_state": mrmi_c["state"],
        "mmi": mrmi_c["momentum"],
        "stress_intensity": mrmi_c["stress_intensity"],
        "macro_buffer": mrmi_c["macro_buffer"],
        "real_economy": macro["real_economy_score"],
        "inflation_dir_pp": macro["inflation_dir_pp"],
        "core_cpi_yoy_pct": macro["core_cpi_yoy_pct"],
        "gii_fast": components["gii_fast"],
        "breadth": components["breadth"],
        "fincon": components["fincon"],
        "snapshot": snapshot,
    }
```

- [ ] **Step 4: Run the tests and verify they pass**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add test_sync_to_supabase.py sync_to_supabase.py
git commit -m "Add row_from_snapshot with regression test for mrmi field-name trap"
```

---

## Task 4: Test-first — row builders for backfill (from time series)

Backfill recomputes MRMI/MMI/etc. for every historical date. Test verifies the row builder correctly maps per-date series values to row dicts, including `mrmi_state` derivation (`LONG` if mrmi > 0, `CASH` if <= 0).

**Files:**
- Modify: `test_sync_to_supabase.py`
- Modify: `sync_to_supabase.py`

- [ ] **Step 1: Write the failing test**

Append to `test_sync_to_supabase.py`:

```python
import pandas as pd
import numpy as np
from sync_to_supabase import rows_from_backfill_series


def test_rows_from_backfill_series_basic():
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    series = {
        "mrmi":             pd.Series([0.5, -0.1, 1.2], index=idx),
        "mmi":              pd.Series([0.3, -0.2, 0.7], index=idx),
        "stress_intensity": pd.Series([0.0, 0.4, 0.0], index=idx),
        "macro_buffer":     pd.Series([1.0, 0.6, 1.0], index=idx),
        "real_economy":     pd.Series([-0.1, -0.5, 0.1], index=idx),
        "inflation_dir_pp": pd.Series([0.0, 1.0, -0.2], index=idx),
        "core_cpi_yoy_pct": pd.Series([3.0, 3.1, 2.9], index=idx),
        "gii_fast":         pd.Series([0.1, 0.0, 0.2], index=idx),
        "breadth":          pd.Series([0.5, 0.4, 0.6], index=idx),
        "fincon":           pd.Series([0.4, 0.3, 0.5], index=idx),
    }
    rows = rows_from_backfill_series(series)

    assert len(rows) == 3
    assert rows[0]["date"] == "2024-01-01"
    assert rows[0]["mrmi"] == 0.5
    assert rows[0]["mrmi_state"] == "LONG"      # mrmi > 0
    assert rows[1]["mrmi_state"] == "CASH"      # mrmi <= 0
    assert rows[2]["mrmi_state"] == "LONG"
    assert rows[0]["snapshot"] is None          # backfill rows have no JSONB blob


def test_rows_from_backfill_series_skips_nan_rows():
    """Rows where mrmi is NaN (e.g. pre-warmup dates) must be skipped."""
    idx = pd.to_datetime(["2024-01-01", "2024-01-02"])
    series = {
        "mrmi":             pd.Series([np.nan, 0.5], index=idx),
        "mmi":              pd.Series([np.nan, 0.3], index=idx),
        "stress_intensity": pd.Series([np.nan, 0.0], index=idx),
        "macro_buffer":     pd.Series([np.nan, 1.0], index=idx),
        "real_economy":     pd.Series([np.nan, -0.1], index=idx),
        "inflation_dir_pp": pd.Series([np.nan, 0.0], index=idx),
        "core_cpi_yoy_pct": pd.Series([np.nan, 3.0], index=idx),
        "gii_fast":         pd.Series([np.nan, 0.1], index=idx),
        "breadth":          pd.Series([np.nan, 0.5], index=idx),
        "fincon":           pd.Series([np.nan, 0.4], index=idx),
    }
    rows = rows_from_backfill_series(series)
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-01-02"
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py::test_rows_from_backfill_series_basic test_sync_to_supabase.py::test_rows_from_backfill_series_skips_nan_rows -v`
Expected: `ImportError: cannot import name 'rows_from_backfill_series'`.

- [ ] **Step 3: Implement `rows_from_backfill_series` in `sync_to_supabase.py`**

Append to `sync_to_supabase.py`:

```python
import math
import pandas as pd


_HOT_COLUMNS = (
    "mrmi", "mmi", "stress_intensity", "macro_buffer",
    "real_economy", "inflation_dir_pp", "core_cpi_yoy_pct",
    "gii_fast", "breadth", "fincon",
)


def rows_from_backfill_series(series: dict[str, pd.Series]) -> list[dict[str, Any]]:
    """Build macro_snapshots rows from per-column daily series.

    Skips rows where mrmi is NaN (pre-warmup dates). Derives mrmi_state
    from mrmi sign: LONG if mrmi > 0 else CASH.
    """
    mrmi = series["mrmi"]
    rows: list[dict[str, Any]] = []
    for date in mrmi.index:
        v = mrmi.loc[date]
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        row: dict[str, Any] = {
            "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
            "mrmi_state": "LONG" if v > 0 else "CASH",
            "snapshot": None,
        }
        for col in _HOT_COLUMNS:
            cell = series[col].loc[date]
            row[col] = None if (isinstance(cell, float) and math.isnan(cell)) else float(cell)
        rows.append(row)
    return rows
```

- [ ] **Step 4: Run all tests and verify they pass**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add test_sync_to_supabase.py sync_to_supabase.py
git commit -m "Add rows_from_backfill_series with state derivation + NaN skip"
```

---

## Task 5: Test-first — credential loading + fail-fast

**Files:**
- Modify: `test_sync_to_supabase.py`
- Modify: `sync_to_supabase.py`

- [ ] **Step 1: Write the failing test**

Append to `test_sync_to_supabase.py`:

```python
from sync_to_supabase import load_credentials


def test_load_credentials_returns_values(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "eyJtest")
    url, key = load_credentials()
    assert url == "https://abc.supabase.co"
    assert key == "eyJtest"


def test_load_credentials_missing_url_exits(monkeypatch, capsys):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "eyJtest")
    with pytest.raises(SystemExit) as exc:
        load_credentials()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "SUPABASE_URL" in captured.err


def test_load_credentials_missing_key_exits(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_URL", "https://abc.supabase.co")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_credentials()
    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "SUPABASE_SERVICE_KEY" in captured.err
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -k load_credentials -v`
Expected: `ImportError: cannot import name 'load_credentials'`.

- [ ] **Step 3: Implement `load_credentials` in `sync_to_supabase.py`**

Append to `sync_to_supabase.py`:

```python
import os
import sys
from dotenv import load_dotenv


def load_credentials() -> tuple[str, str]:
    """Load Supabase URL + service key from .env or environment.

    Exits with code 1 and a clear error message if either is missing.
    """
    load_dotenv()  # silently no-op if .env absent
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    missing = [name for name, val in (("SUPABASE_URL", url), ("SUPABASE_SERVICE_KEY", key)) if not val]
    if missing:
        print(
            f"error: missing required env var(s): {', '.join(missing)}\n"
            f"Set them in .env (copy .env.example) or export them in your shell.",
            file=sys.stderr,
        )
        sys.exit(1)
    return url, key
```

- [ ] **Step 4: Run all tests and verify they pass**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add test_sync_to_supabase.py sync_to_supabase.py
git commit -m "Add load_credentials with fail-fast on missing env vars"
```

---

## Task 6: Implement the `latest` subcommand

Wires `row_from_snapshot` + `load_credentials` + Supabase upsert. No test (this is integration glue; correctness of the row is already covered by Task 3 tests).

**Files:**
- Modify: `sync_to_supabase.py`

- [ ] **Step 1: Add latest-snapshot discovery + upsert function**

Append to `sync_to_supabase.py`:

```python
import json
from pathlib import Path
from supabase import create_client, Client


SNAPSHOT_DIR = Path(__file__).parent / ".cache" / "snapshots"


def _supabase_client() -> Client:
    url, key = load_credentials()
    return create_client(url, key)


def _latest_snapshot_path() -> Path:
    if not SNAPSHOT_DIR.exists():
        print(
            f"error: no snapshot directory at {SNAPSHOT_DIR}.\n"
            f"Run `.venv/bin/python build.py` first to produce a snapshot.",
            file=sys.stderr,
        )
        sys.exit(1)
    snapshots = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not snapshots:
        print(
            f"error: no snapshot JSON files in {SNAPSHOT_DIR}.\n"
            f"Run `.venv/bin/python build.py` first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return snapshots[-1]


def cmd_latest() -> None:
    path = _latest_snapshot_path()
    print(f"Reading {path.name}...")
    with open(path) as f:
        snapshot = json.load(f)
    row = row_from_snapshot(snapshot)
    client = _supabase_client()
    print(f"Upserting row for {row['date']}...")
    resp = client.table("macro_snapshots").upsert(row, on_conflict="date").execute()
    if not resp.data:
        print(f"error: upsert returned empty response: {resp}", file=sys.stderr)
        sys.exit(1)
    print(f"OK ({len(resp.data)} row)")
```

- [ ] **Step 2: Verify imports still work and tests still pass**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
Expected: `7 passed` (no regressions).

- [ ] **Step 3: Commit**

```bash
git add sync_to_supabase.py
git commit -m "Add cmd_latest for daily snapshot upsert"
```

---

## Task 7: Implement the `backfill` subcommand

Reuses compute functions from `build.py` for full history. No test (covered by Task 4's row builder test + the math is `build.py`'s job).

**Files:**
- Modify: `sync_to_supabase.py`

- [ ] **Step 1: Implement `cmd_backfill`**

Append to `sync_to_supabase.py`:

```python
import build  # reuses fetch + compute pipeline


_CHUNK_SIZE = 500


def cmd_backfill() -> None:
    print("Loading raw data + recomputing indicators...")
    data = build.fetch_all_data(use_cache=True)
    gii = build.calc_growth_impulse(data)
    fincon = build.calc_financial_conditions(data)
    breadth = build.calc_sector_breadth(data)
    composite = build.calc_composite(gii, fincon, breadth)  # MMI series
    macro_ctx = build.calc_macro_context(data)
    mrmi_combined = build.calc_milk_road_macro_index(composite, macro_ctx)

    series = {
        "mrmi":             mrmi_combined["mrmi"],
        "mmi":              composite,
        "stress_intensity": mrmi_combined["stress_intensity"],
        "macro_buffer":     mrmi_combined["macro_buffer"],
        "real_economy":     macro_ctx["real_economy_score"],
        "inflation_dir_pp": macro_ctx["inflation_dir_pp"],
        "core_cpi_yoy_pct": macro_ctx["core_cpi_yoy_pct"],
        "gii_fast":         gii["fast"],
        "breadth":          breadth["composite"],
        "fincon":           fincon["composite"],
    }
    rows = rows_from_backfill_series(series)
    print(f"Prepared {len(rows)} rows for backfill.")

    client = _supabase_client()
    total = 0
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i:i + _CHUNK_SIZE]
        try:
            resp = client.table("macro_snapshots").upsert(chunk, on_conflict="date").execute()
            total += len(resp.data) if resp.data else 0
            print(f"  Upserted {i + len(chunk)}/{len(rows)} rows...")
        except Exception as e:
            first = chunk[0]["date"]
            last = chunk[-1]["date"]
            print(f"  WARN: chunk {first}..{last} failed: {e}", file=sys.stderr)
    print(f"Backfill complete. {total} rows confirmed.")
```

- [ ] **Step 2: Verify tests still pass (importing build should be safe)**

Run: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
Expected: `7 passed`.

- [ ] **Step 3: Commit**

```bash
git add sync_to_supabase.py
git commit -m "Add cmd_backfill reusing build.py compute pipeline"
```

---

## Task 8: CLI entry point with argparse

**Files:**
- Modify: `sync_to_supabase.py`

- [ ] **Step 1: Add argparse `main` at bottom of `sync_to_supabase.py`**

Append:

```python
import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sync_to_supabase",
        description="Sync computed macro indicators to Supabase.",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("latest", help="Upsert today's snapshot (default).")
    sub.add_parser("backfill", help="Recompute and upsert full daily history.")
    args = parser.parse_args()

    if args.cmd == "backfill":
        cmd_backfill()
    else:
        cmd_latest()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify CLI parses (no creds needed for `--help`)**

Run: `.venv/bin/python sync_to_supabase.py --help`
Expected: usage text listing `latest` and `backfill` subcommands.

- [ ] **Step 3: Verify missing-creds fail-fast on default invocation**

Run: `env -i .venv/bin/python sync_to_supabase.py latest`
Expected: exit code 1, stderr contains "missing required env var(s): SUPABASE_URL, SUPABASE_SERVICE_KEY".

- [ ] **Step 4: Commit**

```bash
git add sync_to_supabase.py
git commit -m "Add argparse CLI for sync_to_supabase"
```

---

## Task 9: Manual smoke test + README example

**Files:**
- Modify: `README.md` (append a section)

- [ ] **Step 1: Apply the schema to your Supabase project**

In Supabase dashboard → SQL Editor, paste the contents of `supabase_schema.sql` and run it.

Verify: in Table Editor, `macro_snapshots` table exists with the 14 columns from the schema.

- [ ] **Step 2: Create `.env` from the template**

```bash
cp .env.example .env
```

Edit `.env` and fill in real `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` from your Supabase project's API settings.

- [ ] **Step 3: Run the daily sync as a smoke test**

```bash
.venv/bin/python sync_to_supabase.py latest
```

Expected: prints `Reading <date>.json...`, `Upserting row for <date>...`, `OK (1 row)`.

In Supabase Table Editor, verify a row exists for today's date with non-null hot columns and a populated `snapshot` JSONB.

- [ ] **Step 4: Run the backfill**

```bash
.venv/bin/python sync_to_supabase.py backfill
```

Expected: ~3,500 rows upserted in chunks of 500. Final line: `Backfill complete. 3493 rows confirmed.` (or similar count).

In Supabase, `select count(*) from macro_snapshots` should return ~3,500. Historical rows have `snapshot` = null; today's row has the full JSONB blob.

- [ ] **Step 5: Re-run latest to confirm idempotency**

```bash
.venv/bin/python sync_to_supabase.py latest
```

Expected: same `OK (1 row)` output. In Supabase, row count for today's date is still 1, but `updated_at` has advanced.

- [ ] **Step 6: Append README section**

Append to `README.md`:

````markdown

## Supabase Sync (optional)

Mirror computed indicators to a Supabase project for reuse in other apps.

### One-time setup

1. Apply `supabase_schema.sql` in your Supabase project's SQL Editor.
2. Copy `.env.example` to `.env` and fill in `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
3. Backfill history: `.venv/bin/python sync_to_supabase.py backfill`

### Daily sync

After each dashboard build:
```
.venv/bin/python build_v2.py && .venv/bin/python sync_to_supabase.py latest
```

### Downstream usage (any other project)

```python
from supabase import create_client
client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
latest = (client.table('macro_snapshots')
                 .select('date,mrmi,mrmi_state,mmi,real_economy')
                 .order('date', desc=True).limit(1).execute()).data[0]
```

The anon key is safe to embed in browser bundles — RLS permits read only.
````

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "Document Supabase sync setup + downstream reader example"
```

---

## Done criteria

- All 7 unit tests pass: `.venv/bin/python -m pytest test_sync_to_supabase.py -v`
- `sync_to_supabase.py --help` lists `latest` and `backfill`
- Schema applied; table visible in Supabase dashboard
- Latest sync produces a row with non-null hot columns + populated `snapshot` JSONB
- Backfill produces ~3,500 rows with null `snapshot`
- Re-running `latest` is idempotent (same row, `updated_at` advances)
- `build.py`, `build_v2.py`, `generate_commentary.py` unchanged
- README has the Supabase Sync section
