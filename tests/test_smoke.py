"""Smoke tests for macro-framework's src/macro_framework package layout and MRMI invariants.

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
SRC = ROOT / "src"
PACKAGE_DIR = SRC / "macro_framework"
PRODUCTION_MODULES = [
    "macro_framework.backtest_production",
    "macro_framework.build",
    "macro_framework.build_index_page",
    "macro_framework.cost",
    "macro_framework.macro_pipeline",
    "macro_framework.weekly_briefs",
    "macro_framework.sync_to_supabase",
]
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
ENTRYPOINT_MODULES = ["build", "build_index_page", "weekly_briefs", "sync_to_supabase", "backtest_production"]


def _import_module(name: str) -> ModuleType:
    # Production code should resolve through the installed src package; top-level
    # research scripts remain import-smoked as loose repo-root modules.
    for path in (ROOT, SRC):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
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
    missing = [name for name in ENTRYPOINT_MODULES if not _has_main_guard(PACKAGE_DIR / f"{name}.py")]
    assert missing == []


def test_sync_to_supabase_help_does_not_touch_network(monkeypatch: pytest.MonkeyPatch) -> None:
    sync_to_supabase = _import_module("macro_framework.sync_to_supabase")
    monkeypatch.setattr(sys, "argv", ["python -m macro_framework.sync_to_supabase", "--help"])
    with pytest.raises(SystemExit) as exc:
        sync_to_supabase.main()
    assert exc.value.code == 0


def test_weekly_briefs_dry_run_without_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    weekly_briefs = _import_module("macro_framework.weekly_briefs")
    monkeypatch.setattr(weekly_briefs, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(weekly_briefs, "BRIEFS_DIR", tmp_path / "briefs")
    monkeypatch.setattr(weekly_briefs.shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(weekly_briefs, "_run_claude", lambda *args, **kwargs: "brief text")

    # No snapshots means the orchestrator exits without shelling out to Claude.
    assert weekly_briefs.generate_all_briefs(force=True) is False


# ── (c) MRMI formula invariants ─────────────────────────────────────────────

def test_mrmi_formula_matches_documented_equation() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
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

    g = (-re_score).clip(lower=0)
    i = inf_dir.clip(lower=0)
    expected_stress_raw = (
        macro_pipeline.UNIFIED_STRESS_ALPHA * g
        + macro_pipeline.UNIFIED_STRESS_BETA * i
        + macro_pipeline.UNIFIED_STRESS_LAMBDA * g * i
    )
    expected_stress = (expected_stress_raw / macro_pipeline.UNIFIED_STRESS_P99).clip(upper=1.0)
    expected_buffer = buffer_size * (1.0 - expected_stress)
    expected_mrmi = momentum + expected_buffer - threshold

    pd.testing.assert_series_equal(out["growth_weakness"], g)
    pd.testing.assert_series_equal(out["inflation_pressure_raw"], i)
    pd.testing.assert_series_equal(out["stress_intensity"], expected_stress)
    pd.testing.assert_series_equal(out["stress_score"], expected_stress * 10.0)
    pd.testing.assert_series_equal(out["macro_buffer"], expected_buffer)
    pd.testing.assert_series_equal(out["mrmi"], expected_mrmi)


def test_unified_stress_formula_known_point() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    idx = pd.date_range("2026-01-01", periods=1, freq="D")
    momentum = pd.Series([0.0], index=idx)
    re_score = pd.Series([-0.5], index=idx)
    inf_dir = pd.Series([0.2], index=idx)

    out = macro_pipeline.calc_milk_road_macro_index(
        momentum, {"real_economy_score": re_score, "inflation_dir_pp": inf_dir}
    )

    assert out["growth_weakness"].iloc[0] == pytest.approx(0.5)
    assert out["inflation_pressure_raw"].iloc[0] == pytest.approx(0.2)
    assert out["stress_score"].iloc[0] == pytest.approx(1.4738, abs=0.0001)
    assert out["stress_score_bucket"].iloc[0] == "calm"


def test_stress_intensity_is_clipped_to_zero_one() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
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
    assert stress.iloc[2] == pytest.approx(0.0375, abs=0.0001)


def test_stress_score_bucket_boundaries_match_supabase_constraint() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    assert {macro_pipeline.stress_score_bucket(v) for v in [0.0, 3.0, 5.0, 7.0]} == {
        "calm", "watch", "building", "elevated"
    }
    assert macro_pipeline.stress_score_bucket(2.999) == "calm"
    assert macro_pipeline.stress_score_bucket(3.0) == "watch"
    assert macro_pipeline.stress_score_bucket(5.0) == "building"
    assert macro_pipeline.stress_score_bucket(7.0) == "elevated"


def test_mrmi_posture_boundaries_match_investor_grade_zone() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    assert macro_pipeline.mrmi_posture(-0.501) == "CASH"
    assert macro_pipeline.mrmi_exposure(-0.501) == 0.0
    assert macro_pipeline.mrmi_posture(-0.50) == "CAUTION"
    assert macro_pipeline.mrmi_exposure(-0.50) == 0.75
    assert macro_pipeline.mrmi_posture(0.25) == "CAUTION"
    assert macro_pipeline.mrmi_exposure(0.25) == 0.75
    assert macro_pipeline.mrmi_posture(0.251) == "LONG"
    assert macro_pipeline.mrmi_exposure(0.251) == 1.0


def test_canonical_backtest_matches_task35_investor_posture_calmar() -> None:
    backtest = _import_module("macro_framework.backtest_production")
    data_path = ROOT / ".cache" / "raw_data.pkl"
    assert data_path.exists(), "raw_data.pkl is required for the canonical backtest smoke test"
    data = pd.read_pickle(data_path)
    mrmi, _mmi = backtest.production_mrmi(data)
    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "iwm": data["IWM"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
    }

    expected = {"spx": 2.98, "iwm": 2.62, "btc": 0.82}
    for asset, expected_calmar in expected.items():
        result = backtest.backtest_signal(mrmi, asset_rets[asset])
        assert result is not None
        calmar = result["strat_ann"] / abs(result["strat_dd"])
        assert calmar == pytest.approx(expected_calmar, abs=0.01)


def test_prepare_chart_data_uses_release_lagged_macro_values() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
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


def test_core_cpi_inflation_direction_uses_reported_nsa_monthly_prints_without_live_lag() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    daily_idx = pd.date_range("2024-01-01", "2026-08-31", freq="D")
    monthly_idx = pd.date_range("2024-01-01", "2026-08-01", freq="MS")
    nsa_monthly = pd.Series(
        100.0 + np.arange(len(monthly_idx)) * 0.01, index=monthly_idx, name="CPILFENS"
    )
    sa_monthly = pd.Series(
        100.0 + np.arange(len(monthly_idx)) * 0.01, index=monthly_idx, name="CPILFESL"
    )

    # Lock the reported-print example: latest NSA/BLS reported YoY print rounds
    # to 2.9%, six monthly prints earlier rounds to 2.6%, so Inflation Direction
    # is +0.3pp. SA CPILFESL would round lower; CPILFENS must win when present.
    nsa_monthly.loc["2024-12-01"] = 100.0
    nsa_monthly.loc["2025-06-01"] = 100.0
    nsa_monthly.loc["2025-12-01"] = 102.6
    nsa_monthly.loc["2026-06-01"] = 102.9
    sa_monthly.loc["2024-12-01"] = 100.0
    sa_monthly.loc["2025-06-01"] = 100.0
    sa_monthly.loc["2025-12-01"] = 102.6
    sa_monthly.loc["2026-06-01"] = 102.82
    data = pd.DataFrame({
        "CPILFENS": nsa_monthly.reindex(daily_idx).ffill(),
        "CPILFESL": sa_monthly.reindex(daily_idx).ffill(),
    }, index=daily_idx)

    live = macro_pipeline.calc_macro_context(data, lookback_years=1, apply_release_lags=False)

    assert live["core_cpi_yoy_pct"].loc["2026-06-11"] == pytest.approx(2.9)
    assert round(float(live["core_cpi_yoy_pct"].loc["2026-06-11"]), 1) == 2.9
    assert live["inflation_dir_pp"].loc["2026-06-11"] == pytest.approx(0.3)


def test_core_cpi_inflation_direction_falls_back_to_sa_series() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    daily_idx = pd.date_range("2024-01-01", "2026-08-31", freq="D")
    monthly_idx = pd.date_range("2024-01-01", "2026-08-01", freq="MS")
    monthly = pd.Series(
        100.0 + np.arange(len(monthly_idx)) * 0.01, index=monthly_idx, name="CPILFESL"
    )
    monthly.loc["2024-12-01"] = 100.0
    monthly.loc["2025-06-01"] = 100.0
    monthly.loc["2025-12-01"] = 102.6
    monthly.loc["2026-06-01"] = 102.9
    data = pd.DataFrame({"CPILFESL": monthly.reindex(daily_idx).ffill()}, index=daily_idx)

    live = macro_pipeline.calc_macro_context(data, lookback_years=1, apply_release_lags=False)

    assert live["core_cpi_yoy_pct"].loc["2026-06-11"] == pytest.approx(2.9)
    assert live["inflation_dir_pp"].loc["2026-06-11"] == pytest.approx(0.3)


def test_core_cpi_release_lag_remains_available_for_backtests() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    daily_idx = pd.date_range("2024-01-01", "2026-08-31", freq="D")
    monthly_idx = pd.date_range("2024-01-01", "2026-08-01", freq="MS")
    monthly = pd.Series(
        100.0 + np.arange(len(monthly_idx)) * 0.01, index=monthly_idx, name="CPILFESL"
    )
    monthly.loc["2024-12-01"] = 100.0
    monthly.loc["2025-06-01"] = 100.0
    monthly.loc["2025-12-01"] = 102.6
    monthly.loc["2026-06-01"] = 102.9
    data = pd.DataFrame({"CPILFESL": monthly.reindex(daily_idx).ffill()}, index=daily_idx)

    lagged = macro_pipeline.calc_macro_context(data, lookback_years=1, apply_release_lags=True)

    # June's completed CPI print should be hidden from early-June backtest dates
    # and become visible only after the configured CPILFESL release lag.
    assert lagged["core_cpi_yoy_pct"].loc["2026-06-11"] != pytest.approx(2.9)
    assert lagged["inflation_dir_pp"].loc["2026-06-11"] != pytest.approx(0.3)
    assert lagged["core_cpi_yoy_pct"].loc["2026-07-16"] == pytest.approx(2.9)
    assert lagged["inflation_dir_pp"].loc["2026-07-16"] == pytest.approx(0.3)


def test_reference_library_exposes_official_inflation_and_ism_metadata() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    build = _import_module("macro_framework.build")
    idx = pd.date_range("2025-01-01", periods=430, freq="D")
    data = pd.DataFrame({
        "CPIAUCSL": np.linspace(100.0, 112.0, len(idx)),
        "CPILFESL": np.linspace(100.0, 110.0, len(idx)),
        "PPIACO": np.linspace(100.0, 115.0, len(idx)),
        "ISM_PMI": np.linspace(48.0, 52.0, len(idx)),
    }, index=idx)

    library = build.build_library_indicators(data, idx)

    assert "CPILFENS" in macro_pipeline.FRED_SERIES
    assert "PPIACO" in macro_pipeline.FRED_SERIES
    assert "ISM_PMI" in macro_pipeline.NON_FRED_SERIES
    assert library["ism_mfg"]["available"] is True
    assert library["ism_mfg"]["ref_line"] == 50
    assert "DBnomics mirror" in library["ism_mfg"]["notes"]
    assert library["ism_mfg"]["values"][-1] is not None
    assert library["cpi_headline"]["label"] == "Official CPI Headline"
    assert library["cpi_core"]["label"] == "Official Core CPI"
    assert library["ppi_all_commodities"]["label"] == "Official PPI All Commodities"
    assert library["cpi_headline"]["unit"] == "%"
    assert library["cpi_core"]["unit"] == "%"
    assert library["ppi_all_commodities"]["unit"] == "%"
    assert library["ppi_all_commodities"]["values"][-1] is not None


def test_reference_library_ism_chart_uses_observation_points_not_ffilled_tail() -> None:
    build = _import_module("macro_framework.build")
    idx = pd.date_range("2024-10-01", "2025-12-31", freq="D")
    monthly = pd.Series({
        pd.Timestamp("2024-10-01"): 46.9,
        pd.Timestamp("2024-11-01"): 48.4,
        pd.Timestamp("2024-12-01"): 49.2,
        pd.Timestamp("2025-01-01"): 50.9,
        pd.Timestamp("2025-08-01"): 48.7,
    }, name="ISM_PMI")
    data = pd.DataFrame({"ISM_PMI": monthly.reindex(idx).ffill()}, index=idx)

    library = build.build_library_indicators(data, idx)
    ism = library["ism_mfg"]
    visible_values = [v for v in ism["values"] if v is not None]

    assert ism["dates"][-1] == "2025-08-01"
    assert visible_values[-1] == pytest.approx(48.7)
    assert len(visible_values) == 5
    assert len(set(visible_values)) > 1


def test_fetch_dbnomics_ism_pmi_filters_suspicious_tail(monkeypatch: pytest.MonkeyPatch) -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "series": {
                    "docs": [{
                        "period": ["2025-07", "2025-08", "2025-09"],
                        "value": [48.0, 48.7, 11.1],
                    }]
                }
            }

    def fake_get(url: str, timeout: int) -> FakeResponse:
        assert url == macro_pipeline.DBNOMICS_ISM_PMI_URL
        assert timeout == 20
        return FakeResponse()

    monkeypatch.setattr(macro_pipeline.requests, "get", fake_get)

    df = macro_pipeline.fetch_dbnomics_ism_pmi(start="2025-01-01")

    assert list(df.columns) == ["ISM_PMI"]
    assert df.loc[pd.Timestamp("2025-08-01"), "ISM_PMI"] == pytest.approx(48.7)
    assert pd.isna(df.loc[pd.Timestamp("2025-09-01"), "ISM_PMI"])
    assert df["ISM_PMI"].dropna().empty is False


def test_save_snapshot_schema_uses_actual_current_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
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
        "growth_impulse_drilldown",
        "sector_breadth_drilldown",
        "financial_conditions_drilldown",
    } <= snapshot.keys()
    assert {"gii_fast", "fincon", "breadth"} <= snapshot["components"].keys()
    assert {
        "value",
        "state",
        "momentum",
        "stress_intensity",
        "stress_score",
        "growth_weakness",
        "inflation_pressure_raw",
        "stress_score_bucket",
        "macro_buffer",
        "buffer_size",
    } <= snapshot["mrmi_combined"].keys()
    assert {"real_economy_score", "inflation_dir_pp", "core_cpi_yoy_pct", "raw"} <= snapshot[
        "macro"
    ].keys()
    assert {"intro", "score", "rows", "brief"} <= snapshot["growth_impulse_drilldown"].keys()
    assert {"intro", "score", "rows", "brief"} <= snapshot["sector_breadth_drilldown"].keys()
    assert {"intro", "score", "rows", "brief"} <= snapshot["financial_conditions_drilldown"].keys()


def test_growth_impulse_drilldown_exposes_all_current_inputs() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    data_path = ROOT / ".cache" / "raw_data.pkl"
    assert data_path.exists(), "raw_data.pkl is required for the dashboard drill-down smoke test"
    data = pd.read_pickle(data_path)
    gii = macro_pipeline.calc_growth_impulse(data)

    payload = macro_pipeline.growth_impulse_drilldown(data, gii)
    rows = payload["rows"]
    keys = {row["key"] for row in rows}

    assert keys == set(macro_pipeline.GROWTH_IMPULSE_SPECS)
    assert len(rows) == 10
    assert payload["score"] == pytest.approx(round(float(gii["fast"].dropna().iloc[-1]), 4))
    assert payload["brief"]
    assert "|current z|" in payload["sort_note"]
    assert [abs(row["z_21d"] or 0) for row in rows] == sorted(
        (abs(row["z_21d"] or 0) for row in rows), reverse=True
    )
    for row in rows:
        assert {
            "group",
            "label",
            "explanation",
            "current",
            "trend_21d",
            "trend_126d",
            "z_21d",
            "z_126d",
        } <= row.keys()
        assert row["explanation"]


def test_mmi_driver_drilldowns_expose_all_current_inputs() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    data_path = ROOT / ".cache" / "raw_data.pkl"
    assert data_path.exists(), "raw_data.pkl is required for the dashboard drill-down smoke test"
    data = pd.read_pickle(data_path)

    cases = [
        (
            macro_pipeline.sector_breadth_drilldown(data, macro_pipeline.calc_sector_breadth(data)),
            set(macro_pipeline.SECTOR_BREADTH_SPECS),
            7,
        ),
        (
            macro_pipeline.financial_conditions_drilldown(
                data, macro_pipeline.calc_financial_conditions(data)
            ),
            set(macro_pipeline.FINANCIAL_CONDITIONS_SPECS),
            3,
        ),
    ]
    for payload, expected_keys, expected_count in cases:
        rows = payload["rows"]
        assert {row["key"] for row in rows} == expected_keys
        assert len(rows) == expected_count
        assert payload["brief"]
        assert "|current z|" in payload["sort_note"]
        assert [abs(row["z_21d"] or 0) for row in rows] == sorted(
            (abs(row["z_21d"] or 0) for row in rows), reverse=True
        )
        for row in rows:
            assert {
                "group",
                "label",
                "source",
                "explanation",
                "current",
                "z_21d",
                "z_change_7d",
                "z_change_30d",
                "contribution_7d",
                "values",
            } <= row.keys()
            assert row["explanation"]



def _function_source(module_text: str, name: str, next_name: str) -> str:
    return module_text.split(f"def {name}", 1)[1].split(f"def {next_name}", 1)[0]


def test_breadth_lookback_docs_match_code() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    code_lookback = macro_pipeline.SECTOR_BREADTH_LOOKBACK

    docs = "\n".join((ROOT / name).read_text() for name in ("README.md", "CLAUDE.md", "GUIDE.md"))
    assert code_lookback == 90
    assert f"lookback={code_lookback}" in docs or f"lookback = {code_lookback}" in docs
    assert "over 90 days" in docs


def test_documented_mrmi_parameters_are_locked_to_code() -> None:
    source = (PACKAGE_DIR / "macro_pipeline.py").read_text()
    mrmi_src = _function_source(source, "calc_milk_road_macro_index", "calc_macro_context")
    assert "buffer_size: float = UNIFIED_STRESS_BUFFER_SIZE" in mrmi_src
    assert "threshold: float = UNIFIED_STRESS_THRESHOLD" in mrmi_src
    assert "UNIFIED_STRESS_P99" in mrmi_src

    docs = "\n".join((ROOT / name).read_text() for name in ("README.md", "CLAUDE.md", "GUIDE.md"))
    assert "buffer_size=0.5" in docs or "buffer_size = 0.5" in docs
    assert "threshold=0.75" in docs or "threshold = 0.75" in docs
    assert "stress_p99=10.0083" in docs or "stress_p99 = 10.0083" in docs


def test_documented_release_lags_are_locked_to_code() -> None:
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    assert macro_pipeline.RELEASE_LAGS_DAYS == {
        "PCEC96": 60,
        "UNRATE": 35,
        "RPI": 60,
        "GDPNOW": 0,
        "CPILFENS": 45,
        "CPILFESL": 45,
    }

    docs = "\n".join((ROOT / name).read_text() for name in ("README.md", "CLAUDE.md", "GUIDE.md"))
    for snippet in ("PCE/RPI 60d", "unemployment 35d", "Core CPI 45d", "GDPNow 0d"):
        assert snippet in docs


def test_index_page_imports_iteration_surface_constants() -> None:
    renderer = _import_module("macro_framework.build_index_page")
    cost = _import_module("macro_framework.cost")
    macro_pipeline = _import_module("macro_framework.macro_pipeline")
    weekly_briefs = _import_module("macro_framework.weekly_briefs")

    html = renderer.build_html("2026-05-27 09:00 UTC")

    assert str(macro_pipeline.UNIFIED_STRESS_BUFFER_SIZE) in html
    assert str(macro_pipeline.UNIFIED_STRESS_THRESHOLD) in html
    assert str(macro_pipeline.UNIFIED_STRESS_P99) in html
    assert f"{macro_pipeline.MRMI_CASH_THRESHOLD:+.2f}" in html
    assert f"{macro_pipeline.MRMI_LONG_THRESHOLD:+.2f}" in html
    assert str(macro_pipeline.SECTOR_BREADTH_LOOKBACK) in html
    assert "Market Momentum Index inputs" in html
    for section, specs in (
        ("Growth Impulses", macro_pipeline.GROWTH_IMPULSE_SPECS),
        ("Sector Breadth", macro_pipeline.SECTOR_BREADTH_SPECS),
        ("Financial Conditions", macro_pipeline.FINANCIAL_CONDITIONS_SPECS),
    ):
        assert f"<summary>{section}</summary>" in html
        for key, spec in specs.items():
            assert f"<code>{renderer.esc(key)}</code>" in html
            assert renderer.esc(spec["label"]) in html
            assert renderer.esc(spec["source"]) in html
            assert renderer.esc(spec["explanation"]) in html
    assert "Reference Library" in html
    assert "Release lags" in html
    assert "Weekly briefs" in html
    assert "Estimated weekly Claude spend" in html
    assert f"${renderer.cost_total_usd():.2f} / week" in html
    assert cost.COST_ESTIMATES[0]["site"] in html
    assert "github.com/m0xt/macro-framework/edit/main/src/macro_framework/macro_pipeline.py" in html
    assert weekly_briefs.SYSTEM_MARKET[:80] in html


def test_index_page_reference_library_metadata_comes_from_dashboard_builder() -> None:
    renderer = _import_module("macro_framework.build_index_page")
    library = renderer.reference_library_metadata()

    assert "cpi_headline" in library
    assert "cpi_core" in library
    assert "ppi_all_commodities" in library
    assert "ism_mfg" in library
    assert library["cpi_core"]["label"] == "Official Core CPI"
    assert "DBnomics" in library["ism_mfg"]["desc"]


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
