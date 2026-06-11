from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from macro_framework.macro_pipeline import calc_macro_context


def _monthly_core_cpi() -> pd.Series:
    idx = pd.date_range("2024-01-01", "2026-05-01", freq="MS")
    monthly = pd.Series(index=idx, dtype=float, name="CPILFENS")

    # Give every observed month a distinct value so the production helper can
    # recover monthly observations from a daily forward-filled source frame.
    for i, ts in enumerate(pd.date_range("2024-01-01", "2024-12-01", freq="MS")):
        monthly.loc[ts] = 100.0 + i * 0.01
    for ts in pd.date_range("2025-01-01", "2025-12-01", freq="MS"):
        monthly.loc[ts] = monthly.loc[ts - pd.DateOffset(years=1)] * 1.025
    for ts in pd.date_range("2026-01-01", "2026-05-01", freq="MS"):
        monthly.loc[ts] = monthly.loc[ts - pd.DateOffset(years=1)] * 1.025

    # Prior available direction: Mar-2026 YoY 2.8% minus Sep-2025 YoY 2.6% = +0.2pp,
    # first visible on the Apr-2026 release date and then held daily.
    monthly.loc["2025-09-01"] = monthly.loc["2024-09-01"] * 1.026
    monthly.loc["2026-03-01"] = monthly.loc["2025-03-01"] * 1.028

    # New May print: May-2026 YoY 2.9% minus Nov-2025 YoY 2.6% = +0.3pp.
    # It is dated May 1 in FRED but should first affect the live chart on Jun 10.
    monthly.loc["2025-11-01"] = monthly.loc["2024-11-01"] * 1.026
    monthly.loc["2026-05-01"] = monthly.loc["2025-05-01"] * 1.029
    return monthly


def _daily_core_cpi_frame(monthly: pd.Series, daily_idx: pd.DatetimeIndex) -> pd.DataFrame:
    return pd.DataFrame({"CPILFENS": monthly.reindex(daily_idx).ffill()}, index=daily_idx)


def test_core_cpi_yoy_and_inflation_direction_are_daily_release_steps() -> None:
    daily_idx = pd.date_range("2024-01-01", "2026-06-15", freq="D")
    data = _daily_core_cpi_frame(_monthly_core_cpi(), daily_idx)
    live = calc_macro_context(data, lookback_years=1, apply_release_lags=False)

    assert live["core_cpi_yoy_pct"].loc["2026-06-09"] != pytest.approx(2.9)
    assert live["inflation_dir_pp"].loc["2026-05-11"] == pytest.approx(0.0)
    assert live["inflation_dir_pp"].loc["2026-06-09"] == pytest.approx(0.0)
    assert live["core_cpi_yoy_pct"].loc["2026-06-10"] == pytest.approx(2.9)
    assert live["inflation_dir_pp"].loc["2026-06-10"] == pytest.approx(0.3)
    assert live["core_cpi_yoy_pct"].loc["2026-06-11"] == pytest.approx(2.9)
    assert live["inflation_dir_pp"].loc["2026-06-11"] == pytest.approx(0.3)


def test_missing_cpi_month_does_not_overwrite_prior_daily_direction_step() -> None:
    daily_idx = pd.date_range("2024-01-01", "2026-06-15", freq="D")
    monthly = _monthly_core_cpi().drop(pd.Timestamp("2025-10-01"))

    data = _daily_core_cpi_frame(monthly, daily_idx)
    live = calc_macro_context(data, lookback_years=1, apply_release_lags=False)

    assert live["inflation_dir_pp"].loc["2026-04-10"] == pytest.approx(0.2)
    assert live["inflation_dir_pp"].loc["2026-05-11"] == pytest.approx(0.2)
    assert live["inflation_dir_pp"].loc["2026-05-31"] == pytest.approx(0.2)
    assert live["inflation_dir_pp"].loc["2026-06-09"] == pytest.approx(0.2)
    assert live["inflation_dir_pp"].loc["2026-06-10"] == pytest.approx(0.3)
    assert not np.isnan(live["inflation_dir_pp"].loc["2026-05-31"])
