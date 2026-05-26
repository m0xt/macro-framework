#!/usr/bin/env python3
"""Shared data and indicator pipeline for the macro dashboard.

This module preserves the data fetch, indicator math, chart payload, and
snapshot-writing logic that both the dashboard and analytics scripts use.
It intentionally contains no HTML dashboard renderer.
"""
import json
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / ".cache"

DATA_CACHE = CACHE_DIR / "raw_data.pkl"

SNAPSHOT_DIR = REPO_ROOT / "snapshots"

YF_TICKERS = [
    "HYG", "XLY", "XLP", "XLI", "XLU", "SPHB", "SPLV",
    "HG=F",  # Copper
    "GC=F",  # Gold futures
    "^VIX", "^TNX",  # VIX, 10Y yield
    "^MOVE",  # Bond volatility
    "SMH", "IWM", "IYT", "IBB", "XHB", "KBE", "XRT", "SLX",  # Sector ETFs
    "BDRY",  # BDI proxy
    "BTC-USD",  # Bitcoin
    "^GSPC",  # S&P 500
    "DBC",  # Commodities ETF
    "UPS", "FDX", "CAT", "HON", "DOV", "FAST",  # Industrial stocks
    "IWC",  # Micro-caps
    "DJT",  # Dow Transports
    "CBON",  # VanEck China Bond ETF (inverted = CN10Y proxy)
]

FRED_SERIES = {
    "BAMLH0A0HYM2": "HY Spread",
    "BAMLC0A0CM": "IG Spread",
    "WEI": "Weekly Economic Index",
    "DGS10": "10Y Yield",
    "DGS2": "2Y Yield",
    "DTWEXBGS": "USD Trade Weighted Index",
    "WALCL": "Fed Balance Sheet",
    "WTREGEN": "Treasury General Account",
    "RRPONTSYD": "Reverse Repo",
    "ICSA": "Initial Jobless Claims",
    "CCSA": "Continuing Claims",
    "T5YIE": "5Y Breakeven Inflation",
    "T10YIE": "10Y Breakeven Inflation",
    "DFII10": "10Y Real Rate (TIPS)",
    "CFNAI": "Chicago Fed Activity Index",
    "INDPRO": "Industrial Production",
    "HOUST": "Housing Starts",
    "PERMIT": "Building Permits",
    "DRTSCILM": "SLOOS C&I Lending",
    "DGS3MO": "3M Treasury",
    "CPIAUCSL": "CPI All Items",
    "CPILFESL": "CPI Core (ex food & energy)",
    "PPIACO": "Producer Price Index: All Commodities",
    "PCEPILFE": "Core PCE",
    "GDPC1": "Real GDP (chained 2017 dollars)",
    "GDPPOT": "Real Potential GDP (CBO, chained 2017 dollars)",
    "M2SL": "M2 Money Supply (US)",
    "GDPNOW": "Atlanta Fed GDPNow nowcast",
    "PCEC96": "Real Personal Consumption Expenditures",
    "UNRATE": "Unemployment Rate",
    "RPI": "Real Personal Income",
}

DBNOMICS_ISM_PMI_URL = "https://api.db.nomics.world/v22/series/ISM/pmi/pm?observations=1"
NON_FRED_SERIES = {
    "ISM_PMI": "ISM Manufacturing PMI (via DBnomics mirror)",
}

def fetch_yfinance(tickers: list[str], period: str = "10y") -> pd.DataFrame:
    """Fetch close prices for all tickers from Yahoo Finance."""
    print(f"  Fetching {len(tickers)} tickers from Yahoo Finance...", end=" ", flush=True)
    df = yf.download(tickers, period=period, progress=False, group_by="ticker")

    # Extract close prices into a clean DataFrame
    closes = pd.DataFrame(index=df.index)
    for t in tickers:
        try:
            if len(tickers) == 1:
                closes[t] = df["Close"]
            else:
                closes[t] = df[(t, "Close")]
        except (KeyError, TypeError):
            print(f"\n    Warning: {t} not found", end="", flush=True)
            closes[t] = np.nan
    print(f"OK ({len(closes)} rows)")
    return closes

def fetch_fred(series_ids: list[str], start: str = "2016-01-01") -> pd.DataFrame:
    """Fetch series from FRED via CSV download."""
    print(f"  Fetching {len(series_ids)} series from FRED...", end=" ", flush=True)
    frames = {}
    for sid in series_ids:
        try:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            df = pd.read_csv(StringIO(r.text))
            col = df.columns[-1]
            df = df[df[col] != "."].copy()
            df["observation_date"] = pd.to_datetime(df.iloc[:, 0])
            df[sid] = df[col].astype(float)
            df = df.set_index("observation_date")[[sid]]
            frames[sid] = df[sid]
        except Exception as e:
            print(f"\n    Warning: {sid} failed: {e}", end="", flush=True)
            frames[sid] = pd.Series(dtype=float, name=sid)
    result = pd.DataFrame(frames)
    print(f"OK ({len(result)} rows)")
    return result

def fetch_dbnomics_ism_pmi(start: str = "2016-01-01") -> pd.DataFrame:
    """Fetch ISM Manufacturing PMI from DBnomics' ISM mirror.

    FRED's legacy NAPM CSV endpoint currently returns 404, but DBnomics exposes
    the Institute for Supply Management monthly PMI series. DBnomics' current
    mirror has a suspicious low-value tail in late 2025, so implausible PMI
    readings are treated as missing instead of charting bad data.
    """
    print("  Fetching ISM Manufacturing PMI from DBnomics...", end=" ", flush=True)
    try:
        response = requests.get(DBNOMICS_ISM_PMI_URL, timeout=20)
        response.raise_for_status()
        payload = response.json()
        docs = payload.get("series", {}).get("docs", [])
        if not docs:
            raise ValueError("DBnomics response did not include series docs")

        doc = docs[0]
        periods = doc.get("period", [])
        values = doc.get("value", [])
        if len(periods) != len(values):
            raise ValueError("DBnomics period/value lengths differ")

        idx = pd.to_datetime(periods, format="%Y-%m")
        series = pd.Series(pd.to_numeric(values, errors="coerce"), index=idx, name="ISM_PMI")
        series = series[series.index >= pd.Timestamp(start)]

        # PMI is a diffusion index centered on 50. Values in the low teens are
        # incompatible with recent official ISM releases and reflect a mirror
        # data-quality issue, not a manufacturing depression.
        suspicious = series.notna() & ((series < 30.0) | (series > 80.0))
        if suspicious.any():
            print(f"filtered {int(suspicious.sum())} suspicious point(s);", end=" ", flush=True)
            series = series.mask(suspicious)

        result = series.to_frame()
        print(f"OK ({int(series.notna().sum())} observations)")
        return result
    except Exception as e:
        print(f"failed: {e}")
        return pd.DataFrame({"ISM_PMI": pd.Series(dtype=float)})

def fetch_non_fred_series() -> pd.DataFrame:
    """Fetch supplementary non-FRED reference-library series."""
    return fetch_dbnomics_ism_pmi()

def fetch_all_data(use_cache: bool = True) -> pd.DataFrame:
    """Fetch and align all data into a single DataFrame."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if use_cache and DATA_CACHE.exists():
        age_hours = (datetime.now().timestamp() - DATA_CACHE.stat().st_mtime) / 3600
        if age_hours < 12:
            cached = pd.read_pickle(DATA_CACHE)
            expected_cols = set(YF_TICKERS) | set(FRED_SERIES) | set(NON_FRED_SERIES)
            missing_cols = sorted(expected_cols - set(cached.columns))
            empty_expected_cols = [
                col for col in sorted(set(NON_FRED_SERIES) & set(cached.columns))
                if cached[col].dropna().empty
            ]
            refresh_cols = missing_cols + empty_expected_cols
            if not refresh_cols:
                print(f"  Using cached data ({age_hours:.1f}h old)")
                return cached
            print(
                "  Cache missing expected series "
                f"({', '.join(refresh_cols[:8])}{'...' if len(refresh_cols) > 8 else ''}); refreshing"
            )

    print("Fetching data...")
    yf_data = fetch_yfinance(YF_TICKERS)
    fred_data = fetch_fred(list(FRED_SERIES.keys()))
    non_fred_data = fetch_non_fred_series()

    # Align to common daily index
    combined = pd.concat([yf_data, fred_data, non_fred_data], axis=1)
    combined = combined.sort_index()

    # Forward-fill gaps (FRED weekends, WEI weekly gaps)
    combined = combined.ffill()

    # Drop rows where all values are NaN
    combined = combined.dropna(how="all")

    # Trim to today — some series (e.g. CBO Potential GDP) include forward
    # projections that would otherwise extend the index into the future and
    # cause stale-ffilled values to be read as "latest."
    today = pd.Timestamp.now().normalize()
    combined = combined[combined.index <= today]

    # Cache
    combined.to_pickle(DATA_CACHE)
    print(f"  Cached to {DATA_CACHE.name} ({len(combined)} rows)")
    return combined

def zscore(series: pd.Series, lookback: int) -> pd.Series:
    """Rolling z-score."""
    m = series.rolling(lookback, min_periods=lookback // 2).mean()
    s = series.rolling(lookback, min_periods=lookback // 2).std()
    return (series - m) / s.replace(0, np.nan)

def roc(series: pd.Series, period: int) -> pd.Series:
    """Rate of change (%)."""
    return series.pct_change(period) * 100

def chg(series: pd.Series, period: int) -> pd.Series:
    """Simple change (for near-zero series like spreads)."""
    return series.diff(period)

def ema(series: pd.Series, span: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=span, adjust=False).mean()

def clip_series(series: pd.Series, limit: float = 3.0) -> pd.Series:
    """Clip values to ±limit."""
    return series.clip(-limit, limit)


GROWTH_IMPULSE_FAST_ROC = 21      # optimized (was 42)
GROWTH_IMPULSE_SLOW_ROC = 126     # optimized (was 252)
GROWTH_IMPULSE_Z_LEN = 504
GROWTH_IMPULSE_CLIP_Z = 3.0
GROWTH_IMPULSE_EMA_LEN = 1        # optimized: no smoothing (was 21)

GROWTH_IMPULSE_SPECS = {
    "HYG": {
        "label": "HYG",
        "group": "Credit/risk appetite",
        "source": "HYG high-yield ETF",
        "explanation": (
            "High-yield bond ETF; rising HYG usually signals stronger risk appetite and "
            "credit conditions."
        ),
        "unit": "price",
        "trend_type": "roc",
    },
    "BAML_INV": {
        "label": "HY spread inverted",
        "group": "Credit/risk appetite",
        "source": "BAML HY OAS, inverted",
        "explanation": (
            "High-yield credit spread, inverted so tighter spreads are positive for growth "
            "and risk appetite."
        ),
        "unit": "%",
        "trend_type": "change",
    },
    "XLY_XLP": {
        "label": "XLY/XLP",
        "group": "Credit/risk appetite",
        "source": "Discretionary vs staples",
        "explanation": (
            "Consumer discretionary versus staples; a higher ratio signals cyclical "
            "consumer risk appetite."
        ),
        "unit": "ratio",
        "trend_type": "roc",
    },
    "XLI_XLU": {
        "label": "XLI/XLU",
        "group": "Credit/risk appetite",
        "source": "Industrials vs utilities",
        "explanation": (
            "Industrials versus utilities; a higher ratio signals cyclicals beating "
            "defensives."
        ),
        "unit": "ratio",
        "trend_type": "roc",
    },
    "SPHB_SPLV": {
        "label": "SPHB/SPLV",
        "group": "Credit/risk appetite",
        "source": "High beta vs low volatility",
        "explanation": (
            "High-beta equities versus low-volatility equities; a higher ratio signals "
            "investors favor riskier stocks."
        ),
        "unit": "ratio",
        "trend_type": "roc",
    },
    "COPPER": {
        "label": "Copper",
        "group": "Growth/commodities",
        "source": "HG=F copper futures",
        "explanation": "Cyclical commodity proxy for industrial and global growth demand.",
        "unit": "price",
        "trend_type": "roc",
    },
    "BDI_SA": {
        "label": "BDRY/BDI proxy",
        "group": "Growth/commodities",
        "source": "BDRY vs seasonal baseline",
        "explanation": (
            "Dry-bulk shipping proxy; rising values can indicate stronger real-economy "
            "trade and commodity demand."
        ),
        "unit": "pct",
        "trend_type": "change",
    },
    "WEI": {
        "label": "WEI",
        "group": "Growth/commodities",
        "source": "Weekly Economic Index",
        "explanation": (
            "Weekly Economic Index; high, rising, or falling readings capture broad US "
            "economic activity momentum."
        ),
        "unit": "index",
        "trend_type": "change",
    },
    "VIX_INV": {
        "label": "VIX inverted",
        "group": "Vol/rates",
        "source": "VIX, inverted",
        "explanation": (
            "Equity volatility, inverted so lower volatility is positive for risk "
            "appetite."
        ),
        "unit": "index",
        "trend_type": "change",
    },
    "YC": {
        "label": "Yield curve",
        "group": "Vol/rates",
        "source": "10Y minus 2Y Treasury yield",
        "explanation": (
            "10Y minus 2Y Treasury yield; a steeper curve usually supports growth and "
            "liquidity expectations."
        ),
        "unit": "pp",
        "trend_type": "change",
    },
}


FINANCIAL_CONDITIONS_SPECS = {
    "^VIX": {
        "label": "VIX",
        "group": "Equity volatility",
        "source": "CBOE Volatility Index",
        "explanation": (
            "S&P 500 implied volatility. The z-score is inverted, so falling VIX loosens "
            "financial conditions and supports MMI."
        ),
        "unit": "index",
    },
    "^MOVE": {
        "label": "MOVE",
        "group": "Rates volatility",
        "source": "ICE BofA MOVE Index",
        "explanation": (
            "Treasury-market implied volatility. The z-score is inverted, so calmer rate "
            "volatility is positive for financial conditions."
        ),
        "unit": "index",
    },
    "BAMLH0A0HYM2": {
        "label": "HY spread",
        "group": "Credit stress",
        "source": "BofA US High Yield OAS",
        "explanation": (
            "High-yield option-adjusted spread. The z-score is inverted, so tighter credit "
            "spreads read as looser conditions."
        ),
        "unit": "spread %",
    },
}

SECTOR_BREADTH_SPECS = {
    "SMH": {
        "label": "SMH",
        "group": "Semiconductors",
        "source": "VanEck Semiconductor ETF",
        "explanation": "Semiconductors are a high-beta cyclical leadership group; strength broadens risk appetite.",
        "unit": "price",
    },
    "IWM": {
        "label": "IWM",
        "group": "Small caps",
        "source": "iShares Russell 2000 ETF",
        "explanation": "Small caps reflect domestic cyclical participation and financing sensitivity.",
        "unit": "price",
    },
    "IYT": {
        "label": "IYT",
        "group": "Transports",
        "source": "iShares Transportation ETF",
        "explanation": "Transports track economically sensitive shipping, logistics, and travel activity.",
        "unit": "price",
    },
    "IBB": {
        "label": "IBB",
        "group": "Biotech",
        "source": "iShares Biotechnology ETF",
        "explanation": "Biotech adds speculative growth participation outside mega-cap technology.",
        "unit": "price",
    },
    "XHB": {
        "label": "XHB",
        "group": "Housing",
        "source": "SPDR Homebuilders ETF",
        "explanation": "Homebuilders are rate-sensitive cyclicals and often react early to financial conditions.",
        "unit": "price",
    },
    "KBE": {
        "label": "KBE",
        "group": "Banks",
        "source": "SPDR Bank ETF",
        "explanation": "Banks capture credit-cycle health, yield-curve sensitivity, and domestic risk appetite.",
        "unit": "price",
    },
    "XRT": {
        "label": "XRT",
        "group": "Retail",
        "source": "SPDR Retail ETF",
        "explanation": "Retail reflects consumer-facing cyclical participation beyond defensive staples.",
        "unit": "price",
    },
}

GROWTH_IMPULSE_CHANGE_COMPONENTS = {"YC", "WEI", "BAML_INV", "VIX_INV", "BDI_SA"}

def growth_impulse_components(data: pd.DataFrame) -> dict[str, pd.Series]:
    """Build the raw component series used by the Growth Impulses composite."""
    components = {}

    # 1. HYG
    if "HYG" in data:
        components["HYG"] = data["HYG"]

    # 2. BAML HY spread (inverted — tighter spread = risk-on)
    if "BAMLH0A0HYM2" in data:
        components["BAML_INV"] = -data["BAMLH0A0HYM2"]

    # 3. XLY/XLP ratio
    if "XLY" in data and "XLP" in data:
        components["XLY_XLP"] = data["XLY"] / data["XLP"].replace(0, np.nan)

    # 4. XLI/XLU ratio
    if "XLI" in data and "XLU" in data:
        components["XLI_XLU"] = data["XLI"] / data["XLU"].replace(0, np.nan)

    # 5. SPHB/SPLV ratio
    if "SPHB" in data and "SPLV" in data:
        components["SPHB_SPLV"] = data["SPHB"] / data["SPLV"].replace(0, np.nan)

    # 6. Copper
    if "HG=F" in data:
        components["COPPER"] = data["HG=F"]

    # 7. VIX inverted
    if "^VIX" in data:
        components["VIX_INV"] = -data["^VIX"]

    # 8. Yield curve (10Y - 2Y)
    if "DGS10" in data and "DGS2" in data:
        components["YC"] = data["DGS10"] - data["DGS2"]
    elif "^TNX" in data and "DGS2" in data:
        components["YC"] = data["^TNX"] - data["DGS2"]

    # 9. WEI
    if "WEI" in data:
        components["WEI"] = data["WEI"]

    # 10. BDI proxy (BDRY) — seasonally adjusted
    if "BDRY" in data:
        bdry = data["BDRY"]
        # Seasonal baseline: avg of same-date values over last 3 years (63-bar lag)
        baseline = pd.Series(np.nan, index=bdry.index)
        for n_years in range(1, 4):
            shifted = bdry.shift(63 * n_years)
            baseline = baseline.add(shifted.where(shifted > 0), fill_value=0)
        # Count valid years for average
        count = pd.Series(0, index=bdry.index)
        for n_years in range(1, 4):
            shifted = bdry.shift(63 * n_years)
            count += (shifted > 0).astype(int)
        baseline = baseline / count.replace(0, np.nan)
        components["BDI_SA"] = (bdry / baseline.replace(0, np.nan)) - 1.0

    return components

def _growth_impulse_component_signals(name: str, series: pd.Series) -> tuple[pd.Series, pd.Series]:
    if name in GROWTH_IMPULSE_CHANGE_COMPONENTS:
        return chg(series, GROWTH_IMPULSE_FAST_ROC), chg(series, GROWTH_IMPULSE_SLOW_ROC)
    return roc(series, GROWTH_IMPULSE_FAST_ROC), roc(series, GROWTH_IMPULSE_SLOW_ROC)

def _latest_component_value(series: pd.Series) -> float | None:
    s = series.dropna()
    if len(s) == 0:
        return None
    return round(float(s.iloc[-1]), 4)


def _component_delta(series: pd.Series, periods: int) -> float | None:
    s = series.dropna()
    if len(s) <= periods:
        return None
    return round(float(s.iloc[-1] - s.iloc[-(periods + 1)]), 4)


def _component_values(series: pd.Series, index: pd.Index) -> list[float | None]:
    values = series.reindex(index)
    return [round(float(v), 4) if pd.notna(v) else None for v in values]


def _driver_row_label(row: dict | None) -> str:
    if not row:
        return "none"
    return str(row.get("label") or row.get("key") or "none")


def _driver_row_z_text(row: dict) -> str:
    label = _driver_row_label(row)
    z_value = row.get("z_21d")
    if z_value is None:
        return label
    return f"{label} ({float(z_value):+.2f}z)"


def _driver_row_list(rows: list[dict], *, positive: bool) -> str:
    filtered = [row for row in rows if row.get("z_21d") is not None]
    if positive:
        filtered = [row for row in filtered if row["z_21d"] > 0]
        filtered = sorted(filtered, key=lambda row: row["z_21d"], reverse=True)
    else:
        filtered = [row for row in filtered if row["z_21d"] < 0]
        filtered = sorted(filtered, key=lambda row: row["z_21d"])
    if not filtered:
        return "none"
    return " and ".join(_driver_row_z_text(row) for row in filtered[:2])


def _driver_breadth_sentence(
    driver_name: str,
    *,
    score: float,
    supportive: int,
    drag: int,
    valid_count: int,
) -> str:
    if valid_count == 0:
        return f"The {driver_name} read is incomplete because no current input z-scores are valid."
    support_share = supportive / valid_count
    drag_share = drag / valid_count
    if score > 0 and support_share >= 0.65:
        character = "broadly constructive"
    elif score < 0 and drag_share >= 0.65:
        character = "broadly negative"
    elif score > 0 and supportive <= drag:
        character = "positive but fragile"
    elif score < 0 and drag <= supportive:
        character = "negative but fragile"
    else:
        character = "mixed"
    drag_noun = "input is" if drag == 1 else "inputs are"
    return (
        f"Input breadth is {character}: {supportive} of {valid_count} inputs are positive "
        f"and {drag} {drag_noun} negative."
    )


def _driver_next_watch_sentence(
    *,
    score: float,
    support_label: str,
    drag_label: str,
) -> str:
    if score >= 0:
        return (
            f"The next read improves if {drag_label} stops acting as a drag and more inputs "
            f"join the positive side; it weakens if {support_label} rolls over."
        )
    return (
        f"The next read improves if {drag_label} mean-reverts and support broadens; it gets "
        f"worse if {support_label} fails to hold or the current drags deepen."
    )


def _driver_brief(
    *,
    driver_name: str,
    driver_short: str,
    score: float,
    valid: list[dict],
    supportive: int,
    drag: int,
    top_mover: dict | None,
    top_support: dict | None,
    top_drag: dict | None,
) -> list[str]:
    if top_mover and top_mover.get("contribution_7d"):
        mover_dir = "improved" if top_mover["contribution_7d"] > 0 else "deteriorated"
        mover_tail = (
            f"led by {_driver_row_label(top_mover)} "
            f"({float(top_mover['contribution_7d']):+.2f} contribution points)."
        )
    else:
        mover_dir = "was little changed"
        mover_tail = "with no single input making a measurable 7-day contribution."
    support_label = _driver_row_label(top_support)
    drag_label = _driver_row_label(top_drag)
    current_direction = "supporting" if score > 0 else "weighing on"
    support_text = _driver_row_list(valid, positive=True)
    drag_text = _driver_row_list(valid, positive=False)
    return [
        f"{driver_name} {mover_dir} over the latest week, {mover_tail}",
        f"At {score:+.2f}, {driver_short} is currently {current_direction} MMI.",
        f"Support currently comes from {support_text}.",
        f"The main drag is {drag_text}.",
        _driver_breadth_sentence(
            driver_name,
            score=score,
            supportive=supportive,
            drag=drag,
            valid_count=len(valid),
        ),
        _driver_next_watch_sentence(
            score=score,
            support_label=support_label,
            drag_label=drag_label,
        ),
    ]


def growth_impulse_drilldown(
    data: pd.DataFrame,
    gii: pd.DataFrame | None = None,
    *,
    include_values: bool = True,
) -> dict:
    """Latest component evidence stack for the dashboard Growth Impulses drill-down.

    GII = mean of per-component clipped z-scored ROCs (fast leg).  Each row's
    ``contribution_7d`` is the per-input share of the latest 7-day ΔGII proxy:
    ``Δz_fast_i / N`` with ``N`` = number of growth-impulse components.  Rows
    are sorted by ``|z_21d|`` descending so the largest current signals surface
    first, while 7-day and 30-day deltas remain context columns.
    """
    rows = []
    components = growth_impulse_components(data)
    chart_index = gii.index if gii is not None and len(gii.index) else data.index
    component_count = len(GROWTH_IMPULSE_SPECS) or 1
    for name, series in components.items():
        sig_fast, sig_slow = _growth_impulse_component_signals(name, series)
        z_fast = clip_series(zscore(sig_fast, GROWTH_IMPULSE_Z_LEN), GROWTH_IMPULSE_CLIP_Z)
        z_slow = clip_series(zscore(sig_slow, GROWTH_IMPULSE_Z_LEN), GROWTH_IMPULSE_CLIP_Z)
        z_change_7d = _component_delta(z_fast, 5)
        z_change_30d = _component_delta(z_fast, 21)
        contribution_7d = (
            round(float(z_change_7d) / component_count, 6) if z_change_7d is not None else None
        )
        spec = GROWTH_IMPULSE_SPECS[name]
        row = {
            "key": name,
            "label": spec["label"],
            "group": spec["group"],
            "source": spec["source"],
            "explanation": spec["explanation"],
            "unit": spec["unit"],
            "trend_type": spec["trend_type"],
            "current": _latest_component_value(series),
            "trend_21d": _latest_component_value(sig_fast),
            "trend_126d": _latest_component_value(sig_slow),
            "z_21d": _latest_component_value(z_fast),
            "z_126d": _latest_component_value(z_slow),
            "z_change_7d": z_change_7d,
            "z_change_30d": z_change_30d,
            "contribution_7d": contribution_7d,
        }
        if include_values:
            row["values"] = _component_values(series, chart_index)
        rows.append(row)

    rows = sorted(
        rows,
        key=lambda r: (
            -abs(r["z_21d"] or 0),
            list(GROWTH_IMPULSE_SPECS).index(r["key"]),
        ),
    )

    score = _latest_component_value(gii["fast"]) if gii is not None and "fast" in gii else None
    valid = [r for r in rows if r["z_21d"] is not None]
    supportive = sum(1 for r in valid if r["z_21d"] > 0)
    drag = sum(1 for r in valid if r["z_21d"] < 0)
    movers = [r for r in rows if r["contribution_7d"] is not None]
    top_mover = max(movers, key=lambda r: abs(r["contribution_7d"] or 0), default=None)
    top_support = max(valid, key=lambda r: r["z_21d"], default=None)
    top_drag = min(valid, key=lambda r: r["z_21d"], default=None)

    if score is None:
        brief = ["Growth Impulses does not yet have enough valid component history for a full read."]
    else:
        brief = _driver_brief(
            driver_name="Growth Impulses",
            driver_short="GII",
            score=score,
            valid=valid,
            supportive=supportive,
            drag=drag,
            top_mover=top_mover,
            top_support=top_support,
            top_drag=top_drag,
        )

    return {
        "intro": "Growth Impulses asks whether global growth/risk appetite is accelerating or fading.",
        "sort_note": (
            "Rows sort by absolute current z-score (|current z|), so the strongest "
            f"positive or negative signals rise first; 7-day contribution is still "
            f"proxied as each input's 7-day fast z-score change divided by the "
            f"{component_count} growth-impulse components."
        ),
        "score": score,
        "supportive_count": supportive,
        "drag_count": drag,
        "rows": rows,
        "brief": brief,
    }

def calc_growth_impulse(data: pd.DataFrame) -> pd.DataFrame:
    """
    Growth Impulses Index (GII) — Dual ROC composite.
    Returns DataFrame with 'fast' and 'slow' columns.
    """
    components = growth_impulse_components(data)
    if not components:
        return pd.DataFrame(index=data.index)

    # Compute z-scored ROCs for each component at both speeds
    fast_zs = []
    slow_zs = []

    for name, series in components.items():
        sig_fast, sig_slow = _growth_impulse_component_signals(name, series)
        z_fast = clip_series(zscore(sig_fast, GROWTH_IMPULSE_Z_LEN), GROWTH_IMPULSE_CLIP_Z)
        z_slow = clip_series(zscore(sig_slow, GROWTH_IMPULSE_Z_LEN), GROWTH_IMPULSE_CLIP_Z)

        fast_zs.append(z_fast)
        slow_zs.append(z_slow)

    # Weighted average (equal weight, skip NaN)
    fast_df = pd.concat(fast_zs, axis=1)
    slow_df = pd.concat(slow_zs, axis=1)

    gii_fast_raw = fast_df.mean(axis=1, skipna=True)
    gii_slow_raw = slow_df.mean(axis=1, skipna=True)

    # EMA smooth (skip if EMA_LEN == 1)
    gii_fast = ema(gii_fast_raw, GROWTH_IMPULSE_EMA_LEN) if GROWTH_IMPULSE_EMA_LEN > 1 else gii_fast_raw
    gii_slow = ema(gii_slow_raw, GROWTH_IMPULSE_EMA_LEN) if GROWTH_IMPULSE_EMA_LEN > 1 else gii_slow_raw

    return pd.DataFrame({"fast": gii_fast, "slow": gii_slow}, index=data.index)

def _raw_components_from_specs(data: pd.DataFrame, specs: dict[str, dict]) -> dict[str, pd.Series]:
    return {key: data[key] for key in specs if key in data}


def _z_components_from_raw(
    components: dict[str, pd.Series],
    lookback: int,
    *,
    invert: bool = False,
) -> dict[str, pd.Series]:
    sign = -1 if invert else 1
    return {key: sign * zscore(series, lookback) for key, series in components.items()}


def _mmi_driver_drilldown(
    *,
    driver_name: str,
    driver_short: str,
    intro: str,
    specs: dict[str, dict],
    raw_components: dict[str, pd.Series],
    z_components: dict[str, pd.Series],
    composite: pd.DataFrame | None = None,
    include_values: bool = True,
) -> dict:
    rows = []
    chart_index = composite.index if composite is not None and len(composite.index) else None
    if chart_index is None:
        first = next(iter(raw_components.values()), None)
        chart_index = first.index if first is not None else pd.Index([])
    component_count = len(specs) or 1

    for key, spec in specs.items():
        raw = raw_components.get(key)
        z = z_components.get(key)
        if raw is None or z is None:
            continue
        z_change_7d = _component_delta(z, 5)
        z_change_30d = _component_delta(z, 21)
        contribution_7d = (
            round(float(z_change_7d) / component_count, 6) if z_change_7d is not None else None
        )
        row = {
            "key": key,
            "label": spec["label"],
            "group": spec["group"],
            "source": spec["source"],
            "explanation": spec["explanation"],
            "unit": spec["unit"],
            "current": _latest_component_value(raw),
            "z_21d": _latest_component_value(z),
            "z_change_7d": z_change_7d,
            "z_change_30d": z_change_30d,
            "contribution_7d": contribution_7d,
        }
        if include_values:
            row["values"] = _component_values(raw, chart_index)
        rows.append(row)

    spec_order = list(specs)
    rows = sorted(
        rows,
        key=lambda r: (-abs(r["z_21d"] or 0), spec_order.index(r["key"])),
    )

    score = (
        _latest_component_value(composite["composite"])
        if composite is not None and "composite" in composite
        else None
    )
    valid = [r for r in rows if r["z_21d"] is not None]
    supportive = sum(1 for r in valid if r["z_21d"] > 0)
    drag = sum(1 for r in valid if r["z_21d"] < 0)
    movers = [r for r in rows if r["contribution_7d"] is not None]
    top_mover = max(movers, key=lambda r: abs(r["contribution_7d"] or 0), default=None)
    top_support = max(valid, key=lambda r: r["z_21d"], default=None)
    top_drag = min(valid, key=lambda r: r["z_21d"], default=None)

    if score is None:
        brief = [f"{driver_name} does not yet have enough valid component history for a full read."]
    else:
        brief = _driver_brief(
            driver_name=driver_name,
            driver_short=driver_short,
            score=score,
            valid=valid,
            supportive=supportive,
            drag=drag,
            top_mover=top_mover,
            top_support=top_support,
            top_drag=top_drag,
        )

    return {
        "intro": intro,
        "sort_note": (
            f"Rows sort by absolute current z-score (|current z|), so the strongest "
            f"positive or negative {driver_short} signals rise first; 7-day contribution "
            f"is still proxied as each input's 7-day z-score change divided by the "
            f"{component_count} {driver_name.lower()} components."
        ),
        "score": score,
        "supportive_count": supportive,
        "drag_count": drag,
        "rows": rows,
        "brief": brief,
    }


def financial_conditions_drilldown(
    data: pd.DataFrame,
    fincon: pd.DataFrame | None = None,
    *,
    include_values: bool = True,
) -> dict:
    raw_components = _raw_components_from_specs(data, FINANCIAL_CONDITIONS_SPECS)
    z_components = _z_components_from_raw(raw_components, 252, invert=True)
    return _mmi_driver_drilldown(
        driver_name="Financial Conditions",
        driver_short="FinCon",
        intro="Financial Conditions asks whether volatility and credit stress are loosening or tightening.",
        specs=FINANCIAL_CONDITIONS_SPECS,
        raw_components=raw_components,
        z_components=z_components,
        composite=fincon,
        include_values=include_values,
    )


def sector_breadth_drilldown(
    data: pd.DataFrame,
    breadth: pd.DataFrame | None = None,
    *,
    include_values: bool = True,
) -> dict:
    raw_components = _raw_components_from_specs(data, SECTOR_BREADTH_SPECS)
    z_components = _z_components_from_raw(raw_components, 90)
    return _mmi_driver_drilldown(
        driver_name="Sector Breadth",
        driver_short="Breadth",
        intro="Sector Breadth asks whether cyclical equity participation is broadening or narrowing.",
        specs=SECTOR_BREADTH_SPECS,
        raw_components=raw_components,
        z_components=z_components,
        composite=breadth,
        include_values=include_values,
    )


def calc_financial_conditions(data: pd.DataFrame) -> pd.DataFrame:
    """
    Financial Conditions Composite — equal-weight z-score, INVERTED.
    Higher = looser conditions = good for risk assets (consistent with other indicators).
    Returns DataFrame with 'composite' and individual component columns.
    """
    LOOKBACK = 252  # optimized (was 126)
    components = {}

    # Optimized: VIX + MOVE + HY only (drop IG/BAMLC0A0CM)
    # Negate each component so higher = lower stress = better
    for col in FINANCIAL_CONDITIONS_SPECS:
        if col in data:
            components[col] = -zscore(data[col], LOOKBACK)

    if not components:
        return pd.DataFrame(index=data.index)

    zdf = pd.DataFrame(components)
    composite = zdf.mean(axis=1, skipna=True)
    zdf["composite"] = composite
    return zdf

def calc_sector_breadth(data: pd.DataFrame) -> pd.DataFrame:
    """
    US Equity Sector Breadth — equal-weight z-score of 8 sector ETFs.
    """
    LOOKBACK = 90   # optimized for drawdown: was 63 (originally 252)
    tickers = list(SECTOR_BREADTH_SPECS)  # optimized: drop SLX
    components = {}

    for t in tickers:
        if t in data:
            components[t] = zscore(data[t], LOOKBACK)

    if not components:
        return pd.DataFrame(index=data.index)

    zdf = pd.DataFrame(components)
    composite = zdf.mean(axis=1, skipna=True)
    zdf["composite"] = composite
    return zdf

def calc_business_cycle(data: pd.DataFrame) -> pd.DataFrame:
    """
    Business Cycle Composite — combines real economy data, monetary conditions,
    market signals, and labor into one structural cycle indicator.

    4 categories, each z-scored and equal-weighted at the category level:

    1. REAL ECONOMY: CFNAI + Industrial Production + Housing Starts + Building Permits
       (the actual fundamental economic activity)

    2. CREDIT & MONEY: Net Liquidity + 3M-10Y curve + Real rates + SLOOS
       (monetary policy and credit conditions)

    3. MARKETS: Cyclicals vs SPX (industrials, micro-caps, transports, small caps)
       (what equity markets are pricing about the cycle)

    4. LABOR: Inverted jobless claims (initial + continuing)
       (employment health — the most reliable leading recession indicator)

    Inflation (breakevens) kept as separate scorecard item — it tells you the
    character of the cycle, not the direction.
    """
    LOOKBACK = 252
    LIQ_ROC_LEN = 63
    YOY_LEN = 252  # year-over-year for monthly series

    all_components = {}

    # ── Category 1: REAL ECONOMY ────────────────────────────────────────
    real_parts = {}
    if "CFNAI" in data:
        # CFNAI is already a normalized index — use directly
        real_parts["cfnai"] = zscore(data["CFNAI"], LOOKBACK)
    if "INDPRO" in data:
        # Industrial production: use YoY growth z-score
        real_parts["indpro"] = zscore(roc(data["INDPRO"], YOY_LEN), LOOKBACK)
    if "HOUST" in data:
        real_parts["houst"] = zscore(roc(data["HOUST"], YOY_LEN), LOOKBACK)
    if "PERMIT" in data:
        real_parts["permit"] = zscore(roc(data["PERMIT"], YOY_LEN), LOOKBACK)

    if real_parts:
        all_components["real_economy"] = pd.DataFrame(real_parts).mean(axis=1, skipna=True)

    # ── Category 2: LABOR ───────────────────────────────────────────────
    labor_parts = {}
    if "ICSA" in data:
        labor_parts["initial"] = zscore(-data["ICSA"], LOOKBACK)
    if "CCSA" in data:
        labor_parts["continuing"] = zscore(-data["CCSA"], LOOKBACK)
    if labor_parts:
        all_components["labor"] = pd.DataFrame(labor_parts).mean(axis=1, skipna=True)

    # ── Credit & Money (context only — not in growth composite) ─────────
    # Kept for scorecard visibility but excluded from composite: these are
    # leading/financial-conditions indicators, not current-growth measures.
    credit_parts = {}
    if all(col in data for col in ["WALCL", "WTREGEN", "RRPONTSYD"]):
        net_liq = data["WALCL"] - data["WTREGEN"] - data["RRPONTSYD"]
        credit_parts["liquidity"] = zscore(roc(net_liq, LIQ_ROC_LEN), LOOKBACK)
    if "DGS10" in data and "DGS3MO" in data:
        credit_parts["curve_3m10y"] = zscore(data["DGS10"] - data["DGS3MO"], LOOKBACK)
    if "DFII10" in data:
        credit_parts["real_rates"] = zscore(-data["DFII10"], LOOKBACK)
    if "DRTSCILM" in data:
        credit_parts["sloos"] = zscore(-data["DRTSCILM"], LOOKBACK)

    if not all_components:
        return pd.DataFrame(index=data.index)

    result = pd.DataFrame(all_components)
    # Composite = Real Economy + Labor only (the two clean growth measures)
    growth_cols = [c for c in ["real_economy", "labor"] if c in result.columns]
    result["composite"] = result[growth_cols].mean(axis=1, skipna=True)

    # Attach credit_money separately for scorecard display
    if credit_parts:
        result["credit_money"] = pd.DataFrame(credit_parts).mean(axis=1, skipna=True)

    return result

def calc_inflation_context(data: pd.DataFrame) -> pd.DataFrame:
    """
    Inflation context — combines forward-looking (breakevens) and realized (CPI YoY).
    Not directional (rising inflation can be good or bad depending on level).
    Kept separate from Business Cycle Composite as context.
    """
    LOOKBACK = 252
    components = {}

    # Forward-looking: market expectations
    if "T5YIE" in data:
        components["breakeven_5y"] = zscore(data["T5YIE"], LOOKBACK)
    if "T10YIE" in data:
        components["breakeven_10y"] = zscore(data["T10YIE"], LOOKBACK)

    # Realized: actual CPI year-over-year
    # CPI is monthly data forward-filled to daily. YoY = pct change over 252 trading days.
    if "CPIAUCSL" in data:
        cpi_yoy = data["CPIAUCSL"].pct_change(365) * 100
        components["cpi_yoy"] = zscore(cpi_yoy, LOOKBACK)
    if "CPILFESL" in data:
        core_cpi_yoy = data["CPILFESL"].pct_change(365) * 100
        components["core_cpi_yoy"] = zscore(core_cpi_yoy, LOOKBACK)

    if not components:
        return pd.DataFrame(index=data.index)

    zdf = pd.DataFrame(components)
    zdf["composite"] = zdf.mean(axis=1, skipna=True)
    return zdf

def _sahm_rule(unrate: pd.Series) -> pd.Series:
    """
    Sahm Rule = (3-month MA of unemployment rate) − (12-month low of that MA).
    Has historically crossed +0.5pp at the start of every US recession since 1970.
    Index here is calendar-day frequency, so 3m ≈ 90d, 12m ≈ 365d.
    """
    ma3 = unrate.rolling(90, min_periods=30).mean()
    low12 = ma3.rolling(365, min_periods=120).min()
    return ma3 - low12

def _zscore(series: pd.Series, lookback: int) -> pd.Series:
    roll = series.rolling(lookback, min_periods=lookback // 2)
    return (series - roll.mean()) / roll.std()

RELEASE_LAGS_DAYS = {
    "PCEC96":   60,  # BEA Personal Income & Outlays — ~last day of next month
    "UNRATE":   35,  # BLS Employment Situation — first Friday of next month
    "RPI":      60,  # BEA Personal Income & Outlays — bundled with PCE
    "GDPNOW":    0,  # Atlanta Fed nowcast — real-time
    "CPILFESL": 45,  # BLS CPI release — ~mid next month
}

# Unified-stress production parameters promoted from task-34 Phase 1.
# Basis: full-sample Calmar grid across SPX/IWM/BTC plus 70/30 IS/OOS validation.
# They govern the MRMI macro buffer erosion and dashboard stress score. Re-fit
# annually, with care: changing them restates strategy semantics and Supabase
# historical stress values.
UNIFIED_STRESS_ALPHA = 0.75
UNIFIED_STRESS_BETA = 0.50
UNIFIED_STRESS_LAMBDA = 10.0
UNIFIED_STRESS_BUFFER_SIZE = 0.5
UNIFIED_STRESS_THRESHOLD = 0.75
UNIFIED_STRESS_P99 = 10.0083

BUCKET_CUTOFF_CALM_WATCH = 3.0
BUCKET_CUTOFF_WATCH_BUILDING = 5.0
BUCKET_CUTOFF_BUILDING_ELEV = 7.0

STRESS_SCORE_BUCKETS = {
    "calm": (0.0, BUCKET_CUTOFF_CALM_WATCH),
    "watch": (BUCKET_CUTOFF_CALM_WATCH, BUCKET_CUTOFF_WATCH_BUILDING),
    "building": (BUCKET_CUTOFF_WATCH_BUILDING, BUCKET_CUTOFF_BUILDING_ELEV),
    "elevated": (BUCKET_CUTOFF_BUILDING_ELEV, 10.0),
}

MRMI_CASH_THRESHOLD = -0.50
MRMI_LONG_THRESHOLD = 0.25
MRMI_CAUTION_EXPOSURE = 0.75

def mrmi_posture(value: float | None) -> str | None:
    """Map MRMI value to the production allocation posture."""
    if value is None or pd.isna(value):
        return None
    if value < MRMI_CASH_THRESHOLD:
        return "CASH"
    if value > MRMI_LONG_THRESHOLD:
        return "LONG"
    return "CAUTION"

def mrmi_exposure(value: float | None) -> float | None:
    """Map MRMI value to the production exposure weight."""
    posture = mrmi_posture(value)
    if posture == "CASH":
        return 0.0
    if posture == "CAUTION":
        return MRMI_CAUTION_EXPOSURE
    if posture == "LONG":
        return 1.0
    return None

def mrmi_legacy_state(value: float | None) -> str | None:
    """Backward-compatible LONG/CASH state for constrained downstream schemas."""
    exposure = mrmi_exposure(value)
    if exposure is None:
        return None
    return "LONG" if exposure > 0 else "CASH"

def _lagged(series: pd.Series, days: int) -> pd.Series:
    """Shift forward in time so each value first appears on its actual release date."""
    if days <= 0:
        return series
    return series.shift(days)

def stress_score_bucket(score: float | None) -> str | None:
    """Bucket a 0–10 unified-stress score using fixed round cutoffs."""
    if score is None or pd.isna(score):
        return None
    if score < BUCKET_CUTOFF_CALM_WATCH:
        return "calm"
    if score < BUCKET_CUTOFF_WATCH_BUILDING:
        return "watch"
    if score < BUCKET_CUTOFF_BUILDING_ELEV:
        return "building"
    return "elevated"

def calc_milk_road_macro_index(momentum: pd.Series, macro_ctx: dict,
                               buffer_size: float = UNIFIED_STRESS_BUFFER_SIZE,
                               threshold: float = UNIFIED_STRESS_THRESHOLD) -> dict:
    """
    Milk Road Macro Index (MRMI) — single quantified signal that combines:
      · Momentum Score (MMI — composite of GII / Breadth / FinCon)
      · Unified Macro Stress (growth weakness OR rising inflation, amplified when both hit)
      · Action threshold (subtracted from the raw score before posture mapping)

    Formula:
        g              = max(0, -Real_Economy_score)
        i              = max(0, Inflation_direction_pp)
        stress_raw     = α·g + β·i + λ·g·i
        stress_norm    = clip(stress_raw / stress_p99, 0, 1)
        macro_buffer   = buffer_size × (1 − stress_norm)
        MRMI           = MMI + macro_buffer − threshold

    Production posture:
        MRMI < -0.50          → CASH    (0% exposure)
        -0.50 <= MRMI <= 0.25 → CAUTION (75% exposure)
        MRMI > 0.25           → LONG    (100% exposure)

    Defaults are locked task-34 production parameters selected by Calmar grid
    search and IS/OOS validation across SPX/IWM/BTC.

    Returns dict with the index series + intermediate components for transparency.
    """
    re_score = macro_ctx.get("real_economy_score")
    inf_dir = macro_ctx.get("inflation_dir_pp")

    if re_score is None or inf_dir is None:
        nan_series = pd.Series(np.nan, index=momentum.index)
        return {
            "mrmi": nan_series,
            "raw": nan_series,
            "momentum": momentum,
            "stress_intensity": nan_series,
            "stress_score": nan_series,
            "stress_score_bucket": pd.Series([None] * len(momentum.index), index=momentum.index),
            "growth_weakness": nan_series,
            "inflation_pressure_raw": nan_series,
            "macro_buffer": nan_series,
            "buffer_size": buffer_size,
            "threshold": threshold,
        }

    re = re_score.reindex(momentum.index)
    inf = inf_dir.reindex(momentum.index)

    growth_weakness = (-re).clip(lower=0)
    inflation_pressure_raw = inf.clip(lower=0)
    stress_raw = (
        UNIFIED_STRESS_ALPHA * growth_weakness
        + UNIFIED_STRESS_BETA * inflation_pressure_raw
        + UNIFIED_STRESS_LAMBDA * growth_weakness * inflation_pressure_raw
    )
    stress_intensity = (stress_raw / UNIFIED_STRESS_P99).clip(lower=0.0, upper=1.0)
    stress_score = stress_intensity * 10.0
    stress_bucket_series = stress_score.map(stress_score_bucket)

    macro_buffer = buffer_size * (1.0 - stress_intensity)
    raw = momentum + macro_buffer
    mrmi = raw - threshold

    return {
        "mrmi": mrmi,
        "raw": raw,
        "momentum": momentum,
        "stress_intensity": stress_intensity,
        "stress_score": stress_score,
        "stress_score_bucket": stress_bucket_series,
        "growth_weakness": growth_weakness,
        "inflation_pressure_raw": inflation_pressure_raw,
        "macro_buffer": macro_buffer,
        "buffer_size": buffer_size,
        "threshold": threshold,
    }

def calc_macro_context(data: pd.DataFrame, lookback_years: int = 3, apply_release_lags: bool = True) -> dict:
    """
    Macro context — Real Economy Composite + Inflation Direction.

      Real Economy Score — z-scored composite of monthly real-economy indicators:
        · Real PCE YoY %       (consumer growth, ~70% of GDP)
        · Sahm Rule (inverted) (forward-looking labor stress)
        · Real Personal Income YoY %
        · Atlanta Fed GDPNow   (real-time GDP nowcast)
        Positive = expanding, negative = deteriorating.

      Inflation Direction — Core CPI YoY 6-month change, in pp.

    apply_release_lags=True (default) shifts each indicator forward by its
    actual publication lag, so backtests don't use data that wouldn't have
    been available in real time. Set to False to compare against the unlagged
    (look-ahead) baseline.
    """
    YEAR = 365
    LB = YEAR * lookback_years
    out = {}

    def _get(col):
        if col not in data:
            return pd.Series(np.nan, index=data.index)
        s = data[col]
        if apply_release_lags:
            s = _lagged(s, RELEASE_LAGS_DAYS.get(col, 0))
        return s

    # ── Real Economy Composite ──────────────────────────────
    components = {}
    raw = {}

    pce_series = _get("PCEC96")
    pce_yoy = pce_series.pct_change(YEAR) * 100
    raw["pce_yoy"] = pce_yoy
    components["pce"] = _zscore(pce_yoy, LB)

    unrate_series = _get("UNRATE")
    sahm = _sahm_rule(unrate_series)
    raw["sahm_rule"] = sahm
    components["labor_inv"] = -_zscore(sahm, LB)

    rpi_series = _get("RPI")
    income_yoy = rpi_series.pct_change(YEAR) * 100
    raw["income_yoy"] = income_yoy
    components["income"] = _zscore(income_yoy, LB)

    gdpnow_series = _get("GDPNOW")
    raw["gdpnow"] = gdpnow_series
    components["gdpnow"] = _zscore(gdpnow_series, LB)

    comp_df = pd.DataFrame(components)
    real_economy = comp_df.mean(axis=1, skipna=True)

    out["real_economy_score"] = real_economy
    out["real_economy_components"] = comp_df
    out["real_economy_raw"] = raw

    # ── Inflation Direction ─────────────────────────────────
    cpi_series = _get("CPILFESL")
    core_cpi_yoy = cpi_series.pct_change(YEAR) * 100
    out["core_cpi_yoy_pct"] = core_cpi_yoy
    out["inflation_dir_pp"] = core_cpi_yoy.diff(180)  # 6-month change

    out["lookback_years"] = lookback_years
    out["release_lags_applied"] = apply_release_lags

    return out

def calc_composite(gii: pd.DataFrame, fincon: pd.DataFrame,
                   breadth: pd.DataFrame) -> pd.Series:
    """
    Equal-weighted Momentum Score (MMI) — average of GII, Breadth, FinCon.
    Convention: positive = good for risk assets.

    Switched to equal weights from prior alpha-weighting (7.6/7.3/5.8) per the
    drawdown-optimization grid search — equal weights deliver stronger Calmar
    ratios across SPX/IWM/BTC and survive OOS validation better.
    """
    W_GII = 1.0
    W_BREADTH = 1.0
    W_FINCON = 1.0
    W_TOTAL = W_GII + W_BREADTH + W_FINCON

    gii_c = gii["fast"]
    fincon_c = fincon["composite"] if "composite" in fincon else pd.Series(np.nan, index=gii.index)
    breadth_c = breadth["composite"] if "composite" in breadth else pd.Series(np.nan, index=gii.index)

    composite = (gii_c * W_GII + breadth_c * W_BREADTH + fincon_c * W_FINCON) / W_TOTAL
    return composite

def prepare_chart_data(data, composite, gii, fincon, breadth, business_cycle, inflation_ctx, macro_ctx=None, mrmi_combined=None) -> str:
    """Convert all indicator data to JSON for the frontend."""

    # Use GII index as the date reference (aligned with data)
    dates = [d.strftime("%Y-%m-%d") for d in gii.index]

    def to_list(s):
        """Convert series to JSON-safe list (NaN -> null)."""
        return [round(v, 4) if pd.notna(v) else None for v in s]

    # Background colors for composite (green > 0, red < 0)
    def bg_colors_single(series, green_above=True):
        colors = []
        for v in series:
            if pd.isna(v) or v is None:
                colors.append(None)
            elif green_above:
                colors.append("#4CAF50" if v > 0 else "#E84B5A")
            else:
                colors.append("#E84B5A" if v > 0 else "#4CAF50")
        return colors

    # Price data (normalized to 100 at start of visible window — done in JS)
    btc = data["BTC-USD"].reindex(gii.index) if "BTC-USD" in data else pd.Series(np.nan, index=gii.index)
    spx = data["^GSPC"].reindex(gii.index) if "^GSPC" in data else pd.Series(np.nan, index=gii.index)
    iwm = data["IWM"].reindex(gii.index) if "IWM" in data else pd.Series(np.nan, index=gii.index)

    # Backtest stats
    def calc_backtest(signal_series, price_series, green_above=True):
        """Calculate returns during green vs red regimes."""
        daily_ret = price_series.pct_change()
        aligned = pd.DataFrame({"signal": signal_series, "ret": daily_ret}).dropna()
        if len(aligned) == 0:
            return {"green_ann": None, "red_ann": None, "green_pct": None}

        if green_above:
            green = aligned["signal"] > 0
        else:
            green = aligned["signal"] < 0

        green_ret = aligned.loc[green, "ret"]
        red_ret = aligned.loc[~green, "ret"]

        green_ann = float(green_ret.mean() * 252) if len(green_ret) > 0 else 0
        red_ann = float(red_ret.mean() * 252) if len(red_ret) > 0 else 0
        green_pct = float(green.sum() / len(aligned) * 100)

        return {
            "green_ann": round(green_ann * 100, 1),
            "red_ann": round(red_ann * 100, 1),
            "green_pct": round(green_pct, 0),
        }

    composite_signal = composite.reindex(gii.index)

    # Helper to reindex a series to gii.index and convert to list
    def reindex_list(series):
        return to_list(series.reindex(gii.index))

    # Business cycle composite
    bc_composite_values = to_list(business_cycle["composite"].reindex(gii.index)) if "composite" in business_cycle else []

    # Scorecard entries
    scorecard = {
        "gii_fast": {
            "values": to_list(gii["fast"].reindex(gii.index)),
            "label": "GII (Growth Impulses)",
            "green_above": True,
            "type": "regime",
            "desc": "Composite of 10 macro components: credit (HYG, HY spread), sector rotation (consumer discretionary vs staples, industrials vs utilities, high beta vs low vol), copper, inverted VIX, yield curve, weekly economic index, and shipping. Measures the rate of change of economic momentum. <strong>Above zero = growth accelerating</strong>, below zero = decelerating. Fast-moving signal (21-day rate of change).",
        },
        "fincon": {
            "values": reindex_list(fincon["composite"]) if "composite" in fincon else [],
            "label": "Financial Conditions",
            "green_above": True,
            "type": "regime",
            "desc": "Z-score composite of VIX (equity volatility), MOVE (bond volatility), and high-yield credit spreads, inverted so higher = looser conditions. <strong>Above zero = loose conditions</strong> (green, favorable for risk assets), below zero = tight conditions (red, unfavorable). Slow-moving structural signal (252-day lookback).",
        },
        "breadth": {
            "values": reindex_list(breadth["composite"]) if "composite" in breadth else [],
            "label": "Sector Breadth",
            "green_above": True,
            "type": "regime",
            "desc": "Z-score of 7 cyclical sector ETFs: semiconductors (SMH), small caps (IWM), transports (IYT), biotech (IBB), homebuilders (XHB), banks (KBE), and retail (XRT). Measures how broadly the market rally extends across cyclical sectors. <strong>Above zero = broad participation</strong> (green, healthy rally), below zero = narrow or deteriorating breadth (red).",
        },
        "bc_real_economy": {
            "values": reindex_list(business_cycle["real_economy"]) if "real_economy" in business_cycle else [],
            "label": "Real Economy",
            "green_above": True,
            "type": "cycle",
            "desc": "Combined z-score of fundamental economic activity: Chicago Fed National Activity Index (a weighted composite of 85 monthly indicators), Industrial Production growth, Housing Starts, and Building Permits. Housing data leads the economy by 6-12 months. <strong>Above zero = economy expanding</strong>, below zero = contracting.",
        },
        "bc_credit_money": {
            "values": reindex_list(business_cycle["credit_money"]) if "credit_money" in business_cycle else [],
            "label": "Credit & Money",
            "green_above": True,
            "type": "cycle",
            "desc": "Combined z-score of monetary conditions: Net Fed Liquidity (balance sheet minus TGA minus reverse repo), 3M-10Y yield curve (the Fed's preferred recession indicator), inverted Real Rates (10Y TIPS), and inverted SLOOS lending standards (Senior Loan Officer Survey). <strong>Above zero = accommodative</strong> (loose money, easy credit), below zero = restrictive.",
        },
        "bc_markets": {
            "values": reindex_list(business_cycle["markets"]) if "markets" in business_cycle else [],
            "label": "Markets (Cyclicals)",
            "green_above": True,
            "type": "cycle",
            "desc": "Performance of cyclical equities (industrials basket, micro-caps, transports, small caps) relative to the S&P 500. When cyclicals outperform, the market is pricing in economic expansion. When they underperform, it signals defensive positioning and potential slowdown.",
        },
        "bc_labor": {
            "values": reindex_list(business_cycle["labor"]) if "labor" in business_cycle else [],
            "label": "Labor Market",
            "green_above": True,
            "type": "cycle",
            "desc": "Inverted z-score of initial and continuing jobless claims. One of the best leading indicators of recession — claims rise 3-6 months before downturns. <strong>Above zero = strong labor market</strong> (claims below average), below zero = weakening (claims rising).",
        },
        "inflation": {
            "values": reindex_list(inflation_ctx["composite"]) if "composite" in inflation_ctx else [],
            "label": "Inflation (Breakevens)",
            "green_above": None,
            "type": "context",
            "desc": "Z-score of 5-year and 10-year breakeven inflation rates (derived from TIPS spreads). Reflects the market's expectation of future inflation. Rising from low levels can be reflationary (positive for growth assets). Rising from high levels signals overheating. This is context, not a directional signal — interpretation depends on the level and cycle phase.",
        },
    }

    chart_data = {
        "dates": dates,
        "btc": to_list(btc),
        "spx": to_list(spx),
        "iwm": to_list(iwm),
        "growth_impulse": growth_impulse_drilldown(data, gii),
        "sector_breadth": sector_breadth_drilldown(data, breadth),
        "financial_conditions": financial_conditions_drilldown(data, fincon),
        "composite": {
            "value": to_list(composite.reindex(gii.index)),
            "bg": bg_colors_single(composite.reindex(gii.index), green_above=True),
            "bt_btc": calc_backtest(composite_signal, btc, green_above=True),
            "bt_spx": calc_backtest(composite_signal, spx, green_above=True),
        },
        "business_cycle": {
            "value": bc_composite_values,
            "bg": [],  # filled below with season colors
        },
        "scorecard": scorecard,
        "inflation_trend": _compute_inflation_trend(data),
    }

    # Milk Road Macro Index time series (the new headline composite)
    if mrmi_combined:
        stress_bucket_series = mrmi_combined["stress_score_bucket"].reindex(gii.index)
        chart_data["mrmi_combined"] = {
            "value":                     to_list(mrmi_combined["mrmi"].reindex(gii.index)),
            "momentum":                  to_list(mrmi_combined["momentum"].reindex(gii.index)),
            "stress_intensity":          to_list(mrmi_combined["stress_intensity"].reindex(gii.index)),
            "stress_score":              to_list(mrmi_combined["stress_score"].reindex(gii.index)),
            "growth_weakness":           to_list(mrmi_combined["growth_weakness"].reindex(gii.index)),
            "inflation_pressure_raw":    to_list(mrmi_combined["inflation_pressure_raw"].reindex(gii.index)),
            "stress_score_bucket":       [v if pd.notna(v) else None for v in stress_bucket_series],
            "macro_buffer":              to_list(mrmi_combined["macro_buffer"].reindex(gii.index)),
        }

    # Macro context — Real Economy Composite + Inflation Direction
    if macro_ctx:
        chart_data["macro_ctx"] = {
            "real_economy_score": to_list(macro_ctx["real_economy_score"].reindex(gii.index)),
            "inflation_dir_pp":   to_list(macro_ctx["inflation_dir_pp"].reindex(gii.index)),
            "core_cpi_yoy_pct":   to_list(macro_ctx["core_cpi_yoy_pct"].reindex(gii.index)),
        }
        comps = macro_ctx.get("real_economy_components")
        if comps is not None and not comps.empty:
            chart_data["macro_ctx"]["components"] = {
                col: to_list(comps[col].reindex(gii.index)) for col in comps.columns
            }
        raw = macro_ctx.get("real_economy_raw") or {}
        chart_data["macro_ctx"]["raw"] = {
            k: to_list(v.reindex(gii.index)) for k, v in raw.items() if v is not None
        }

    # ── Season classification → MRCI chart background colors ──────────────────
    _season_colors = ['#A8D86E', '#FF8C00', '#E84B5A', '#4DA8DA']
    _season_names  = ['SPRING', 'SUMMER', 'FALL', 'WINTER']
    seasons_current = -1  # 0=spring,1=summer,2=fall,3=winter, -1=unknown

    if "composite" in business_cycle and "CPILFESL" in data:
        mrci_s  = business_cycle["composite"].reindex(gii.index)
        # Core CPI YoY minus 2% Fed target — positive = above target, negative = below
        # Use 365 rows (calendar-day index has ~365 rows/year, not 252 trading days)
        core_yoy   = data["CPILFESL"].pct_change(365) * 100
        infl_x     = (core_yoy - 2.0).reindex(gii.index)

        def _classify(m, ir):
            if pd.isna(m) or pd.isna(ir):
                return None
            if m > 0 and ir <= 0: return 0   # Spring
            if m > 0 and ir > 0:  return 1   # Summer
            if m <= 0 and ir > 0: return 2   # Fall
            return 3                          # Winter

        season_series = [_classify(m, ir) for m, ir in zip(mrci_s, infl_x)]

        # Current season
        for s in reversed(season_series):
            if s is not None:
                seasons_current = s
                break

        # Background color per data point for MRCI chart
        chart_data["business_cycle"]["bg"] = [
            _season_colors[s] if s is not None else None
            for s in season_series
        ]

        # Core CPI YoY - 2% for compass X-axis
        chart_data["business_cycle"]["infl_roc"] = to_list(infl_x)

        # Raw inflation inputs for the Macro Seasons chart table (latest value + full series for charts)
        def _latest_val(series):
            s = series.dropna()
            return round(float(s.iloc[-1]), 2) if len(s) else None

        headline_yoy = data["CPIAUCSL"].pct_change(365) * 100 if "CPIAUCSL" in data else None
        chart_data["compass_inflation"] = {
            "core_cpi":     _latest_val(core_yoy),
            "headline_cpi": _latest_val(headline_yoy) if headline_yoy is not None else None,
            "t5yie":        _latest_val(data["T5YIE"]) if "T5YIE" in data else None,
            "t10yie":       _latest_val(data["T10YIE"]) if "T10YIE" in data else None,
        }

        # Add series to scorecard so expand-chart works for each row
        scorecard["ci_core_cpi"] = {
            "values": to_list(core_yoy.reindex(gii.index)),
            "label": "Core CPI YoY", "green_above": None, "type": "context",
            "unit": "pct",
            "desc": "Core CPI year-over-year % change (excludes food & energy). The X-axis driver for the Macro Seasons. Center line = Fed 2% target.",
        }
        if headline_yoy is not None:
            scorecard["ci_headline_cpi"] = {
                "values": to_list(headline_yoy.reindex(gii.index)),
                "label": "Headline CPI YoY", "green_above": None, "type": "context",
                "desc": "Headline CPI year-over-year % change (includes food & energy). More volatile than core due to commodity swings.",
            }
        if "T5YIE" in data:
            scorecard["ci_5y_bei"] = {
                "values": reindex_list(data["T5YIE"]),
                "label": "5Y Breakeven", "green_above": None, "type": "context",
                "desc": "5-year inflation breakeven rate — the market's expectation for average inflation over the next 5 years, derived from TIPS vs nominal Treasuries.",
            }
        if "T10YIE" in data:
            scorecard["ci_10y_bei"] = {
                "values": reindex_list(data["T10YIE"]),
                "label": "10Y Breakeven", "green_above": None, "type": "context",
                "desc": "10-year inflation breakeven rate — the market's expectation for average inflation over the next 10 years.",
            }

    return json.dumps(chart_data), seasons_current

def _compute_inflation_trend(data: pd.DataFrame) -> dict:
    """
    Compute inflation trend from actual underlying values (not z-scores).
    Returns: {direction: 'heating'|'cooling'|'stable', headline_cpi: %, change_30d: %}
    """
    if "CPIAUCSL" not in data:
        return {"direction": "unknown", "headline_cpi": None, "change_30d": None}

    cpi = data["CPIAUCSL"].dropna()
    # Get unique monthly values (data is forward-filled)
    cpi_monthly = cpi[cpi.diff() != 0]
    if len(cpi_monthly) < 13:
        return {"direction": "unknown", "headline_cpi": None, "change_30d": None}

    # Latest YoY
    latest = cpi_monthly.iloc[-1]
    year_ago = cpi_monthly.iloc[-13]  # 12 months back
    yoy_now = (latest / year_ago - 1) * 100

    # YoY one month ago
    if len(cpi_monthly) >= 14:
        one_month_ago = cpi_monthly.iloc[-2]
        year_before_that = cpi_monthly.iloc[-14]
        yoy_prev = (one_month_ago / year_before_that - 1) * 100
        change = yoy_now - yoy_prev
    else:
        change = 0

    if change > 0.10:
        direction = "heating"
    elif change < -0.10:
        direction = "cooling"
    else:
        direction = "stable"

    return {
        "direction": direction,
        "headline_cpi": round(float(yoy_now), 2),
        "change_30d": round(float(change), 2),
    }

def _latest(series) -> float | None:
    """Return the latest non-NaN value from a pandas Series, or None."""
    s = series.dropna()
    if len(s) == 0:
        return None
    v = s.iloc[-1]
    try:
        return float(v)
    except (TypeError, ValueError):
        return None

def _latest_label(series) -> str | None:
    """Return the latest non-NaN label from a pandas Series, or None."""
    s = series.dropna()
    if len(s) == 0:
        return None
    v = s.iloc[-1]
    return str(v) if v is not None else None

def save_snapshot(data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx=None, mrmi_combined=None) -> Path:
    """Save a compact JSON snapshot of today's key metrics for daily-brief diffing."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Latest composite / drivers (from our z-scored signals)
    composite_v = _latest(composite)
    snapshot = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "build_time_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "mrmi": {
            "composite": composite_v,
            "state": ("green" if (composite_v is not None and composite_v > 0)
                      else "red" if composite_v is not None else None),
        },
        "components": {
            "gii_fast": _latest(gii["fast"]) if "fast" in gii else None,
            "fincon": _latest(fincon["composite"]) if "composite" in fincon else None,
            "breadth": _latest(breadth["composite"]) if "composite" in breadth else None,
        },
        "mrci": {
            "composite": _latest(biz_cycle["composite"]) if "composite" in biz_cycle else None,
            "real_economy": _latest(biz_cycle["real_economy"]) if "real_economy" in biz_cycle else None,
            "credit_money": _latest(biz_cycle["credit_money"]) if "credit_money" in biz_cycle else None,
            "markets": _latest(biz_cycle["markets"]) if "markets" in biz_cycle else None,
            "labor": _latest(biz_cycle["labor"]) if "labor" in biz_cycle else None,
        },
        "inflation": _latest(infl_ctx["composite"]) if "composite" in infl_ctx else None,
        "growth_impulse_drilldown": growth_impulse_drilldown(data, gii, include_values=False),
        "sector_breadth_drilldown": sector_breadth_drilldown(data, breadth, include_values=False),
        "financial_conditions_drilldown": financial_conditions_drilldown(data, fincon, include_values=False),
    }

    # Milk Road Macro Index (combined headline signal)
    if mrmi_combined:
        mrmi_v = _latest(mrmi_combined["mrmi"])
        snapshot["mrmi_combined"] = {
            "value": mrmi_v,
            "state": mrmi_posture(mrmi_v),
            "legacy_state": mrmi_legacy_state(mrmi_v),
            "exposure": mrmi_exposure(mrmi_v),
            "cash_threshold": MRMI_CASH_THRESHOLD,
            "long_threshold": MRMI_LONG_THRESHOLD,
            "momentum": _latest(mrmi_combined["momentum"]),
            "stress_intensity": _latest(mrmi_combined["stress_intensity"]),
            "stress_score": _latest(mrmi_combined["stress_score"]),
            "growth_weakness": _latest(mrmi_combined["growth_weakness"]),
            "inflation_pressure_raw": _latest(mrmi_combined["inflation_pressure_raw"]),
            "stress_score_bucket": _latest_label(mrmi_combined["stress_score_bucket"]),
            "macro_buffer": _latest(mrmi_combined["macro_buffer"]),
            "buffer_size": mrmi_combined.get("buffer_size", UNIFIED_STRESS_BUFFER_SIZE),
            "threshold": mrmi_combined.get("threshold", UNIFIED_STRESS_THRESHOLD),
        }

    # Macro context — Real Economy Composite + Inflation Direction
    if macro_ctx:
        comps = macro_ctx.get("real_economy_components")
        comps_latest = {}
        if comps is not None and not comps.empty:
            for col in comps.columns:
                comps_latest[col] = _latest(comps[col])
        raw = macro_ctx.get("real_economy_raw") or {}
        snapshot["macro"] = {
            "real_economy_score":     _latest(macro_ctx["real_economy_score"]),
            "real_economy_components": comps_latest,
            "inflation_dir_pp":       _latest(macro_ctx["inflation_dir_pp"]),
            "core_cpi_yoy_pct":       _latest(macro_ctx["core_cpi_yoy_pct"]),
            "raw": {k: _latest(v) for k, v in raw.items()},
        }

    # Raw underlier levels — useful for LLM narrative
    underlier_keys = [
        "^GSPC", "IWM", "BTC-USD", "^VIX", "^MOVE", "^TNX",
        "HYG", "HG=F", "GC=F", "DBC",
        "DGS10", "DGS2", "DGS3MO", "DFII10",
        "BAMLH0A0HYM2", "T5YIE", "T10YIE",
        "ICSA", "CCSA", "DTWEXBGS",
        "WALCL", "WTREGEN", "RRPONTSYD",
    ]
    underliers = {}
    for k in underlier_keys:
        if k in data:
            underliers[k] = _latest(data[k])
    snapshot["underliers"] = underliers

    path = SNAPSHOT_DIR / f"{snapshot['date']}.json"
    with open(path, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"Snapshot saved to {path}")
    return path
