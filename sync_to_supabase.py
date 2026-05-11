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
