"""
Sync computed macro indicators to Supabase.

Subcommands:
  doctor   — preflight schema/version/auth before any write
  latest   — preflight, then upsert today's snapshot (default)
  backfill — preflight, then upsert dashboard chart history

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in .env or environment.
See docs/superpowers/specs/2026-05-11-supabase-sync-design.md for design.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

from macro_framework.macro_pipeline import (
    UNIFIED_STRESS_ALPHA,
    UNIFIED_STRESS_BETA,
)
from macro_framework.macro_pipeline import (
    mrmi_posture as build_mrmi_posture,
)

EXPECTED_SCHEMA_VERSION = 5
SCHEMA_VERSION_KEY = "schema_version"
REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_DIR = REPO_ROOT / "snapshots"
DASHBOARD_OUTPUT = REPO_ROOT / "outputs" / "dashboard.html"
_CHUNK_SIZE = 500

EXIT_AUTH = 20
EXIT_NETWORK = 21
EXIT_SCHEMA_DRIFT = 22
EXIT_SUPABASE_UNKNOWN = 23

REQUIRED_MACRO_SNAPSHOTS_COLUMNS = (
    "date",
    "mrmi",
    "mrmi_state",
    "mmi",
    "stress_intensity",
    "stress_score",
    "stress_growth_pressure",
    "stress_inflation_pressure",
    "stress_score_bucket",
    "macro_buffer",
    "real_economy",
    "inflation_dir_pp",
    "core_cpi_yoy_pct",
    "gii_fast",
    "breadth",
    "fincon",
    "snapshot",
    "created_at",
    "updated_at",
)

_HOT_COLUMNS = (
    "mrmi",
    "mmi",
    "stress_intensity",
    "stress_score",
    "stress_growth_pressure",
    "stress_inflation_pressure",
    "stress_score_bucket",
    "macro_buffer",
    "real_economy",
    "inflation_dir_pp",
    "core_cpi_yoy_pct",
    "gii_fast",
    "breadth",
    "fincon",
)


@dataclass
class SupabaseSyncError(RuntimeError):
    """Typed external-integration failure for refresh.sh classification."""

    error_type: str
    message: str
    exit_code: int = EXIT_SUPABASE_UNKNOWN

    def __str__(self) -> str:
        return f"{self.error_type}: {self.message}"


def row_from_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a macro_snapshots row from a daily snapshot dict.

    IMPORTANT: snapshot['mrmi'] is the MMI value (misnamed legacy field).
    The true MRMI headline is snapshot['mrmi_combined']['value'].
    """
    mrmi_c = snapshot["mrmi_combined"]
    macro = snapshot["macro"]
    components = snapshot["components"]
    value = mrmi_c["value"]
    growth_weakness = mrmi_c.get("growth_weakness")
    inflation_pressure = mrmi_c.get("inflation_pressure_raw")
    return {
        "date": snapshot["date"],
        "mrmi": value,
        # Existing Supabase schema v5 only accepts LONG/CASH here. The current
        # three-state posture remains available in the dashboard snapshot JSON;
        # frontend code should derive CAUTION from `mrmi` thresholds or read
        # `snapshot.mrmi_combined.state`.
        "mrmi_state": "CASH" if build_mrmi_posture(value) == "CASH" else "LONG",
        "mmi": mrmi_c["momentum"],
        # New unified-stress semantics: normalized 0–1 stress_score / 10.
        "stress_intensity": mrmi_c["stress_intensity"],
        # New unified-stress semantics: normalized 0–10 production stress score.
        "stress_score": mrmi_c.get("stress_score"),
        # Column name unchanged; value is α·g contribution before normalization.
        "stress_growth_pressure": growth_weakness * UNIFIED_STRESS_ALPHA if growth_weakness is not None else None,
        # Column name unchanged; value is β·i contribution before normalization.
        "stress_inflation_pressure": inflation_pressure * UNIFIED_STRESS_BETA if inflation_pressure is not None else None,
        # New round-boundary bucket: calm/watch/building/elevated.
        "stress_score_bucket": mrmi_c.get("stress_score_bucket"),
        "macro_buffer": mrmi_c["macro_buffer"],
        "real_economy": macro["real_economy_score"],
        "inflation_dir_pp": macro["inflation_dir_pp"],
        "core_cpi_yoy_pct": macro["core_cpi_yoy_pct"],
        "gii_fast": components["gii_fast"],
        "breadth": components["breadth"],
        "fincon": components["fincon"],
        "snapshot": snapshot,
    }


def rows_from_backfill_series(series: dict[str, pd.Series]) -> list[dict[str, Any]]:
    """Build recomputed macro_snapshots rows from per-column daily series.

    Prefer `rows_from_snapshot_files()` for product/frontend history: it mirrors
    the exact daily dashboard snapshots. This helper exists only for analytical
    recompute workflows where no point-in-time snapshot file exists.
    """
    mrmi = series["mrmi"]
    rows: list[dict[str, Any]] = []
    for date in mrmi.index:
        value = mrmi.loc[date]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        row: dict[str, Any] = {
            "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
            "mrmi_state": "CASH" if build_mrmi_posture(value) == "CASH" else "LONG",
            "snapshot": None,
        }
        for col in _HOT_COLUMNS:
            cell = series[col].loc[date]
            if isinstance(cell, float) and math.isnan(cell):
                row[col] = None
            elif col == "stress_score_bucket":
                row[col] = str(cell) if cell is not None else None
            else:
                row[col] = float(cell)
        rows.append(row)
    return rows


def load_credentials() -> tuple[str, str]:
    """Load Supabase URL + service key from .env or environment.

    Exits with code 20 and a clear error message if either is missing.
    """
    load_dotenv()  # silently no-op if .env absent
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    missing = [name for name, val in (("SUPABASE_URL", url), ("SUPABASE_SERVICE_KEY", key)) if not val]
    if missing:
        print(
            "error[supabase-auth]: missing required env var(s): "
            f"{', '.join(missing)}\nSet them in .env (copy .env.example) or export them in your shell.",
            file=sys.stderr,
        )
        sys.exit(EXIT_AUTH)
    return url, key


def _supabase_client() -> Client:
    url, key = load_credentials()
    return create_client(url, key)


def classify_supabase_exception(exc: Exception, default: str = "supabase-network") -> SupabaseSyncError:
    text = str(exc)
    lowered = text.lower()
    if any(token in lowered for token in ("jwt", "unauthorized", "401", "403", "permission", "invalid api key")):
        return SupabaseSyncError("supabase-auth", text, EXIT_AUTH)
    if any(token in lowered for token in ("column", "schema", "relation", "table", "constraint", "macro_meta")):
        return SupabaseSyncError("supabase-schema-drift", text, EXIT_SCHEMA_DRIFT)
    if any(token in lowered for token in ("timeout", "connection", "network", "dns", "temporarily unavailable")):
        return SupabaseSyncError("supabase-network", text, EXIT_NETWORK)
    if default == "supabase-schema-drift":
        return SupabaseSyncError("supabase-schema-drift", text, EXIT_SCHEMA_DRIFT)
    return SupabaseSyncError(default, text, EXIT_NETWORK if default == "supabase-network" else EXIT_SUPABASE_UNKNOWN)


def _response_data(resp: Any) -> Any:
    return getattr(resp, "data", None)


def remote_schema_version(client: Client) -> int:
    """Read the schema sentinel from macro_meta."""
    try:
        resp = (
            client.table("macro_meta")
            .select("key,value")
            .eq("key", SCHEMA_VERSION_KEY)
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise classify_supabase_exception(exc, default="supabase-schema-drift") from exc

    data = _response_data(resp) or []
    if not data:
        raise SupabaseSyncError(
            "supabase-schema-drift",
            "macro_meta schema_version row is missing. Apply migrations/ before syncing.",
            EXIT_SCHEMA_DRIFT,
        )
    value = data[0].get("value") if isinstance(data[0], dict) else None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SupabaseSyncError(
            "supabase-schema-drift",
            f"macro_meta schema_version value is not an integer: {value!r}",
            EXIT_SCHEMA_DRIFT,
        ) from exc


def check_required_columns(client: Client) -> None:
    """Ask PostgREST for every required column; missing columns fail here."""
    try:
        (
            client.table("macro_snapshots")
            .select(",".join(REQUIRED_MACRO_SNAPSHOTS_COLUMNS))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        raise classify_supabase_exception(exc, default="supabase-schema-drift") from exc


def preflight(client: Client | None = None) -> None:
    """Validate remote schema version and required macro_snapshots columns."""
    client = client or _supabase_client()
    check_required_columns(client)
    actual_version = remote_schema_version(client)
    if actual_version != EXPECTED_SCHEMA_VERSION:
        raise SupabaseSyncError(
            "supabase-schema-drift",
            f"remote schema version {actual_version} != expected {EXPECTED_SCHEMA_VERSION}. "
            "Apply/update migrations/ and keep EXPECTED_SCHEMA_VERSION in sync.",
            EXIT_SCHEMA_DRIFT,
        )
    print(f"Supabase preflight OK (schema version {actual_version})")


def _latest_snapshot_path() -> Path:
    if not SNAPSHOT_DIR.exists():
        print(
            f"error: no snapshot directory at {SNAPSHOT_DIR}.\n"
            f"Run `uv run python -m macro_framework.build` first to produce a snapshot.",
            file=sys.stderr,
        )
        sys.exit(1)
    snapshots = sorted(SNAPSHOT_DIR.glob("*.json"))
    if not snapshots:
        print(
            f"error: no snapshot JSON files in {SNAPSHOT_DIR}.\n"
            f"Run `uv run python -m macro_framework.build` first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return snapshots[-1]


def cmd_doctor() -> None:
    preflight()


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


def cmd_latest() -> None:
    client = _supabase_client()  # fail-fast on missing creds
    preflight(client)
    path = _latest_snapshot_path()
    print(f"Reading {path.name}...")
    with open(path) as f:
        snapshot = json.load(f)
    row = row_from_snapshot(snapshot)
    print(f"Upserting row for {row['date']}...")
    try:
        resp = client.table("macro_snapshots").upsert(row, on_conflict="date").execute()
    except Exception as exc:
        raise classify_supabase_exception(exc) from exc
    if not resp.data:
        raise SupabaseSyncError(
            "supabase-network",
            f"upsert returned empty response: {resp}",
            EXIT_NETWORK,
        )
    print(f"OK ({len(resp.data)} row)")
    _upsert_backtest(client)


def rows_from_snapshot_files(snapshot_dir: Path = SNAPSHOT_DIR) -> list[dict[str, Any]]:
    """Build Supabase rows from the exact snapshots used by the dashboard.

    This is the product/frontend source of truth: one hot Supabase value per
    dashboard indicator, with the JSONB blob retained for audit. Older legacy
    snapshots that predate the current `mrmi_combined` / `macro` schema are
    skipped because they cannot populate the current frontend contract.
    """
    rows: list[dict[str, Any]] = []
    for path in sorted(snapshot_dir.glob("*.json")):
        with open(path) as f:
            snapshot = json.load(f)
        if "mrmi_combined" not in snapshot or "macro" not in snapshot:
            print(f"Skipping {path.name}: legacy snapshot schema", file=sys.stderr)
            continue
        rows.append(row_from_snapshot(snapshot))
    return rows


def rows_from_dashboard_output(path: Path = DASHBOARD_OUTPUT) -> list[dict[str, Any]]:
    """Build Supabase rows from the generated dashboard chart payload.

    The website hot fields should match the same `CHART_DATA` arrays rendered in
    `outputs/dashboard.html`. This avoids schema changes and avoids having a
    second historical recompute path drift away from the actual dashboard.
    """
    if not path.exists():
        print(f"error: dashboard output not found at {path}. Run build first.", file=sys.stderr)
        sys.exit(1)
    html = path.read_text()
    match = re.search(r"const CHART_DATA = (\{.*?\});\n", html, re.S)
    if not match:
        print(f"error: CHART_DATA payload not found in {path}", file=sys.stderr)
        sys.exit(1)
    chart = json.loads(match.group(1))

    dates = chart["dates"]
    mrmi_c = chart.get("mrmi_combined") or {}
    macro = chart.get("macro") or {}
    drivers = chart.get("drivers") or {}

    def val(series: Any, i: int) -> Any:
        if isinstance(series, dict):
            series = series.get("values")
        if series is None or i >= len(series):
            return None
        return series[i]

    rows: list[dict[str, Any]] = []
    for i, date in enumerate(dates):
        mrmi = val(mrmi_c.get("value"), i)
        if mrmi is None:
            continue
        growth_weakness = val(mrmi_c.get("growth_weakness"), i)
        inflation_pressure = val(mrmi_c.get("inflation_pressure_raw"), i)
        rows.append(
            {
                "date": date,
                "mrmi": mrmi,
                "mrmi_state": "CASH" if build_mrmi_posture(mrmi) == "CASH" else "LONG",
                "mmi": val(mrmi_c.get("momentum"), i),
                "stress_intensity": val(mrmi_c.get("stress_intensity"), i),
                "stress_score": val(mrmi_c.get("stress_score"), i),
                "stress_growth_pressure": growth_weakness * UNIFIED_STRESS_ALPHA if growth_weakness is not None else None,
                "stress_inflation_pressure": inflation_pressure * UNIFIED_STRESS_BETA if inflation_pressure is not None else None,
                "stress_score_bucket": val(mrmi_c.get("stress_score_bucket"), i),
                "macro_buffer": val(mrmi_c.get("macro_buffer"), i),
                "real_economy": val(macro.get("real_economy_score"), i),
                "inflation_dir_pp": val(macro.get("inflation_dir_pp"), i),
                "core_cpi_yoy_pct": val(macro.get("core_cpi_yoy_pct"), i),
                "gii_fast": val(drivers.get("gii_fast"), i),
                "breadth": val(drivers.get("breadth"), i),
                "fincon": val(drivers.get("fincon"), i),
                "snapshot": None,
            }
        )
    return rows


def _upsert_rows(client: Client, rows: list[dict[str, Any]], *, label: str) -> None:
    total = 0
    for i in range(0, len(rows), _CHUNK_SIZE):
        chunk = rows[i : i + _CHUNK_SIZE]
        try:
            resp = client.table("macro_snapshots").upsert(chunk, on_conflict="date").execute()
            total += len(resp.data) if resp.data else 0
            print(f"  Upserted {i + len(chunk)}/{len(rows)} rows...")
        except Exception as exc:
            first = chunk[0]["date"]
            last = chunk[-1]["date"]
            classified = classify_supabase_exception(exc)
            print(f"  WARN[{classified.error_type}]: {label} chunk {first}..{last} failed: {exc}", file=sys.stderr)
    print(f"{label} complete. {total} rows confirmed.")


def cmd_backfill() -> None:
    client = _supabase_client()  # fail-fast on missing creds
    preflight(client)
    rows = rows_from_dashboard_output()
    print(f"Prepared {len(rows)} dashboard chart rows for backfill.")
    if not rows:
        print(f"error: no dashboard chart rows found in {DASHBOARD_OUTPUT}", file=sys.stderr)
        sys.exit(1)
    _upsert_rows(client, rows, label="Dashboard chart backfill")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sync_to_supabase",
        description="Sync computed macro indicators to Supabase.",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("doctor", help="Preflight Supabase schema/version/auth without writing.")
    sub.add_parser("latest", help="Upsert today's snapshot (default).")
    sub.add_parser("backfill", help="Upsert dashboard chart history into Supabase.")
    args = parser.parse_args()

    try:
        if args.cmd == "doctor":
            cmd_doctor()
        elif args.cmd == "backfill":
            cmd_backfill()
        else:
            cmd_latest()
    except SupabaseSyncError as exc:
        print(f"error[{exc.error_type}]: {exc.message}", file=sys.stderr)
        sys.exit(exc.exit_code)


if __name__ == "__main__":
    main()
