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
