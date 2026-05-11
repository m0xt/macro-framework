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
