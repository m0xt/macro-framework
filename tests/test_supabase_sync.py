from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import macro_framework.sync_to_supabase as sync_to_supabase  # noqa: E402


class FakeQuery:
    def __init__(self, client: FakeClient, table: str) -> None:
        self.client = client
        self.table = table
        self.selected = ""
        self.payload: Any = None

    def select(self, columns: str) -> FakeQuery:
        self.selected = columns
        return self

    def eq(self, _key: str, _value: str) -> FakeQuery:
        return self

    def limit(self, _limit: int) -> FakeQuery:
        return self

    def upsert(self, payload: Any, on_conflict: str | None = None) -> FakeQuery:
        self.payload = payload
        self.client.upsert_on_conflict = on_conflict
        return self

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
        if self.table == "macro_backtest":
            if not self.client.backtest_table_exists:
                raise RuntimeError("relation macro_backtest does not exist")
            self.client.backtest_upserts.append(self.payload)
            return SimpleNamespace(data=[self.payload])
        raise RuntimeError(f"relation {self.table} does not exist")


class FakeClient:
    def __init__(self, *, schema_version: int = sync_to_supabase.EXPECTED_SCHEMA_VERSION, columns: set[str] | None = None) -> None:
        self.schema_version = schema_version
        self.columns = columns or set(sync_to_supabase.REQUIRED_MACRO_SNAPSHOTS_COLUMNS)
        self.upsert_on_conflict: str | None = None
        self.backtest_table_exists = True
        self.backtest_upserts: list[Any] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def test_preflight_matching_schema_version_ok(capsys: pytest.CaptureFixture[str]) -> None:
    sync_to_supabase.preflight(FakeClient())

    assert "Supabase preflight OK" in capsys.readouterr().out


def test_preflight_mismatching_schema_version_clear_error() -> None:
    with pytest.raises(sync_to_supabase.SupabaseSyncError) as exc:
        sync_to_supabase.preflight(FakeClient(schema_version=sync_to_supabase.EXPECTED_SCHEMA_VERSION + 1))

    assert exc.value.error_type == "supabase-schema-drift"
    assert "remote schema version" in exc.value.message
    assert str(sync_to_supabase.EXPECTED_SCHEMA_VERSION) in exc.value.message


def test_preflight_missing_column_clear_error() -> None:
    columns = set(sync_to_supabase.REQUIRED_MACRO_SNAPSHOTS_COLUMNS)
    columns.remove("macro_buffer")

    with pytest.raises(sync_to_supabase.SupabaseSyncError) as exc:
        sync_to_supabase.preflight(FakeClient(columns=columns))

    assert exc.value.error_type == "supabase-schema-drift"
    assert "macro_buffer" in exc.value.message


def test_refresh_sh_isolates_supabase_failure_and_still_commits(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    ops_lib = home / "ops" / "lib"
    ops_lib.mkdir(parents=True)
    log_path = tmp_path / "commit.log"
    status_path = tmp_path / "status.json"

    (ops_lib / "cron-wrapper.sh").write_text(
        """
_CRON_WRAPPER_START_TS=2026-06-02T15:04:43Z
_CRON_WRAPPER_START_EPOCH=1780412683
cron_wrapper_pull() { echo pull >> "$TEST_LOG"; }
cron_wrapper_commit_outputs() { echo commit_outputs "$@" >> "$TEST_LOG"; }
trap 'mkdir -p "$(dirname "$STATUS_FILE")"; printf '"'"'{"status":"ok","summary":"%s"}'"'"' "$SUCCESS_SUMMARY" > "$STATUS_FILE"' EXIT
""".lstrip()
    )

    (ops_lib / "write_status.py").write_text(
        """#!/usr/bin/env python3
import argparse, json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--out')
parser.add_argument('--summary')
parser.add_argument('--project')
parser.add_argument('--start-ts')
parser.add_argument('--duration-sec')
parser.add_argument('--status')
args = parser.parse_args()
Path(args.out).write_text(json.dumps({'status': args.status, 'summary': args.summary}))
"""
    )

    fake_python = tmp_path / "python"
    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$TEST_LOG"
case "$*" in
  "-m macro_framework.build --no-cache --skip-briefs") exit 0 ;;
  "-m macro_framework.build_index_page") exit 0 ;;
  "-m macro_framework.sync_to_supabase latest") echo 'schema mismatch' >&2; exit 22 ;;
  *) exit 99 ;;
esac
"""
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "PYTHON_BIN": str(fake_python),
        "TEST_LOG": str(log_path),
        "STATUS_FILE": str(status_path),
        "SYNC_LOG": str(tmp_path / "supabase.log"),
    })

    proc = subprocess.run(
        ["bash", "scripts/refresh.sh"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert proc.returncode == 0, proc.stderr
    log = log_path.read_text()
    assert "-m macro_framework.build --no-cache --skip-briefs" in log
    assert "-m macro_framework.build_index_page" in log
    assert "-m macro_framework.sync_to_supabase latest" in log
    assert "commit_outputs" in log
    assert "docs/index.html" in log
    assert "supabase-schema-drift" in proc.stderr
    status = json.loads(status_path.read_text())
    assert status["summary"] == "refresh ok, supabase sync failed (supabase-schema-drift)"


def test_refresh_sh_briefs_only_forces_briefs_then_rerenders(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[1]
    home = tmp_path / "home"
    ops_lib = home / "ops" / "lib"
    ops_lib.mkdir(parents=True)
    log_path = tmp_path / "commit.log"
    status_path = tmp_path / "status.json"

    (ops_lib / "cron-wrapper.sh").write_text(
        """
_CRON_WRAPPER_START_TS=2026-06-02T15:04:43Z
_CRON_WRAPPER_START_EPOCH=1780412683
cron_wrapper_pull() { echo pull >> "$TEST_LOG"; }
cron_wrapper_commit_outputs() { echo commit_outputs "$@" >> "$TEST_LOG"; }
trap 'mkdir -p "$(dirname "$STATUS_FILE")"; printf '"'"'{"status":"ok","summary":"%s"}'"'"' "$SUCCESS_SUMMARY" > "$STATUS_FILE"' EXIT
""".lstrip()
    )

    (ops_lib / "write_status.py").write_text(
        """#!/usr/bin/env python3
import argparse, json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--out')
parser.add_argument('--summary')
parser.add_argument('--project')
parser.add_argument('--start-ts')
parser.add_argument('--duration-sec')
parser.add_argument('--status')
args = parser.parse_args()
Path(args.out).write_text(json.dumps({'status': args.status, 'summary': args.summary}))
"""
    )

    fake_python = tmp_path / "python"
    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$TEST_LOG"
case "$*" in
  "-m macro_framework.weekly_briefs --force") exit 0 ;;
  "-m macro_framework.build --skip-briefs") exit 0 ;;
  "-m macro_framework.build_index_page") exit 0 ;;
  "-m macro_framework.sync_to_supabase latest") echo 'sync ok'; exit 0 ;;
  *) exit 99 ;;
esac
"""
    )
    fake_python.chmod(0o755)

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "PYTHON_BIN": str(fake_python),
        "TEST_LOG": str(log_path),
        "STATUS_FILE": str(status_path),
        "SYNC_LOG": str(tmp_path / "supabase.log"),
    })

    proc = subprocess.run(
        ["bash", "scripts/refresh.sh", "--briefs-only"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert proc.returncode == 0, proc.stderr
    log = log_path.read_text()
    assert "-m macro_framework.weekly_briefs --force" in log
    assert "-m macro_framework.build --skip-briefs" in log
    assert "-m macro_framework.sync_to_supabase latest" in log
    assert "commit_outputs" in log
    assert "briefs/" in log
    status = json.loads(status_path.read_text())
    assert status["summary"] == "refresh ok (briefs + dashboard + supabase sync)"


def test_refresh_if_et_time_gate_matches_new_york_wall_clock() -> None:
    repo = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update({
        "MACRO_REFRESH_ET_WEEKDAY": "2",
        "MACRO_REFRESH_ET_HOUR": "16",
        "MACRO_REFRESH_ET_MINUTE": "00",
        "MACRO_REFRESH_ET_STAMP": "2026-06-02 16:00 EDT",
        "MACRO_REFRESH_DRY_RUN": "1",
    })

    proc = subprocess.run(
        ["bash", "scripts/refresh-if-et-time.sh", "data"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert proc.returncode == 0
    assert "ET gate matched for data at 2026-06-02 16:00 EDT" in proc.stdout

    env["MACRO_REFRESH_ET_HOUR"] = "15"
    proc = subprocess.run(
        ["bash", "scripts/refresh-if-et-time.sh", "data"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert proc.returncode == 0
    assert "ET gate skipped data" in proc.stdout


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
