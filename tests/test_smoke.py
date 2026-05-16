"""Smoke tests for macro-framework's flat module layout and MRMI invariants.

This intentionally does not fix the known doc/code drift or retired research
scripts. Known-broken Macro Seasons research imports are xfailed so the suite is
useful today while still surfacing the follow-up work.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_MODULES = ["build", "macro_pipeline", "weekly_briefs", "sync_to_supabase"]
ANALYZE_MODULES = sorted(
    [f"research.{p.stem}" for p in (ROOT / "research").glob("analyze_*.py")]
    + [f"research.archive.{p.stem}" for p in (ROOT / "research" / "archive").glob("analyze_*.py")]
)
BROKEN_ANALYZE_MODULES = {
    "research.archive.analyze_conviction_score": "retired Macro Seasons API — see AUDIT-MACRO-FRAMEWORK.md",
    "research.archive.analyze_seasons_conditioning": "retired Macro Seasons API — see AUDIT-MACRO-FRAMEWORK.md",
    "research.analyze_alpha_strategies": "research import drift surfaced by smoke baseline",
    "research.analyze_multi_signal": "research import drift surfaced by smoke baseline",
}
ENTRYPOINT_MODULES = ["build", "weekly_briefs", "sync_to_supabase"]


def _import_module(name: str) -> ModuleType:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module(name)


def _has_main_guard(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    return any(isinstance(node, ast.If) and "__main__" in ast.unparse(node.test) for node in tree.body)


# ── (a) importability smoke ─────────────────────────────────────────────────

@pytest.mark.parametrize("module_name", PRODUCTION_MODULES)
def test_production_modules_import(module_name: str) -> None:
    _import_module(module_name)


def _analyze_param(module_name: str) -> pytest.ParameterSet | str:
    if module_name in BROKEN_ANALYZE_MODULES:
        return pytest.param(
            module_name,
            marks=pytest.mark.xfail(reason=BROKEN_ANALYZE_MODULES[module_name], strict=False),
        )
    return module_name


@pytest.mark.parametrize("module_name", [_analyze_param(name) for name in ANALYZE_MODULES])
def test_analyze_modules_import_or_known_xfail(module_name: str) -> None:
    _import_module(module_name)


# ── (b) entry-point dry-run ─────────────────────────────────────────────────

def test_entrypoint_scripts_have_main_guard() -> None:
    missing = [name for name in ENTRYPOINT_MODULES if not _has_main_guard(ROOT / f"{name}.py")]
    assert missing == []


def test_sync_to_supabase_help_does_not_touch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    sync_to_supabase = _import_module("sync_to_supabase")
    monkeypatch.setattr(sys, "argv", ["sync_to_supabase.py", "--help"])
    with pytest.raises(SystemExit) as exc:
        sync_to_supabase.main()
    assert exc.value.code == 0


def test_weekly_briefs_dry_run_without_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weekly_briefs = _import_module("weekly_briefs")
    monkeypatch.setattr(weekly_briefs, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(weekly_briefs, "BRIEFS_DIR", tmp_path / "briefs")
    monkeypatch.setattr(weekly_briefs.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(weekly_briefs, "_run_claude", lambda *args, **kwargs: "brief text")

    # No snapshots means the orchestrator exits without shelling out to Claude.
    assert weekly_briefs.generate_all_briefs(force=True) is False


# ── (c) MRMI formula invariants ─────────────────────────────────────────────

def test_mrmi_formula_matches_documented_equation() -> None:
    macro_pipeline = _import_module("macro_pipeline")
    idx = pd.date_range("2026-01-01", periods=4, freq="D")
    momentum = pd.Series([0.2, -0.1, 0.8, 0.0], index=idx)
    re_score = pd.Series([0.5, -0.5, -2.0, -0.25], index=idx)
    inf_dir = pd.Series([-0.2, 0.4, 2.0, 0.0], index=idx)
    buffer_size = 1.5
    threshold = 0.25

    out = macro_pipeline.calc_milk_road_macro_index(
        momentum,
        {"real_economy_score": re_score, "inflation_dir_pp": inf_dir},
        buffer_size=buffer_size,
        threshold=threshold,
    )

    expected_stress = ((-re_score).clip(lower=0) * inf_dir.clip(lower=0)).clip(upper=1.0)
    expected_buffer = buffer_size * (1.0 - expected_stress)
    expected_mrmi = momentum + expected_buffer - threshold

    pd.testing.assert_series_equal(out["stress_intensity"], expected_stress)
    pd.testing.assert_series_equal(out["macro_buffer"], expected_buffer)
    pd.testing.assert_series_equal(out["mrmi"], expected_mrmi)


def test_stress_intensity_is_clipped_to_zero_one() -> None:
    macro_pipeline = _import_module("macro_pipeline")
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    momentum = pd.Series(np.zeros(len(idx)), index=idx)
    re_score = pd.Series([10.0, -10.0, -0.5, 0.0, -2.0], index=idx)
    inf_dir = pd.Series([10.0, 10.0, -5.0, 1.0, 0.75], index=idx)

    out = macro_pipeline.calc_milk_road_macro_index(
        momentum,
        {"real_economy_score": re_score, "inflation_dir_pp": inf_dir},
    )

    stress = out["stress_intensity"]
    assert (stress >= 0).all()
    assert (stress <= 1).all()
    assert stress.iloc[1] == pytest.approx(1.0)
    assert stress.iloc[2] == pytest.approx(0.0)


def test_prepare_chart_data_uses_release_lagged_macro_values() -> None:
    macro_pipeline = _import_module("macro_pipeline")
    idx = pd.date_range("2025-01-01", periods=430, freq="D")
    data = pd.DataFrame({
        "PCEC96": np.linspace(100.0, 140.0, len(idx)),
        "UNRATE": np.linspace(4.0, 4.5, len(idx)),
        "RPI": np.linspace(100.0, 130.0, len(idx)),
        "GDPNOW": np.linspace(1.0, 2.0, len(idx)),
        "CPILFESL": np.linspace(100.0, 110.0, len(idx)),
        "CPIAUCSL": np.linspace(100.0, 111.0, len(idx)),
        "^GSPC": np.linspace(5000.0, 5100.0, len(idx)),
    }, index=idx)
    gii = pd.DataFrame({"fast": np.zeros(len(idx))}, index=idx)
    fincon = pd.DataFrame({"composite": np.zeros(len(idx))}, index=idx)
    breadth = pd.DataFrame({"composite": np.zeros(len(idx))}, index=idx)
    business_cycle = pd.DataFrame({
        "composite": np.zeros(len(idx)),
        "real_economy": np.zeros(len(idx)),
        "credit_money": np.zeros(len(idx)),
        "markets": np.zeros(len(idx)),
        "labor": np.zeros(len(idx)),
    }, index=idx)
    inflation_ctx = pd.DataFrame({"composite": np.zeros(len(idx))}, index=idx)
    composite = pd.Series(np.zeros(len(idx)), index=idx)
    macro_ctx = macro_pipeline.calc_macro_context(data, lookback_years=1, apply_release_lags=True)
    mrmi = macro_pipeline.calc_milk_road_macro_index(composite, macro_ctx)

    chart_json, _season = macro_pipeline.prepare_chart_data(
        data, composite, gii, fincon, breadth, business_cycle, inflation_ctx, macro_ctx, mrmi
    )
    chart = json.loads(chart_json)
    pce_yoy = chart["macro_ctx"]["raw"]["pce_yoy"]

    # PCE has a 60-day release lag: the first year-over-year value from source
    # day 365 must not be visible until chart day 425.
    assert pce_yoy[365] is None
    assert pce_yoy[425] == pytest.approx(round(float(macro_ctx["real_economy_raw"]["pce_yoy"].iloc[425]), 4))


def test_save_snapshot_schema_uses_actual_current_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    macro_pipeline = _import_module("macro_pipeline")
    idx = pd.date_range("2026-01-01", periods=3, freq="D")
    monkeypatch.setattr(macro_pipeline, "SNAPSHOT_DIR", tmp_path)

    data = pd.DataFrame({
        "^GSPC": [5000.0, 5010.0, 5020.0],
        "DGS10": [4.0, 4.1, 4.2],
    }, index=idx)
    composite = pd.Series([0.1, 0.2, 0.3], index=idx)
    gii = pd.DataFrame({"fast": [0.1, 0.2, 0.3]}, index=idx)
    fincon = pd.DataFrame({"composite": [0.4, 0.5, 0.6]}, index=idx)
    breadth = pd.DataFrame({"composite": [0.7, 0.8, 0.9]}, index=idx)
    biz_cycle = pd.DataFrame({
        "composite": [0.1, 0.2, 0.3],
        "real_economy": [0.2, 0.3, 0.4],
        "credit_money": [0.3, 0.4, 0.5],
        "markets": [0.4, 0.5, 0.6],
        "labor": [0.5, 0.6, 0.7],
    }, index=idx)
    infl_ctx = pd.DataFrame({"composite": [0.2, 0.3, 0.4]}, index=idx)
    macro_ctx = {
        "real_economy_score": pd.Series([0.1, -0.2, -0.3], index=idx),
        "real_economy_components": pd.DataFrame({"pce": [0.1, 0.2, 0.3]}, index=idx),
        "inflation_dir_pp": pd.Series([0.1, 0.2, 0.3], index=idx),
        "core_cpi_yoy_pct": pd.Series([2.0, 2.1, 2.2], index=idx),
        "real_economy_raw": {"pce_yoy": pd.Series([1.0, 1.1, 1.2], index=idx)},
    }
    mrmi_combined = macro_pipeline.calc_milk_road_macro_index(composite, macro_ctx)

    path = macro_pipeline.save_snapshot(
        data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, mrmi_combined
    )
    snapshot = json.loads(path.read_text())

    assert {
        "date",
        "build_time_utc",
        "mrmi",
        "components",
        "mrci",
        "inflation",
        "mrmi_combined",
        "macro",
        "underliers",
    } <= snapshot.keys()
    assert {"gii_fast", "fincon", "breadth"} <= snapshot["components"].keys()
    assert {"value", "state", "momentum", "stress_intensity", "macro_buffer", "buffer_size"} <= snapshot[
        "mrmi_combined"
    ].keys()
    assert {"real_economy_score", "inflation_dir_pp", "core_cpi_yoy_pct", "raw"} <= snapshot[
        "macro"
    ].keys()


def _function_source(module_text: str, name: str, next_name: str) -> str:
    return module_text.split(f"def {name}", 1)[1].split(f"def {next_name}", 1)[0]


def test_breadth_lookback_docs_match_code() -> None:
    source = (ROOT / "macro_pipeline.py").read_text()
    calc_sector_src = _function_source(source, "calc_sector_breadth", "calc_business_cycle")
    code_lookback = int(calc_sector_src.split("LOOKBACK =", 1)[1].split("#", 1)[0].strip())

    docs = "\n".join((ROOT / name).read_text() for name in ("README.md", "CLAUDE.md", "GUIDE.md"))
    assert code_lookback == 90
    assert f"lookback={code_lookback}" in docs or f"lookback = {code_lookback}" in docs
    assert "over 90 days" in docs


def test_documented_mrmi_parameters_are_locked_to_code() -> None:
    source = (ROOT / "macro_pipeline.py").read_text()
    mrmi_src = _function_source(source, "calc_milk_road_macro_index", "calc_macro_context")
    assert "buffer_size: float = 1.0" in mrmi_src
    assert "threshold: float = 0.5" in mrmi_src
    assert "stress_intensity = stress_raw.clip(upper=1.0)" in mrmi_src

    docs = "\n".join((ROOT / name).read_text() for name in ("README.md", "CLAUDE.md", "GUIDE.md"))
    assert "buffer_size=1.0" in docs or "buffer_size = 1.0" in docs
    assert "threshold=0.5" in docs or "threshold = 0.5" in docs
    assert "[0, 1]" in docs


def test_documented_release_lags_are_locked_to_code() -> None:
    macro_pipeline = _import_module("macro_pipeline")
    assert macro_pipeline.RELEASE_LAGS_DAYS == {
        "PCEC96": 60,
        "UNRATE": 35,
        "RPI": 60,
        "GDPNOW": 0,
        "CPILFESL": 45,
    }

    docs = "\n".join((ROOT / name).read_text() for name in ("README.md", "CLAUDE.md", "GUIDE.md"))
    for snippet in ("PCE/RPI 60d", "unemployment 35d", "Core CPI 45d", "GDPNow 0d"):
        assert snippet in docs
