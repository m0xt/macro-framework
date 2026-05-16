"""
Sync computed macro indicators to Supabase.

Subcommands:
  doctor   — preflight schema/version/auth before any write
  latest   — preflight, then upsert today's snapshot (default)
  backfill — preflight, then recompute and upsert full daily history

Requires SUPABASE_URL and SUPABASE_SERVICE_KEY in .env or environment.
See docs/superpowers/specs/2026-05-11-supabase-sync-design.md for design.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from supabase import Client, create_client

EXPECTED_SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "schema_version"
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
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


def rows_from_backfill_series(series: dict[str, pd.Series]) -> list[dict[str, Any]]:
    """Build macro_snapshots rows from per-column daily series.

    Skips rows where mrmi is NaN (pre-warmup dates). Derives mrmi_state
    from mrmi sign: LONG if mrmi > 0 else CASH.
    """
    mrmi = series["mrmi"]
    rows: list[dict[str, Any]] = []
    for date in mrmi.index:
        value = mrmi.loc[date]
        if value is None or (isinstance(value, float) and math.isnan(value)):
            continue
        row: dict[str, Any] = {
            "date": pd.Timestamp(date).strftime("%Y-%m-%d"),
            "mrmi_state": "LONG" if value > 0 else "CASH",
            "snapshot": None,
        }
        for col in _HOT_COLUMNS:
            cell = series[col].loc[date]
            row[col] = None if (isinstance(cell, float) and math.isnan(cell)) else float(cell)
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
            "macro_meta schema_version row is missing. Apply supabase_schema.sql before syncing.",
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
            "Apply/update supabase_schema.sql and keep EXPECTED_SCHEMA_VERSION in sync.",
            EXIT_SCHEMA_DRIFT,
        )
    print(f"Supabase preflight OK (schema version {actual_version})")


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


def cmd_doctor() -> None:
    preflight()


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


def cmd_backfill() -> None:
    import build  # reuses fetch + compute pipeline

    if not build.DATA_CACHE.exists():
        print(
            f"error: {build.DATA_CACHE} not found.\n"
            f"Run `.venv/bin/python build.py` first to populate the cache.",
            file=sys.stderr,
        )
        sys.exit(1)
    client = _supabase_client()  # fail-fast on missing creds before heavy compute
    preflight(client)

    print("Loading raw data + recomputing indicators...")
    data = build.fetch_all_data(use_cache=True)
    gii = build.calc_growth_impulse(data)
    fincon = build.calc_financial_conditions(data)
    breadth = build.calc_sector_breadth(data)
    composite = build.calc_composite(gii, fincon, breadth)  # MMI series
    macro_ctx = build.calc_macro_context(data)
    mrmi_combined = build.calc_milk_road_macro_index(composite, macro_ctx)

    series = {
        "mrmi": mrmi_combined["mrmi"],
        "mmi": composite,
        "stress_intensity": mrmi_combined["stress_intensity"],
        "macro_buffer": mrmi_combined["macro_buffer"],
        "real_economy": macro_ctx["real_economy_score"],
        "inflation_dir_pp": macro_ctx["inflation_dir_pp"],
        "core_cpi_yoy_pct": macro_ctx["core_cpi_yoy_pct"],
        "gii_fast": gii["fast"],
        "breadth": breadth["composite"],
        "fincon": fincon["composite"],
    }
    rows = rows_from_backfill_series(series)
    print(f"Prepared {len(rows)} rows for backfill.")

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
            print(f"  WARN[{classified.error_type}]: chunk {first}..{last} failed: {exc}", file=sys.stderr)
    print(f"Backfill complete. {total} rows confirmed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sync_to_supabase",
        description="Sync computed macro indicators to Supabase.",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("doctor", help="Preflight Supabase schema/version/auth without writing.")
    sub.add_parser("latest", help="Upsert today's snapshot (default).")
    sub.add_parser("backfill", help="Recompute and upsert full daily history.")
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
