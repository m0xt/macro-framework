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
        if self.table == "macro_top_brief":
            if not self.client.brief_table_exists:
                raise RuntimeError("relation macro_top_brief does not exist")
            self.client.brief_upserts.append(self.payload)
            return SimpleNamespace(data=[self.payload])
        raise RuntimeError(f"relation {self.table} does not exist")


class FakeClient:
    def __init__(self, *, schema_version: int = sync_to_supabase.EXPECTED_SCHEMA_VERSION, columns: set[str] | None = None) -> None:
        self.schema_version = schema_version
        self.columns = columns or set(sync_to_supabase.REQUIRED_MACRO_SNAPSHOTS_COLUMNS)
        self.upsert_on_conflict: str | None = None
        self.brief_table_exists = True
        self.brief_upserts: list[Any] = []

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
cron_wrapper_pull() { echo pull >> \"$TEST_LOG\"; }
cron_wrapper_commit_outputs() { echo commit_outputs \"$@\" >> \"$TEST_LOG\"; }
trap 'mkdir -p "$(dirname "$STATUS_FILE")"; printf "{\\\"status\\\":\\\"ok\\\",\\\"summary\\\":\\\"%s\\\"}" "$SUCCESS_SUMMARY" > "$STATUS_FILE"' EXIT
""".lstrip()
    )

    fake_python = tmp_path / "python"
    fake_python.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
echo "$*" >> "$TEST_LOG"
case "$*" in
  "-m macro_framework.build --no-cache") exit 0 ;;
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
    assert "-m macro_framework.build --no-cache" in log
    assert "-m macro_framework.build_index_page" in log
    assert "-m macro_framework.sync_to_supabase latest" in log
    assert "commit_outputs" in log
    assert "docs/index.html" in log
    assert "supabase-schema-drift" in proc.stderr
    status = json.loads(status_path.read_text())
    assert status["summary"] == "refresh ok, supabase sync failed (supabase-schema-drift)"


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
