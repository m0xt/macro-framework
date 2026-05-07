#!/usr/bin/env python3
"""
Macro Framework Dashboard
=========================
Fetches market data, computes 4 macro risk indicators, and generates
a self-contained HTML dashboard with interactive charts.

Indicators:
  1. Growth Impulses Index (GII) — dual-speed ROC composite of 10 macro components
  2. Financial Conditions Composite — z-score of VIX, MOVE, HY & IG spreads
  3. US Equity Sector Breadth — z-score of 8 cyclical sector ETFs

Usage:
  python build.py              # Fetch (cached), calculate, build dashboard
  python build.py --no-cache   # Force re-fetch all data
  python build.py --open       # Open dashboard in browser after building
"""

import json
import sys
import subprocess
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf

CACHE_DIR = Path(__file__).parent / ".cache"
DATA_CACHE = CACHE_DIR / "raw_data.pkl"
OUTPUT_FILE = CACHE_DIR / "dashboard.html"
SNAPSHOT_DIR = CACHE_DIR / "snapshots"
BRIEF_FILE = CACHE_DIR / "brief.html"

# ============================================================================
# SECTION 1: DATA FETCHING
# ============================================================================

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
    "PCEPILFE": "Core PCE",
    "GDPC1": "Real GDP (chained 2017 dollars)",
    "GDPPOT": "Real Potential GDP (CBO, chained 2017 dollars)",
    "M2SL": "M2 Money Supply (US)",
    "GDPNOW": "Atlanta Fed GDPNow nowcast",
    "PCEC96": "Real Personal Consumption Expenditures",
    "UNRATE": "Unemployment Rate",
    "RPI": "Real Personal Income",
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


def fetch_all_data(use_cache: bool = True) -> pd.DataFrame:
    """Fetch and align all data into a single DataFrame."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if use_cache and DATA_CACHE.exists():
        age_hours = (datetime.now().timestamp() - DATA_CACHE.stat().st_mtime) / 3600
        if age_hours < 12:
            print(f"  Using cached data ({age_hours:.1f}h old)")
            return pd.read_pickle(DATA_CACHE)

    print("Fetching data...")
    yf_data = fetch_yfinance(YF_TICKERS)
    fred_data = fetch_fred(list(FRED_SERIES.keys()))

    # Align to common daily index
    combined = pd.concat([yf_data, fred_data], axis=1)
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


# ============================================================================
# SECTION 2: INDICATOR CALCULATIONS
# ============================================================================

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


def calc_growth_impulse(data: pd.DataFrame) -> pd.DataFrame:
    """
    Growth Impulses Index (GII) — Dual ROC composite.
    Returns DataFrame with 'fast' and 'slow' columns.
    """
    FAST_ROC = 21      # optimized (was 42)
    SLOW_ROC = 126     # optimized (was 252)
    Z_LEN = 504
    CLIP_Z = 3.0
    EMA_LEN = 1        # optimized: no smoothing (was 21)

    # Build component series
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

    # Compute z-scored ROCs for each component at both speeds
    fast_zs = []
    slow_zs = []

    for name, series in components.items():
        # Use change instead of ROC for near-zero/negative series
        if name in ("YC", "WEI", "BAML_INV", "VIX_INV", "BDI_SA"):
            sig_fast = chg(series, FAST_ROC)
            sig_slow = chg(series, SLOW_ROC)
        else:
            sig_fast = roc(series, FAST_ROC)
            sig_slow = roc(series, SLOW_ROC)

        z_fast = clip_series(zscore(sig_fast, Z_LEN), CLIP_Z)
        z_slow = clip_series(zscore(sig_slow, Z_LEN), CLIP_Z)

        fast_zs.append(z_fast)
        slow_zs.append(z_slow)

    # Weighted average (equal weight, skip NaN)
    fast_df = pd.concat(fast_zs, axis=1)
    slow_df = pd.concat(slow_zs, axis=1)

    gii_fast_raw = fast_df.mean(axis=1, skipna=True)
    gii_slow_raw = slow_df.mean(axis=1, skipna=True)

    # EMA smooth (skip if EMA_LEN == 1)
    gii_fast = ema(gii_fast_raw, EMA_LEN) if EMA_LEN > 1 else gii_fast_raw
    gii_slow = ema(gii_slow_raw, EMA_LEN) if EMA_LEN > 1 else gii_slow_raw

    return pd.DataFrame({"fast": gii_fast, "slow": gii_slow}, index=data.index)


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
    for col in ["^VIX", "^MOVE", "BAMLH0A0HYM2"]:
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
    tickers = ["SMH", "IWM", "IYT", "IBB", "XHB", "KBE", "XRT"]  # optimized: drop SLX
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


# Release lags from observation date to public release (calendar days).
# Used to avoid look-ahead bias: at date T, only data actually released by T
# should influence the Macro Composite.
RELEASE_LAGS_DAYS = {
    "PCEC96":   60,  # BEA Personal Income & Outlays — ~last day of next month
    "UNRATE":   35,  # BLS Employment Situation — first Friday of next month
    "RPI":      60,  # BEA Personal Income & Outlays — bundled with PCE
    "GDPNOW":    0,  # Atlanta Fed nowcast — real-time
    "CPILFESL": 45,  # BLS CPI release — ~mid next month
}


def _lagged(series: pd.Series, days: int) -> pd.Series:
    """Shift forward in time so each value first appears on its actual release date."""
    if days <= 0:
        return series
    return series.shift(days)


def calc_milk_road_macro_index(momentum: pd.Series, macro_ctx: dict,
                                 buffer_size: float = 1.0, threshold: float = 0.5) -> dict:
    """
    Milk Road Macro Index (MRMI) — single quantified signal that combines:
      · Momentum Score (MMI — composite of GII / Breadth / FinCon)
      · Macro Stress (positive only when in stagflation territory)
      · Action threshold (subtracted from the raw score so MRMI > 0 means LONG)

    Formula:
        raw  = MMI + buffer_size × (1 − Stress_intensity)
        MRMI = raw − threshold

    Where Stress_intensity is bounded [0, 1] and positive only when the economy is
    in stagflation territory (Real Economy negative AND Inflation Direction positive):
        Stress_raw       = max(0, −RE_score) × max(0, Inflation_dir)
        Stress_intensity = min(1, Stress_raw)

    Action:
        MRMI > 0 → STAY LONG  (raw > threshold)
        MRMI < 0 → CASH       (raw < threshold)

    The default buffer_size=1.0 and threshold=0.5 were selected by the drawdown
    optimization grid search to maximize Calmar ratio (return/|max DD|) across
    SPX/IWM/BTC. This makes MRMI active ~20% of the time (vs ~3% under prior
    buffer=2.0/threshold=0 settings), generating real drawdown protection plus
    positive alpha on equities.

    Returns dict with the index series + intermediate components for transparency.
    """
    re_score = macro_ctx.get("real_economy_score")
    inf_dir = macro_ctx.get("inflation_dir_pp")

    if re_score is None or inf_dir is None:
        nan_series = pd.Series(np.nan, index=momentum.index)
        return {
            "mrmi": nan_series, "momentum": momentum,
            "stress_intensity": nan_series, "macro_buffer": nan_series,
        }

    # Align to momentum's index
    re = re_score.reindex(momentum.index)
    inf = inf_dir.reindex(momentum.index)

    re_neg = (-re).clip(lower=0)        # positive when RE < 0
    inf_pos = inf.clip(lower=0)         # positive when inflation rising
    stress_raw = re_neg * inf_pos
    stress_intensity = stress_raw.clip(upper=1.0)

    macro_buffer = buffer_size * (1.0 - stress_intensity)
    raw = momentum + macro_buffer
    mrmi = raw - threshold  # bake threshold into the value so > 0 = LONG

    return {
        "mrmi": mrmi,
        "raw": raw,                       # MMI + macro_buffer (pre-threshold)
        "momentum": momentum,
        "stress_intensity": stress_intensity,
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


# ============================================================================
# SECTION 3: CHART DATA PREPARATION
# ============================================================================

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
        chart_data["mrmi_combined"] = {
            "value":            to_list(mrmi_combined["mrmi"].reindex(gii.index)),
            "momentum":         to_list(mrmi_combined["momentum"].reindex(gii.index)),
            "stress_intensity": to_list(mrmi_combined["stress_intensity"].reindex(gii.index)),
            "macro_buffer":     to_list(mrmi_combined["macro_buffer"].reindex(gii.index)),
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


# ============================================================================
# SECTION 4: HTML TEMPLATE
# ============================================================================

def build_html(chart_json: str, build_time: str, brief_html: str = "",
               seasons_current: int = -1) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Macro Framework</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', system-ui, sans-serif;
    background: #0a0a0a;
    color: #e0e0e0;
    height: 100vh;
    overflow-y: auto;
  }}
  header {{
    padding: 10px 20px;
    background: #111;
    border-bottom: 1px solid #222;
    display: flex;
    justify-content: space-between;
    align-items: center;
    position: sticky;
    top: 0;
    z-index: 10;
  }}
  .header-left {{
    display: flex;
    align-items: center;
    gap: 20px;
  }}
  header h1 {{
    font-size: 14px;
    font-weight: 600;
    color: #888;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }}
  .filters {{
    display: flex;
    gap: 4px;
  }}
  .filter-btn {{
    font-size: 11px;
    font-weight: 500;
    padding: 4px 10px;
    border-radius: 4px;
    border: 1px solid #333;
    background: transparent;
    color: #666;
    cursor: pointer;
    transition: all 0.15s;
  }}
  .filter-btn:hover {{
    border-color: #555;
    color: #999;
  }}
  .filter-btn.active {{
    background: #f59e0b22;
    border-color: #f59e0b55;
    color: #f59e0b;
  }}
  .stats {{
    font-size: 11px;
    color: #444;
  }}
  .charts {{
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }}
  .chart-panel {{
    background: #111;
    border: 1px solid #1a1a1a;
    border-radius: 6px;
    overflow: hidden;
  }}
  .chart-header {{
    padding: 10px 16px 6px;
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }}
  .chart-header h2 {{
    font-size: 13px;
    font-weight: 600;
    color: #ccc;
  }}
  .chart-header .value {{
    font-size: 13px;
    font-family: 'SF Mono', Menlo, monospace;
    font-weight: 600;
  }}
  .chart-header .value.positive {{ color: #4CAF50; }}
  .chart-header .value.negative {{ color: #E84B5A; }}
  .chart-header .value.neutral {{ color: #888; }}
  .chart-desc {{
    padding: 6px 16px 12px;
    font-size: 11px;
    line-height: 1.5;
    color: #444;
  }}
  .chart-desc strong {{ color: #555; }}
  .info-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 1.5px solid #555;
    color: #555;
    font-size: 9px;
    font-style: italic;
    font-weight: 700;
    cursor: default;
    margin-left: 6px;
    vertical-align: middle;
    flex-shrink: 0;
    line-height: 1;
    transition: border-color 0.15s, color 0.15s;
  }}
  .info-icon:hover {{ border-color: #aaa; color: #aaa; }}
  #info-tooltip {{
    display: none;
    position: fixed;
    max-width: 280px;
    background: #1c1c1e;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 11px;
    line-height: 1.6;
    color: #bbb;
    z-index: 9999;
    pointer-events: none;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6);
  }}
  #info-tooltip strong {{ color: #ddd; }}
  .chart-container {{
    padding: 0 8px 4px;
    height: 280px;
  }}
  .legend-row {{
    padding: 2px 16px 8px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }}
  .legend-item {{
    font-size: 10px;
    color: #555;
    display: flex;
    align-items: center;
    gap: 4px;
  }}
  .legend-dot {{
    width: 8px;
    height: 8px;
    border-radius: 50%;
  }}
  .backtest {{
    padding: 4px 16px 6px;
    display: flex;
    gap: 20px;
    font-size: 10px;
    color: #555;
  }}
  .backtest .stat {{
    display: flex;
    gap: 4px;
    align-items: center;
  }}
  .backtest .stat .g {{ color: #4CAF50; font-family: 'SF Mono', Menlo, monospace; }}
  .backtest .stat .r {{ color: #E84B5A; font-family: 'SF Mono', Menlo, monospace; }}

  /* Scorecard */
  .scorecard {{ margin: 0 12px; }}
  .scorecard table {{ width: 100%; border-collapse: collapse; }}
  .scorecard th {{
    font-size: 10px; color: #444; text-transform: uppercase; letter-spacing: 0.5px;
    text-align: left; padding: 6px 12px; border-bottom: 1px solid #1a1a1a;
  }}
  .scorecard .group-header td {{
    font-size: 10px; color: #555; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.5px; padding: 10px 12px 4px; border: none;
  }}
  .scorecard td {{
    padding: 8px 12px; border-bottom: 1px solid #111; cursor: pointer;
    font-size: 12px; transition: background 0.1s;
  }}
  .scorecard tr:hover td {{ background: #151515; }}
  .scorecard .val {{ font-family: 'SF Mono', Menlo, monospace; font-weight: 500; }}
  .scorecard .val.pos {{ color: #4CAF50; }}
  .scorecard .val.neg {{ color: #E84B5A; }}
  .scorecard .val.neutral {{ color: #555; }}
  .scorecard .dir {{ font-size: 11px; }}
  .scorecard .dir {{ font-family: 'SF Mono', Menlo, monospace; }}
  .scorecard .dir.up {{ color: #4CAF50; }}
  .scorecard .dir.down {{ color: #E84B5A; }}
  .scorecard .dir.flat {{ color: #444; }}
  .scorecard .dot.blue {{ background: #4DA8DA; }}
  .scorecard .chg {{ font-size: 10px; color: #555; margin-left: 2px; }}
  .scorecard .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; }}
  .scorecard .dot.green {{ background: #4CAF50; }}
  .scorecard .dot.red {{ background: #E84B5A; }}
  .scorecard .dot.grey {{ background: #444; }}
  .proximity-wrap {{ margin-top: 5px; }}
  .proximity-track {{
    height: 2px; background: #1e1e1e; border-radius: 1px;
    width: 100%; max-width: 140px; position: relative; overflow: hidden;
  }}
  .proximity-fill {{ height: 100%; border-radius: 1px; transition: width 0.3s; }}
  .proximity-label {{
    font-size: 10px; margin-top: 3px; letter-spacing: 0.2px;
    font-family: 'SF Mono', Menlo, monospace;
  }}
  .proximity-label.far {{ color: #444; }}
  .proximity-label.mid {{ color: #f59e0b; }}
  .proximity-label.near {{ color: #E84B5A; }}
  .expanded-chart {{ display: none; padding: 4px 12px 12px; }}
  .expanded-chart.active {{ display: block; }}
  .expanded-chart .chart-wrap {{ position: relative; height: 180px; width: 100%; }}

  /* ── Smooth scroll ── */
  html {{ scroll-behavior: smooth; }}

  /* ── Section nav ── */
  .section-nav {{
    display: flex; gap: 2px; align-items: center;
  }}
  .snav-btn {{
    font-size: 11px; font-weight: 500; padding: 4px 10px;
    border-radius: 4px; border: 1px solid transparent;
    color: #555; cursor: pointer; background: transparent;
    text-decoration: none; transition: all 0.15s; white-space: nowrap;
    font-family: inherit;
  }}
  .snav-btn:hover {{ color: #999; border-color: #333; }}
  .snav-btn.active {{ background: #ffffff0f; border-color: #333; color: #ccc; }}

  /* ── Header right cluster ── */
  .header-right {{ display: flex; align-items: center; gap: 16px; }}

  /* ── Mini floating regime badge ── */
  #mini-badge {{
    position: fixed; top: 52px; right: 16px; z-index: 9;
    display: flex; align-items: center; gap: 8px;
    background: #111; border: 1px solid #222; border-radius: 6px;
    padding: 6px 12px; cursor: pointer;
    opacity: 0; pointer-events: none;
    transition: opacity 0.2s;
  }}
  #mini-badge.visible {{ opacity: 1; pointer-events: auto; }}
  #mini-badge-label {{ font-size: 12px; font-weight: 700; letter-spacing: 0.5px; }}
  #mini-badge-val {{
    font-size: 12px; font-family: 'SF Mono', Menlo, monospace;
    font-weight: 600; color: #ccc;
  }}
  #mini-badge-hint {{ font-size: 10px; color: #444; }}

  /* ── Brief collapse ── */
  .drivers-toggle {{
    width: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 11px 16px;
    background: #111;
    border: none;
    border-top: 1px solid #222;
    border-bottom: 1px solid #222;
    cursor: pointer;
    color: #888;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    text-align: left;
    transition: background 0.15s, color 0.15s;
    margin-top: 4px;
  }}
  .drivers-toggle:hover {{ background: #161616; color: #bbb; }}
  .drivers-toggle.open {{ color: #ccc; background: #141414; border-bottom-color: #1a1a1a; }}
  .drivers-toggle-left {{ display: flex; align-items: center; gap: 8px; }}
  .drivers-toggle-pip {{
    width: 6px; height: 6px; border-radius: 50%;
    background: #333;
    flex-shrink: 0;
    transition: background 0.15s;
  }}
  .drivers-toggle.open .drivers-toggle-pip {{ background: #4CAF50; }}
  #toggle-compass-inputs.open .drivers-toggle-pip {{ background: #FF8C00; }}
  #toggle-cycle-chart.open .drivers-toggle-pip {{ background: #4DA8DA; }}
  .drivers-toggle-hint {{
    font-size: 10px;
    color: #444;
    font-weight: 400;
    letter-spacing: 0;
    text-transform: none;
  }}
  .drivers-toggle.open .drivers-toggle-hint {{ color: #555; }}
  .drivers-toggle-chevron {{
    font-size: 10px;
    color: #444;
    transition: transform 0.2s, color 0.15s;
    flex-shrink: 0;
  }}
  .drivers-toggle.open .drivers-toggle-chevron {{ transform: rotate(180deg); color: #666; }}
  .drivers-body {{ display: none; }}
  .drivers-body.open {{ display: block; }}

  .brief-collapse-btn {{
    background: none; border: none; cursor: pointer; color: #555;
    font-size: 14px; padding: 0 0 0 8px; line-height: 1;
    transition: color 0.15s, transform 0.2s;
  }}
  .brief-collapse-btn:hover {{ color: #999; }}
  .brief-card.collapsed .brief-collapse-btn {{ transform: rotate(-90deg); }}
  .brief-card.collapsed .brief-body {{ display: none; }}
</style>
</head>
<body>

<!-- Floating regime badge (hidden until scrolled past hero) -->
<div id="info-tooltip"></div>
<div id="mini-badge" onclick="scrollToSection('section-hero')" title="Back to status">
  <span id="mini-badge-label"></span>
  <span id="mini-badge-val"></span>
  <span id="mini-badge-hint">↑ top</span>
</div>

<header>
  <div class="header-left">
    <h1>Macro Framework</h1>
    <div class="filters">
      <button class="filter-btn" onclick="setRange('1y')">1Y</button>
      <button class="filter-btn active" onclick="setRange('2y')">2Y</button>
      <button class="filter-btn" onclick="setRange('5y')">5Y</button>
      <button class="filter-btn" onclick="setRange('all')">All</button>
      <span style="margin:0 6px;color:#333;">|</span>
      <button class="filter-btn active" id="toggle-spx" onclick="toggleAsset('spx')">S&P 500</button>
      <button class="filter-btn" id="toggle-iwm" onclick="toggleAsset('iwm')">Russell</button>
      <button class="filter-btn" id="toggle-btc" onclick="toggleAsset('btc')">Bitcoin</button>
    </div>
  </div>
  <div class="header-right">
    <nav class="section-nav" id="section-nav">
      <button class="snav-btn" data-target="section-brief" onclick="scrollToSection('section-brief')" title="B">Brief</button>
      <button class="snav-btn" data-target="section-hero" onclick="scrollToSection('section-hero')" title="1">Status</button>
      <button class="snav-btn" data-target="section-mrmi" onclick="scrollToSection('section-mrmi')" title="2">MRMI</button>
      <button class="snav-btn" data-target="section-seasons" onclick="scrollToSection('section-seasons')" title="3">Compass</button>
    </nav>
    <div class="stats">Built {build_time}</div>
  </div>
</header>

<div class="charts">

  <!-- ═══════ HERO STATUS PANEL ═══════ -->
  <div id="section-hero" style="scroll-margin-top:52px"></div>
  <div id="regime-banner" style="margin: 12px 12px 0; padding: 20px 24px; border-radius: 8px; display: grid; grid-template-columns: 1.2fr 1fr; gap: 32px;">
    <!-- LEFT: MRMI signal -->
    <div>
      <div style="display: flex; align-items: baseline; gap: 16px;">
        <span id="regime-label" style="font-size: 28px; font-weight: 700; letter-spacing: 1.5px;"></span>
        <span class="value" id="composite-val" style="font-size: 28px; font-family: 'SF Mono', Menlo, monospace;"></span>
        <span id="conviction-label" style="font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px;"></span>
      </div>

      <!-- Visual gauge -->
      <div style="margin-top: 14px; position: relative; height: 28px;">
        <div style="position: absolute; top: 12px; left: 0; right: 0; height: 4px; background: linear-gradient(to right, #E84B5A22 0%, #E84B5A11 33%, #88888822 50%, #4CAF5011 67%, #4CAF5022 100%); border-radius: 2px;"></div>
        <div style="position: absolute; top: 0; left: 50%; width: 1px; height: 28px; background: #444;"></div>
        <div id="gauge-marker" style="position: absolute; top: 6px; width: 14px; height: 14px; border-radius: 50%; transform: translateX(-50%); border: 2px solid #0a0a0a; transition: left 0.3s, background 0.3s;"></div>
        <div style="display: flex; justify-content: space-between; margin-top: 18px; font-size: 9px; color: #444; font-family: 'SF Mono', Menlo, monospace;">
          <span>-3</span><span>-2</span><span>-1</span><span>0</span><span>+1</span><span>+2</span><span>+3</span>
        </div>
      </div>

      <!-- Trajectory + sparkline -->
      <div style="margin-top: 14px; display: flex; align-items: center; gap: 16px;">
        <div style="font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 0.5px;">Last 30 days</div>
        <canvas id="sparkline" style="height: 36px; width: 200px;"></canvas>
        <div id="regime-changes" style="display: flex; gap: 12px; font-size: 11px; font-family: 'SF Mono', Menlo, monospace;"></div>
      </div>
    </div>

    <!-- RIGHT: Season + secondary indicators -->
    <div style="border-left: 1px solid #222; padding-left: 24px;">
      <div style="font-size: 11px; color: #555; text-transform: uppercase; letter-spacing: 1px;">Macro Seasons</div>
      <div style="display: flex; align-items: baseline; gap: 12px; margin-top: 4px;">
        <span id="season-label" style="font-size: 24px; font-weight: 700;"></span>
        <span id="season-sub" style="font-size: 11px; color: #888;"></span>
      </div>

      <div style="margin-top: 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div>
          <div style="font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 0.5px;">Growth</div>
          <div style="display: flex; align-items: baseline; gap: 8px; margin-top: 2px;">
            <span id="hero-mrci-val" class="value" style="font-size: 18px; font-family: 'SF Mono', Menlo, monospace;"></span>
            <span id="hero-mrci-status" style="font-size: 10px;"></span>
          </div>
        </div>
        <div>
          <div style="font-size: 10px; color: #555; text-transform: uppercase; letter-spacing: 0.5px;">Core CPI <span style="color:#333;text-transform:none;letter-spacing:0;">vs 2% target</span></div>
          <div style="display: flex; align-items: baseline; gap: 8px; margin-top: 2px;">
            <span id="hero-infl-val" class="value" style="font-size: 18px; font-family: 'SF Mono', Menlo, monospace;"></span>
            <span id="hero-infl-status" style="font-size: 10px;"></span>
          </div>
        </div>
      </div>
    </div>
  </div>

  {brief_html}

  <!-- ═══════ TIER 1: MRMI ═══════ -->
  <div id="section-mrmi" style="scroll-margin-top:52px"></div>
  <div class="chart-panel" style="margin-top: 8px;">
    <div class="chart-header">
      <h2>Milk Road Momentum Index (MRMI)<span class="info-icon" data-key="mrmi">i</span></h2>
    </div>
    <div class="legend-row">
      <span class="legend-item"><span class="legend-dot" style="background:#fff"></span>Composite (alpha-weighted)</span>
      <span class="legend-item"><span class="legend-dot" style="background:#f5c842"></span>S&P 500</span>
      <span class="legend-item"><span class="legend-dot" style="background:#E84B9A"></span>Russell</span>
      <span class="legend-item"><span class="legend-dot" style="background:#A78BFA"></span>Bitcoin</span>
    </div>
    <div class="chart-container"><canvas id="chart-composite"></canvas></div>
  </div>

  <!-- ═══════ MRMI Scorecard (the three regime drivers) ═══════ -->
  <button class="drivers-toggle" id="toggle-mrmi-drivers" onclick="toggleDrivers('mrmi-drivers')">
    <span class="drivers-toggle-left">
      <span class="drivers-toggle-pip"></span>
      <span>MRMI Drivers</span>
      <span class="drivers-toggle-hint">GII · Breadth · FinCon — click to expand</span>
    </span>
    <span class="drivers-toggle-chevron">▼</span>
  </button>
  <div class="drivers-body" id="mrmi-drivers">
    <div style="padding: 10px 16px 4px;">
      <p style="font-size: 11px; color: #444; line-height: 1.5;">
        The three alpha-weighted components behind the MRMI signal: <strong style="color:#666;">GII</strong> (global growth momentum, 37%), <strong style="color:#666;">Breadth</strong> (cross-asset breadth, 35%), <strong style="color:#666;">FinCon</strong> (financial conditions, 28%). Click any row to expand the chart.
      </p>
    </div>
    <div class="scorecard" id="scorecard-mrmi"></div>
  </div>

  <!-- ═══════ Business Cycle ═══════ -->
  <div id="section-seasons" style="scroll-margin-top:52px"></div>

  <div style="padding: 24px 16px 8px;">
    <h2 style="font-size: 13px; font-weight: 700; color: #888; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px;">Market Context</h2>
    <p style="font-size: 13px; color: #666; line-height: 1.6; max-width: 640px;">
      The MRMI tells you <em>whether</em> to be invested. The Macro Seasons provides context for <em>where</em> we are in the cycle — useful for understanding the macro environment, but not a buy/sell signal.
    </p>
  </div>

  <div class="chart-panel">
    <div class="chart-header">
      <h2>Macro Seasons<span class="info-icon" data-key="compass">i</span></h2>
      <div id="compass-season-badge" style="font-size:11px;font-weight:700;letter-spacing:1.5px;padding:3px 10px;border-radius:3px;"></div>
    </div>
    <div style="position:relative;width:100%;aspect-ratio:4/3;">
      <canvas id="chart-compass" style="position:absolute;top:0;left:0;width:100%;height:100%;"></canvas>
    </div>
  </div>

  <!-- ═══════ Growth + Inflation time-series ═══════ -->
  <button class="drivers-toggle" id="toggle-cycle-chart" onclick="toggleDrivers('cycle-chart')">
    <span class="drivers-toggle-left">
      <span class="drivers-toggle-pip"></span>
      <span>Growth &amp; Inflation Over Time</span>
      <span class="drivers-toggle-hint">click to expand</span>
    </span>
    <span class="drivers-toggle-chevron">▼</span>
  </button>
  <div class="drivers-body" id="cycle-chart">
    <div class="chart-panel" style="margin-top: 0; border-top: none;">
      <p style="font-size: 11px; color: #444; padding: 12px 16px 8px; line-height: 1.5;">
        The two inputs that position the dot on the Macro Seasons, shown as time series. Growth (left axis) above zero = expanding; Core CPI (right axis) above the dashed line = above the Fed 2% target.
      </p>
      <div class="legend-row" style="padding-top:0;">
        <span class="legend-item"><span class="legend-dot" style="background:#4CAF50"></span>Growth composite (Y-axis)</span>
        <span class="legend-item"><span class="legend-dot" style="background:#FF8C00"></span>Core CPI YoY (X-axis)</span>
        <span class="legend-item" style="color:#555;font-size:10px;">── zero / 2% target</span>
      </div>
      <div class="chart-container"><canvas id="chart-cycle"></canvas></div>
    </div>
  </div>

  <!-- ═══════ Compass Inputs ═══════ -->
  <button class="drivers-toggle" id="toggle-compass-inputs" onclick="toggleDrivers('compass-inputs')">
    <span class="drivers-toggle-left">
      <span class="drivers-toggle-pip"></span>
      <span>Compass Inputs</span>
      <span class="drivers-toggle-hint">Growth (Y-axis) · Inflation (X-axis) — click to expand</span>
    </span>
    <span class="drivers-toggle-chevron">▼</span>
  </button>
  <div class="drivers-body" id="compass-inputs">

    <!-- Y-Axis: Growth -->
    <div style="padding: 12px 16px 4px; border-top: 1px solid #1a1a1a;">
      <div style="display:flex;align-items:baseline;gap:8px;">
        <span style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#4CAF50;background:#0d2010;padding:2px 7px;border-radius:3px;">Y-Axis</span>
        <h3 style="font-size: 12px; font-weight: 600; color: #ccc; margin: 0;">Growth</h3>
        <span id="freshness-growth" style="font-size:10px;color:#333;margin-left:4px;"></span>
      </div>
      <p style="font-size: 11px; color: #444; margin-top: 6px; line-height: 1.5;">Real Economy (CFNAI, industrial production, housing) + Labor (jobless claims). Above zero = expanding; below zero = contracting.</p>
    </div>
    <div class="scorecard" id="scorecard-mrci"></div>

    <!-- X-Axis: Inflation -->
    <div style="padding: 16px 16px 4px; border-top: 1px solid #1a1a1a;">
      <div style="display:flex;align-items:baseline;gap:8px;">
        <span style="font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#FF8C00;background:#1f1200;padding:2px 7px;border-radius:3px;">X-Axis</span>
        <h3 style="font-size: 12px; font-weight: 600; color: #ccc; margin: 0;">Inflation</h3>
        <span id="freshness-inflation" style="font-size:10px;color:#333;margin-left:4px;"></span>
      </div>
      <p style="font-size: 11px; color: #444; margin-top: 6px; line-height: 1.5;">Core CPI YoY minus the Fed 2% target. Right of center = above target; left = below. Tells you the character of the season, not its direction.</p>
    </div>
    <div class="scorecard" id="scorecard-inflation"></div>

  </div>

</div>

<script>
const DATA = {chart_json};
const SEASONS_CURRENT = {seasons_current}; // current season index: 0=Spring 1=Summer 2=Fall 3=Winter
const RANGE_BARS = {{ '1y': 252, '2y': 504, '5y': 1260, 'all': 0 }};
let currentRange = '2y';
let charts = {{}};
let expandedCharts = {{}};
let showSpx = true;
let showBtc = false;
let showIwm = false;

// ── Helpers ──────────────────────────────────────────────

function sliceData(arr, range) {{
  if (!arr || arr.length === 0) return [];
  const n = RANGE_BARS[range];
  return n > 0 ? arr.slice(-n) : arr;
}}

function lastValid(arr) {{
  for (let i = arr.length - 1; i >= 0; i--) {{
    if (arr[i] !== null && arr[i] !== undefined) return arr[i];
  }}
  return null;
}}

function valClass(v) {{
  if (v === null) return 'neutral';
  return v > 0 ? 'positive' : v < 0 ? 'negative' : 'neutral';
}}

function updateValue(id, val) {{
  const el = document.getElementById(id);
  if (!el) return;
  if (val !== null) {{
    el.textContent = val.toFixed(2);
    el.className = 'value ' + valClass(val);
  }} else {{
    el.textContent = '\u2014';
    el.className = 'value neutral';
  }}
}}

// ── Shared chart config ──────────────────────────────────

const GRID_COLOR = '#1a1a1a';
const ZERO_LINE = {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1 }};
const BAND_STYLE = {{ borderColor: '#222', borderWidth: 1, borderDash: [4, 4] }};

function bandLines() {{
  return {{
    zero: ZERO_LINE,
    p1: {{ type: 'line', yMin: 1, yMax: 1, ...BAND_STYLE }},
    m1: {{ type: 'line', yMin: -1, yMax: -1, ...BAND_STYLE }},
    p2: {{ type: 'line', yMin: 2, yMax: 2, ...BAND_STYLE, borderColor: '#1a1a1a' }},
    m2: {{ type: 'line', yMin: -2, yMax: -2, ...BAND_STYLE, borderColor: '#1a1a1a' }},
  }};
}}

function baseOptions(annotations) {{
  return {{
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ display: false }},
      tooltip: {{
        backgroundColor: '#1a1a1a',
        borderColor: '#333',
        borderWidth: 1,
        titleColor: '#999',
        bodyColor: '#e0e0e0',
        titleFont: {{ size: 11 }},
        bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
        padding: 8,
        filter: item => item.dataset.label !== '_bg',
        callbacks: {{
          label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '\u2014'),
        }},
      }},
      annotation: {{ annotations: annotations || bandLines() }},
    }},
    scales: {{
      x: {{
        type: 'category',
        ticks: {{
          color: '#333',
          font: {{ size: 10 }},
          maxTicksLimit: 12,
          maxRotation: 0,
        }},
        grid: {{ display: false }},
      }},
      y: {{
        position: 'left',
        ticks: {{
          color: '#444',
          font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }},
          maxTicksLimit: 7,
        }},
        grid: {{ color: GRID_COLOR }},
      }},
      yPrice: {{
        position: 'right',
        ticks: {{
          color: '#333',
          font: {{ size: 9, family: "'SF Mono', Menlo, monospace" }},
          maxTicksLimit: 5,
        }},
        grid: {{ display: false }},
      }},
      yBg: {{
        display: false,
        min: 0,
        max: 100,
      }},
    }},
  }};
}}

function lineDataset(label, data, color, width) {{
  return {{
    label, data,
    borderColor: color,
    borderWidth: width || 1.5,
    borderDash: [4, 3],
    pointRadius: 0,
    tension: 0.1,
    spanGaps: true,
  }};
}}

// Line with green-above-zero / red-below-zero fill (matches report style).
// If invertColors=true, flip colors (for indicators like FinCon where below 0 = good).
function lineDatasetFilled(label, data, lineColor, invertColors) {{
  const greenColor = invertColors ? 'rgba(232, 75, 90, 0.20)' : 'rgba(76, 175, 80, 0.20)';
  const redColor = invertColors ? 'rgba(76, 175, 80, 0.20)' : 'rgba(232, 75, 90, 0.20)';
  return {{
    label, data,
    borderColor: lineColor,
    borderWidth: 1.8,
    pointRadius: 0,
    tension: 0.1,
    spanGaps: true,
    fill: {{
      target: 'origin',
      above: greenColor,
      below: redColor,
    }},
  }};
}}

function bgBarDataset(colors) {{
  return {{
    label: '_bg',
    data: colors.map(c => c !== null ? 100 : null),
    backgroundColor: colors.map(c => c ? c + '30' : 'transparent'),
    borderWidth: 0,
    barPercentage: 1.0,
    categoryPercentage: 1.0,
    type: 'bar',
    order: 10,
    yAxisID: 'yBg',
  }};
}}

function normalizePrices(arr) {{
  let firstValid = null;
  for (let i = 0; i < arr.length; i++) {{
    if (arr[i] !== null) {{ firstValid = arr[i]; break; }}
  }}
  if (!firstValid) return arr;
  return arr.map(v => v !== null ? (v / firstValid) * 100 : null);
}}

function priceDataset(label, data, color) {{
  return {{
    label, data,
    borderColor: color,
    borderWidth: 2.5,
    pointRadius: 0,
    tension: 0.1,
    spanGaps: true,
    yAxisID: 'yPrice',
    order: 1,
  }};
}}

function priceSets() {{
  const btc = normalizePrices(sliceData(DATA.btc, currentRange));
  const spx = normalizePrices(sliceData(DATA.spx, currentRange));
  const iwm = normalizePrices(sliceData(DATA.iwm, currentRange));
  const sets = [];
  if (showSpx) sets.push(priceDataset('S&P 500', spx, '#f5c842'));
  if (showIwm) sets.push(priceDataset('Russell', iwm, '#E84B9A'));
  if (showBtc) sets.push(priceDataset('Bitcoin', btc, '#A78BFA'));
  return sets;
}}

// ── Backtest stats ───────────────────────────────────────

function renderBacktest(elementId, indicator) {{
  if (!indicator.bt_btc && !indicator.bt_spx) return;
  const el = document.getElementById(elementId);
  if (!el) return;
  const btc = indicator.bt_btc || {{}};
  const spx = indicator.bt_spx || {{}};
  el.innerHTML = `
    <span class="stat">SPX green: <span class="g">${{spx.green_ann !== null ? spx.green_ann + '%' : '\u2014'}}</span></span>
    <span class="stat">SPX red: <span class="r">${{spx.red_ann !== null ? spx.red_ann + '%' : '\u2014'}}</span></span>
    <span class="stat">BTC green: <span class="g">${{btc.green_ann !== null ? btc.green_ann + '%' : '\u2014'}}</span></span>
    <span class="stat">BTC red: <span class="r">${{btc.red_ann !== null ? btc.red_ann + '%' : '\u2014'}}</span></span>
    <span class="stat" style="color:#444">Green ${{spx.green_pct || '\u2014'}}% of time</span>
  `;
}}

// ── Scorecard ────────────────────────────────────────────

const SCORECARD_TABLES = [
  {{ containerId: 'scorecard-mrmi', keys: ['gii_fast', 'fincon', 'breadth'] }},
  {{ containerId: 'scorecard-mrci', keys: ['bc_real_economy', 'bc_labor'] }},
  {{ containerId: 'scorecard-inflation', keys: ['ci_core_cpi'] }},
];

// ── Macro Seasons ─────────────────────────────────────────────────────────
function buildCompass() {{
  const SEASON_META = [
    {{ name: 'SPRING', color: '#A8D86E', sub: 'Growth ↑  ·  Inflation ↓' }},
    {{ name: 'SUMMER', color: '#FF8C00', sub: 'Growth ↑  ·  Inflation ↑' }},
    {{ name: 'FALL',   color: '#E84B5A', sub: 'Growth ↓  ·  Inflation ↑' }},
    {{ name: 'WINTER', color: '#4DA8DA', sub: 'Growth ↓  ·  Inflation ↓' }},
  ];

  const mrci  = DATA.business_cycle.value   || [];
  const iroc  = DATA.business_cycle.infl_roc || [];

  // Build paired points where both axes have data
  const pts = [];
  for (let i = 0; i < Math.min(mrci.length, iroc.length); i++) {{
    if (mrci[i] !== null && iroc[i] !== null) pts.push({{ x: iroc[i], y: mrci[i] }});
  }}
  if (pts.length === 0) return;

  const cur = pts[pts.length - 1];

  // Season for current point
  const seasonIdx = cur.y > 0
    ? (cur.x <= 0 ? 0 : 1)   // Spring or Summer
    : (cur.x > 0  ? 2 : 3);  // Fall or Winter
  const season = SEASON_META[seasonIdx];

  // Update badge
  const badge = document.getElementById('compass-season-badge');
  if (badge) {{
    badge.textContent = season.name;
    badge.style.color = season.color;
    badge.style.border = `1px solid ${{season.color}}55`;
    badge.style.background = `${{season.color}}18`;
  }}

  // Axis limits: 97th percentile of absolute values to clip outliers, ensure current point is always visible
  function quantile97(arr) {{
    const sorted = arr.map(Math.abs).sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length * 0.97)] || 1;
  }}
  const xMax = Math.max(quantile97(pts.map(p => p.x)), Math.abs(cur.x) * 1.15, 0.5);
  const yMax = Math.max(quantile97(pts.map(p => p.y)), Math.abs(cur.y) * 1.15, 0.5);
  // Round up to nearest 0.5 for clean axes
  const xLim = Math.ceil(xMax / 0.5) * 0.5;
  const yLim = Math.ceil(yMax / 0.5) * 0.5;

  // Time marker definitions: bars back from current, display label
  const TIME_MARKERS = [
    {{ n: 21,  label: '1m ago' }},
    {{ n: 63,  label: '3m ago' }},
    {{ n: 126, label: '6m ago' }},
    {{ n: 252, label: '12m ago' }},
  ];

  // Custom plugin: quadrants + gradient trail + time markers (all on canvas)
  const quadrantPlugin = {{
    id: 'quadrants',
    beforeDraw(chart) {{
      const {{ctx, chartArea: {{left, right, top, bottom}}, scales}} = chart;
      const cx = Math.max(left + 1, Math.min(right - 1, scales.x.getPixelForValue(0)));
      const cy = Math.max(top + 1, Math.min(bottom - 1, scales.y.getPixelForValue(0)));

      // Quadrant fills + labels
      const quads = [
        [left, top,   cx-left,   cy-top,     '#A8D86E', 'SPRING', left+10,   top+10,    'left',  'top'],
        [cx,   top,   right-cx,  cy-top,     '#FF8C00', 'SUMMER', right-10,  top+10,    'right', 'top'],
        [cx,   cy,    right-cx,  bottom-cy,  '#E84B5A', 'FALL',   right-10,  bottom-10, 'right', 'bottom'],
        [left, cy,    cx-left,   bottom-cy,  '#4DA8DA', 'WINTER', left+10,   bottom-10, 'left',  'bottom'],
      ];
      quads.forEach(([qx, qy, qw, qh, c, lbl, tx, ty, ha, va]) => {{
        ctx.save();
        ctx.fillStyle = c + '28';
        ctx.fillRect(qx, qy, qw, qh);
        ctx.font = '700 11px monospace';
        ctx.fillStyle = c + 'bb';
        ctx.textAlign = ha;
        ctx.textBaseline = va;
        ctx.fillText(lbl, tx, ty);
        ctx.restore();
      }});

      // Axis dividers
      ctx.save();
      ctx.strokeStyle = '#2a2a2a';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(cx, top); ctx.lineTo(cx, bottom); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(left, cy); ctx.lineTo(right, cy); ctx.stroke();
      ctx.restore();
    }},

    afterDraw(chart) {{
      const {{ctx, chartArea, scales}} = chart;
      // Clip drawing to chart area
      ctx.save();
      ctx.beginPath();
      ctx.rect(chartArea.left, chartArea.top, chartArea.right - chartArea.left, chartArea.bottom - chartArea.top);
      ctx.clip();

      // ── Connecting line through markers → current ────────────────────────
      const markerChain = TIME_MARKERS.slice().reverse()
        .map(tm => {{ const idx = pts.length - 1 - tm.n; return idx >= 0 ? pts[idx] : null; }})
        .filter(Boolean);
      markerChain.push(cur);
      if (markerChain.length > 1) {{
        ctx.save();
        ctx.strokeStyle = '#555';
        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.lineJoin = 'round';
        ctx.beginPath();
        markerChain.forEach((p, i) => {{
          const px = scales.x.getPixelForValue(p.x);
          const py = scales.y.getPixelForValue(p.y);
          i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
        }});
        ctx.stroke();
        ctx.restore();
      }}

      // ── Time markers ─────────────────────────────────────────────────────
      TIME_MARKERS.forEach(tm => {{
        const idx = pts.length - 1 - tm.n;
        if (idx < 0) return;
        const p = pts[idx];
        const px = scales.x.getPixelForValue(p.x);
        const py = scales.y.getPixelForValue(p.y);

        // Dot
        ctx.save();
        ctx.beginPath();
        ctx.arc(px, py, 5, 0, Math.PI * 2);
        ctx.fillStyle = '#555';
        ctx.fill();
        ctx.strokeStyle = '#888';
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.restore();

        // Label with contrasting background pill
        ctx.save();
        ctx.font = 'bold 9px monospace';
        const tw = ctx.measureText(tm.label).width;
        const padX = 4, padY = 2, lh = 10;
        // Position label: prefer above, nudge if near top
        let lx = px - tw / 2 - padX;
        let ly = py - lh - padY * 2 - 7;
        if (ly < chartArea.top + 2) ly = py + 9;
        // Background pill
        ctx.fillStyle = '#0d0d0d';
        ctx.beginPath();
        ctx.roundRect(lx, ly, tw + padX * 2, lh + padY * 2, 3);
        ctx.fill();
        // Text
        ctx.fillStyle = '#999';
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.fillText(tm.label, lx + padX, ly + padY);
        ctx.restore();
      }});

      ctx.restore(); // remove clip
    }},
  }};

  if (charts.compass) {{ charts.compass.destroy(); }}
  charts.compass = new Chart(document.getElementById('chart-compass'), {{
    type: 'scatter',
    data: {{
      datasets: [
        // Current position — large season-colored dot (only Chart.js dataset, for tooltip)
        {{
          type: 'scatter',
          data: [{{ x: cur.x, y: cur.y }}],
          pointRadius: 12,
          pointHoverRadius: 14,
          backgroundColor: season.color,
          borderColor: '#000000',
          borderWidth: 2,
          label: 'Now',
        }},
      ],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      layout: {{ padding: {{ top: 4, right: 8, bottom: 4, left: 4 }} }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          callbacks: {{
            title: () => season.name,
            label: () => [`Growth: ${{cur.y > 0 ? '+' : ''}}${{cur.y.toFixed(2)}}`, `Core CPI YoY: ${{(cur.x + 2).toFixed(1)}}% (${{cur.x > 0 ? '+' : ''}}${{cur.x.toFixed(1)}}pp vs target)`],
          }},
        }},
        annotation: {{ annotations: {{}} }},
      }},
      scales: {{
        x: {{
          type: 'linear',
          min: -xLim, max: xLim,
          title: {{ display: true, text: '← Below 2% Target    Core CPI YoY    Above 2% Target →', color: '#444', font: {{ size: 10 }} }},
          grid: {{ color: '#161616', drawBorder: false }},
          ticks: {{ color: '#444', font: {{ size: 9 }}, maxTicksLimit: 7 }},
          border: {{ color: '#1a1a1a' }},
        }},
        y: {{
          type: 'linear',
          min: -yLim, max: yLim,
          title: {{ display: true, text: 'Growth', color: '#444', font: {{ size: 10 }} }},
          grid: {{ color: '#161616', drawBorder: false }},
          ticks: {{ color: '#444', font: {{ size: 9 }}, maxTicksLimit: 7 }},
          border: {{ color: '#1a1a1a' }},
        }},
      }},
    }},
    plugins: [quadrantPlugin],
  }});
}}

function buildCycleChart() {{
  const dates   = sliceData(DATA.dates, currentRange);
  const growth  = sliceData(DATA.business_cycle.value, currentRange);
  const ciSc    = DATA.scorecard && DATA.scorecard.ci_core_cpi;
  const coreCpi = ciSc ? sliceData(ciSc.values, currentRange) : [];

  if (charts.cycle) {{ charts.cycle.destroy(); }}
  charts.cycle = new Chart(document.getElementById('chart-cycle'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{
          label: 'Growth composite',
          data: growth,
          borderColor: '#4CAF50',
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          yAxisID: 'yGrowth',
        }},
        {{
          label: 'Core CPI YoY (%)',
          data: coreCpi,
          borderColor: '#FF8C00',
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3,
          yAxisID: 'yCpi',
        }},
      ],
    }},
    options: {{
      responsive: true,
      maintainAspectRatio: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#111',
          borderColor: '#333',
          borderWidth: 1,
          callbacks: {{
            label: ctx => ctx.dataset.yAxisID === 'yCpi'
              ? `Core CPI: ${{ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) + '%' : '—'}}`
              : `Growth: ${{ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '—'}}`,
          }},
        }},
        annotation: {{
          annotations: {{
            zeroLine: {{
              type: 'line', yMin: 0, yMax: 0, yScaleID: 'yGrowth',
              borderColor: '#4CAF5033', borderWidth: 1, borderDash: [4, 4],
            }},
            targetLine: {{
              type: 'line', yMin: 2, yMax: 2, yScaleID: 'yCpi',
              borderColor: '#FF8C0033', borderWidth: 1, borderDash: [4, 4],
            }},
          }},
        }},
      }},
      scales: {{
        x: {{
          type: 'category',
          ticks: {{
            color: '#555', maxTicksLimit: 8, maxRotation: 0,
            callback: (v, i) => {{
              const d = dates[i];
              return d ? d.slice(0, 7) : '';
            }},
          }},
          grid: {{ color: '#1a1a1a' }},
        }},
        yGrowth: {{
          type: 'linear', position: 'left',
          ticks: {{ color: '#4CAF5088', maxTicksLimit: 6 }},
          grid: {{ color: '#1a1a1a' }},
          title: {{ display: true, text: 'Growth (z-score)', color: '#4CAF5066', font: {{ size: 10 }} }},
        }},
        yCpi: {{
          type: 'linear', position: 'right',
          ticks: {{
            color: '#FF8C0088', maxTicksLimit: 6,
            callback: v => v.toFixed(1) + '%',
          }},
          grid: {{ drawOnChartArea: false }},
          title: {{ display: true, text: 'Core CPI YoY', color: '#FF8C0066', font: {{ size: 10 }} }},
        }},
      }},
    }},
  }});
}}

function buildScorecard() {{
  const sc = DATA.scorecard;

  SCORECARD_TABLES.forEach(table => {{
    const container = document.getElementById(table.containerId);
    if (!container) return;

    let html = '<table><thead><tr>';
    html += '<th>Indicator</th><th>Value</th><th>7d</th><th>30d</th><th>Signal</th>';
    html += '</tr></thead><tbody>';

    table.keys.forEach(key => {{
      const entry = sc[key];
      if (!entry) return;

      const sliced = sliceData(entry.values, currentRange);
      const current = lastValid(sliced);
      const greenAbove = entry.green_above;
      const itype = entry.type;

      // Value from 7d and 30d ago
      const prev7 = sliced.length > 5 ? lastValid(sliced.slice(0, sliced.length - 5)) : null;
      const prev30 = sliced.length > 21 ? lastValid(sliced.slice(0, sliced.length - 21)) : null;

      // Current value class
      let valCls = 'neutral';
      if (current !== null && greenAbove !== null) {{
        if (greenAbove) {{
          valCls = current > 0 ? 'pos' : 'neg';
        }} else {{
          valCls = current < 0 ? 'pos' : 'neg';
        }}
      }}

      // Direction helper — show % change
      function fmtChg(curr, prev) {{
        if (curr === null || prev === null) return '<span class="dir flat">\u2014</span>';
        const diff = curr - prev;
        // Express as % of the scale (z-scores typically range -3 to +3, so diff of 0.3 ~ 10%)
        const pct = (diff * 100).toFixed(0);
        const sign = diff > 0 ? '+' : '';
        if (Math.abs(diff) < 0.03) return `<span class="dir flat">${{sign}}${{pct}}%</span>`;
        if (diff > 0) return `<span class="dir up">\u25B2 ${{sign}}${{pct}}%</span>`;
        return `<span class="dir down">\u25BC ${{sign}}${{pct}}%</span>`;
      }}

      // Signal: regime = green/red dot, cycle = expanding/contracting text, context = text
      let signalHtml = '<span style="font-size:10px;color:#444;">\u2014</span>';
      if (current !== null) {{
        if (itype === 'regime' && greenAbove !== null) {{
          const isGreen = greenAbove ? current > 0 : current < 0;
          signalHtml = `<span class="dot ${{isGreen ? 'green' : 'red'}}"></span>`;
        }} else if (itype === 'cycle' && greenAbove !== null) {{
          // Cycle: above zero = expanding, below = contracting (based on z-score of the pillar)
          const isPos = greenAbove ? current > 0 : current < 0;
          if (isPos) {{
            signalHtml = '<span style="font-size:10px;color:#4DA8DA;">Expanding</span>';
          }} else {{
            signalHtml = '<span style="font-size:10px;color:#888;">Contracting</span>';
          }}
        }} else if (itype === 'context') {{
          // Inflation: rising vs falling expectations
          const prev = sliced.length > 21 ? lastValid(sliced.slice(0, sliced.length - 21)) : null;
          if (prev !== null) {{
            const diff = current - prev;
            if (diff > 0.05) {{
              signalHtml = '<span style="font-size:10px;color:#FF8C00;">Rising</span>';
            }} else if (diff < -0.05) {{
              signalHtml = '<span style="font-size:10px;color:#4DA8DA;">Falling</span>';
            }} else {{
              signalHtml = '<span style="font-size:10px;color:#888;">Stable</span>';
            }}
          }}
        }}
      }}

      const valStr = current !== null ? current.toFixed(2) : '\u2014';

      // Proximity to flip (threshold = 0)
      let proximityHtml = '';
      if (current !== null && greenAbove !== null) {{
        const dist = Math.abs(current);
        const pct = Math.min(100, (dist / 3) * 100).toFixed(1);
        const fillColor = current > 0 ? '#4CAF50' : '#E84B5A';
        const urgency = dist < 0.3 ? 'near' : dist < 0.75 ? 'mid' : 'far';
        const flipDir = current > 0 ? '↓ to red' : '↑ to green';
        proximityHtml = `
          <div class="proximity-wrap">
            <div class="proximity-track">
              <div class="proximity-fill" style="width:${{pct}}%;background:${{fillColor}}"></div>
            </div>
            <div class="proximity-label ${{urgency}}">${{dist.toFixed(2)}} ${{flipDir}}</div>
          </div>`;
      }}

      html += `<tr class="sc-row" data-key="${{key}}" onclick="toggleExpanded('${{key}}', this)">`;
      const infoIcon = entry.desc ? `<span class="info-icon" data-key="${{key}}">i</span>` : '';
      html += `<td style="color:#999">${{entry.label}}${{infoIcon}}${{proximityHtml}}</td>`;
      html += `<td><span class="val ${{valCls}}">${{valStr}}</span></td>`;
      if (entry.unit === 'pct') {{
        // Monthly data — 7d is always stale, 30d shows the actual monthly move in pp
        const d30 = (current !== null && prev30 !== null) ? current - prev30 : null;
        const pp30 = d30 !== null
          ? `<span class="dir ${{Math.abs(d30) < 0.02 ? 'flat' : d30 > 0 ? 'up' : 'down'}}">${{d30 > 0 ? '▲ +' : d30 < 0 ? '▼ ' : ''}}${{d30.toFixed(2)}}pp</span>`
          : '<span class="dir flat">—</span>';
        html += `<td><span class="dir flat" title="Monthly data — updates once per month">—</span></td>`;
        html += `<td>${{pp30}}</td>`;
      }} else {{
        html += `<td>${{fmtChg(current, prev7)}}</td>`;
        html += `<td>${{fmtChg(current, prev30)}}</td>`;
      }}
      html += `<td>${{signalHtml}}</td>`;
      html += `</tr>`;
      const descHtml = entry.desc ? `<div class="chart-desc">${{entry.desc}}</div>` : '';
      html += `<tr class="expanded-row" id="exp-${{key}}" style="display:none"><td colspan="5"><div class="expanded-chart" id="expc-${{key}}"><div class="chart-wrap"><canvas id="canvas-${{key}}"></canvas></div>${{descHtml}}</div></td></tr>`;
    }});

    html += '</tbody></table>';
    container.innerHTML = html;
  }});
}}

function toggleExpanded(key, rowEl) {{
  const expRow = document.getElementById('exp-' + key);
  const expDiv = document.getElementById('expc-' + key);

  // Temporarily disable smooth scrolling and lock scroll
  const scrollY = window.scrollY;

  if (expRow.style.display === 'none') {{
    // Expand — show row, render chart, then scroll clicked row back into view
    expRow.style.display = '';
    expDiv.classList.add('active');
    createExpandedChart(key);
    window.scrollTo(0, scrollY);
    // Scroll the clicked row into view at the same position
    rowEl.scrollIntoView({{ block: 'nearest', behavior: 'instant' }});
  }} else {{
    // Collapse
    const rowRect = rowEl.getBoundingClientRect();
    expRow.style.display = 'none';
    expDiv.classList.remove('active');
    if (expandedCharts[key]) {{
      expandedCharts[key].destroy();
      delete expandedCharts[key];
    }}
    // Restore scroll so row stays put
    const newRect = rowEl.getBoundingClientRect();
    window.scrollBy(0, newRect.top - rowRect.top);
  }}
}}

function createExpandedChart(key) {{
  const entry = DATA.scorecard[key];
  if (!entry) return;

  // Destroy existing if any
  if (expandedCharts[key]) {{
    expandedCharts[key].destroy();
    delete expandedCharts[key];
  }}

  const dates = sliceData(DATA.dates, currentRange);
  const values = sliceData(entry.values, currentRange);

  const isContext = entry.green_above === null;
  const invert = entry.green_above === false;

  let opts;
  if (isContext) {{
    // Context series (CPI, breakevens): no ±1/±2 bands, auto-scale y to actual data range
    const validVals = values.filter(v => v !== null);
    const dataMin = Math.min(...validVals);
    const dataMax = Math.max(...validVals);
    const pad = (dataMax - dataMin) * 0.1 || 0.5;
    opts = baseOptions({{ zero: ZERO_LINE }});
    opts.scales.y.min = Math.floor((dataMin - pad) * 2) / 2;
    opts.scales.y.max = Math.ceil((dataMax + pad) * 2) / 2;
  }} else {{
    opts = baseOptions(bandLines());
  }}

  const lineDs = isContext
    ? lineDataset(entry.label, values, '#ffffff')
    : lineDatasetFilled(entry.label, values, '#ffffff', invert);

  expandedCharts[key] = new Chart(document.getElementById('canvas-' + key), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [lineDs],
    }},
    options: opts,
  }});
}}

// ── Main charts ──────────────────────────────────────────

function createCharts() {{
  const dates = sliceData(DATA.dates, currentRange);

  // Tier 1: MRMI (filled style: green above zero, red below zero) + price overlays
  charts.composite = new Chart(document.getElementById('chart-composite'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        ...priceSets(),
        lineDatasetFilled('MRMI', sliceData(DATA.composite.value, currentRange), '#ffffff', false),
      ],
    }},
    options: baseOptions(),
  }});

  // Tier 3: Macro Seasons — 2D scatter (Growth × Inflation)
  buildCompass();
  buildCycleChart();

  updateValues();
  buildScorecard();
  updateFreshness();
}}

function updateFreshness() {{
  // Find the last date with a valid value for a given series
  function lastDataDate(series) {{
    const dates = DATA.dates;
    for (let i = series.length - 1; i >= 0; i--) {{
      if (series[i] !== null && series[i] !== undefined) {{
        return dates[i] ? dates[i].slice(0, 10) : null;
      }}
    }}
    return null;
  }}
  function setFreshness(elId, series) {{
    const el = document.getElementById(elId);
    if (!el) return;
    const d = lastDataDate(series);
    el.textContent = d ? 'data as of ' + d : '';
  }}
  setFreshness('freshness-growth', DATA.business_cycle.value);
  const ciSc = DATA.scorecard && DATA.scorecard.ci_core_cpi;
  setFreshness('freshness-inflation', ciSc ? ciSc.values : []);
}}

function updateValues() {{
  const compVal = lastValid(sliceData(DATA.composite.value, currentRange));
  updateValue('composite-val', compVal);
  // compass badge updated via buildCompass()

  // ── Update hero banner ──────────────────────────────
  const banner = document.getElementById('regime-banner');
  const label = document.getElementById('regime-label');
  const conviction = document.getElementById('conviction-label');

  let signalColor;
  if (compVal !== null && compVal > 0) {{
    banner.style.background = '#4CAF5012';
    banner.style.border = '1px solid #4CAF5033';
    label.style.color = '#4CAF50';
    label.textContent = 'RISK-ON';
    signalColor = '#4CAF50';
  }} else {{
    banner.style.background = '#E84B5A12';
    banner.style.border = '1px solid #E84B5A33';
    label.style.color = '#E84B5A';
    label.textContent = 'RISK-OFF';
    signalColor = '#E84B5A';
  }}

  // Conviction strength label
  const absVal = Math.abs(compVal || 0);
  let convictionText = '';
  if (absVal >= 1.5) convictionText = 'high conviction';
  else if (absVal >= 0.5) convictionText = 'moderate conviction';
  else if (absVal > 0) convictionText = 'low conviction';
  conviction.textContent = convictionText;

  // ── Visual gauge ────────────────────────────────────
  const marker = document.getElementById('gauge-marker');
  if (compVal !== null) {{
    const clamped = Math.max(-3, Math.min(3, compVal));
    const pct = ((clamped + 3) / 6) * 100;
    marker.style.left = pct + '%';
    marker.style.background = signalColor;
  }}

  // ── 1d / 7d / 30d changes ───────────────────────────
  const fullValues = DATA.composite.value;
  let lvIdx = fullValues.length - 1;
  while (lvIdx > 0 && (fullValues[lvIdx] === null || fullValues[lvIdx] === undefined)) lvIdx--;
  const cur = fullValues[lvIdx];
  const v1d = lvIdx >= 1 ? fullValues[lvIdx - 1] : null;
  const v7d = lvIdx >= 5 ? fullValues[lvIdx - 5] : null;
  const v30d = lvIdx >= 21 ? fullValues[lvIdx - 21] : null;

  function changeStr(lbl, prev) {{
    if (cur === null || prev === null) return `<span style="color:#444;">${{lbl}} —</span>`;
    const diff = cur - prev;
    const sign = diff >= 0 ? '+' : '';
    const color = diff > 0.05 ? '#4CAF50' : diff < -0.05 ? '#E84B5A' : '#888';
    const arrow = diff > 0.05 ? '\u25B2' : diff < -0.05 ? '\u25BC' : '\u25BA';
    return `<span style="color:#666;">${{lbl}}</span> <span style="color:${{color}};">${{arrow}} ${{sign}}${{diff.toFixed(2)}}</span>`;
  }}
  document.getElementById('regime-changes').innerHTML =
    changeStr('1d', v1d) + changeStr('7d', v7d) + changeStr('30d', v30d);

  // ── 30-day sparkline ────────────────────────────────
  drawSparkline(fullValues.slice(Math.max(0, lvIdx - 30), lvIdx + 1), signalColor);

  // ── Season + secondary indicators ───────────────────
  const mrciVal = lastValid(DATA.business_cycle.value);
  const inflFull = DATA.scorecard.inflation ? DATA.scorecard.inflation.values : [];
  const inflVal = lastValid(inflFull);
  const inflPrev30 = inflFull.length > 21 ? lastValid(inflFull.slice(0, inflFull.length - 21)) : null;
  const inflDir = inflPrev30 !== null ? inflVal - inflPrev30 : 0;

  // Determine season
  // Cycle: positive = expanding, negative = contracting
  // Inflation direction: positive = rising, negative = falling
  const cycleUp = mrciVal !== null && mrciVal > 0;
  const inflRising = inflDir > 0.05;
  const inflFalling = inflDir < -0.05;
  let seasonName, seasonColor, seasonSub;
  if (cycleUp && (inflFalling || Math.abs(inflDir) <= 0.05)) {{
    seasonName = 'SPRING'; seasonColor = '#A8D86E';
    seasonSub = 'Cycle ↑ + Inflation ↓';
  }} else if (cycleUp && inflRising) {{
    seasonName = 'SUMMER'; seasonColor = '#FF8C00';
    seasonSub = 'Cycle ↑ + Inflation ↑';
  }} else if (!cycleUp && inflRising) {{
    seasonName = 'FALL'; seasonColor = '#E84B5A';
    seasonSub = 'Cycle ↓ + Inflation ↑';
  }} else {{
    seasonName = 'WINTER'; seasonColor = '#4DA8DA';
    seasonSub = 'Cycle ↓ + Inflation ↓';
  }}

  const seasonEl = document.getElementById('season-label');
  seasonEl.textContent = seasonName;
  seasonEl.style.color = seasonColor;
  document.getElementById('season-sub').textContent = seasonSub;

  // Growth hero
  const mrciValEl = document.getElementById('hero-mrci-val');
  if (mrciVal !== null) {{
    mrciValEl.textContent = (mrciVal > 0 ? '+' : '') + mrciVal.toFixed(2);
    mrciValEl.style.color = mrciVal > 0 ? '#4CAF50' : '#E84B5A';
  }}
  document.getElementById('hero-mrci-status').innerHTML = mrciVal > 0
    ? '<span style="color:#4DA8DA;">Expanding (above avg)</span>'
    : '<span style="color:#888;">Contracting (below avg)</span>';

  // Inflation hero — show Core CPI vs 2% target (the actual compass X-axis driver)
  const inflTrend = DATA.inflation_trend || {{}};
  const ci = DATA.compass_inflation || {{}};
  const inflValEl = document.getElementById('hero-infl-val');
  if (ci.core_cpi !== null && ci.core_cpi !== undefined) {{
    const vsTarget = ci.core_cpi - 2;
    inflValEl.textContent = ci.core_cpi.toFixed(2) + '%';
    inflValEl.style.color = vsTarget > 0 ? '#FF8C00' : '#4CAF50';
  }}

  // Direction based on actual Core CPI trend
  let inflStatus = '<span style="color:#888;">► Stable</span>';
  if (inflTrend.direction === 'heating') {{
    const change = inflTrend.change_30d;
    inflStatus = `<span style="color:#FF8C00;">\u25B2 Heating (${{change > 0 ? '+' : ''}}${{change}}pp/mo)</span>`;
  }} else if (inflTrend.direction === 'cooling') {{
    const change = inflTrend.change_30d;
    inflStatus = `<span style="color:#4DA8DA;">\u25BC Cooling (${{change}}pp/mo)</span>`;
  }}
  document.getElementById('hero-infl-status').innerHTML = inflStatus;

  // Update season logic to use ACTUAL inflation direction (not z-score)
  // Re-determine season with corrected inflation direction
  const inflActuallyRising = inflTrend.direction === 'heating';
  const inflActuallyFalling = inflTrend.direction === 'cooling';
  let actualSeasonName, actualSeasonColor, actualSeasonSub;
  if (cycleUp && (inflActuallyFalling || inflTrend.direction === 'stable')) {{
    actualSeasonName = 'SPRING'; actualSeasonColor = '#A8D86E';
    actualSeasonSub = 'Cycle ↑ + Inflation ↓';
  }} else if (cycleUp && inflActuallyRising) {{
    actualSeasonName = 'SUMMER'; actualSeasonColor = '#FF8C00';
    actualSeasonSub = 'Cycle ↑ + Inflation ↑';
  }} else if (!cycleUp && inflActuallyRising) {{
    actualSeasonName = 'FALL'; actualSeasonColor = '#E84B5A';
    actualSeasonSub = 'Cycle ↓ + Inflation ↑';
  }} else {{
    actualSeasonName = 'WINTER'; actualSeasonColor = '#4DA8DA';
    actualSeasonSub = 'Cycle ↓ + Inflation ↓';
  }}
  seasonEl.textContent = actualSeasonName;
  seasonEl.style.color = actualSeasonColor;
  document.getElementById('season-sub').textContent = actualSeasonSub;
}}

// Draw a tiny inline sparkline using canvas
function drawSparkline(data, color) {{
  const canvas = document.getElementById('sparkline');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const width = canvas.offsetWidth;
  const height = canvas.offsetHeight;
  // Set the actual canvas resolution
  canvas.width = width * window.devicePixelRatio;
  canvas.height = height * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

  ctx.clearRect(0, 0, width, height);

  const valid = data.filter(v => v !== null && v !== undefined);
  if (valid.length < 2) return;
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = Math.max(0.5, max - min);

  // Zero line
  if (min < 0 && max > 0) {{
    const zeroY = height - ((0 - min) / range) * height;
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, zeroY);
    ctx.lineTo(width, zeroY);
    ctx.stroke();
  }}

  // Sparkline path
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  data.forEach((v, i) => {{
    if (v === null || v === undefined) return;
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * height;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }});
  ctx.stroke();

  // Last point dot
  const lastValidIdx = data.length - 1;
  if (data[lastValidIdx] !== null) {{
    const x = width;
    const y = height - ((data[lastValidIdx] - min) / range) * height;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x - 2, y, 3, 0, 2 * Math.PI);
    ctx.fill();
  }}
}}

function setRange(r) {{
  currentRange = r;
  document.querySelectorAll('.filters .filter-btn:not(#toggle-spx):not(#toggle-btc):not(#toggle-iwm)').forEach(b => b.classList.remove('active'));
  const btn = document.querySelector(`.filter-btn[onclick="setRange('${{r}}')"]`);
  if (btn) btn.classList.add('active');
  rebuildCharts();
}}

function toggleAsset(asset) {{
  if (asset === 'spx') {{
    showSpx = !showSpx;
    document.getElementById('toggle-spx').classList.toggle('active', showSpx);
  }} else if (asset === 'iwm') {{
    showIwm = !showIwm;
    document.getElementById('toggle-iwm').classList.toggle('active', showIwm);
  }} else {{
    showBtc = !showBtc;
    document.getElementById('toggle-btc').classList.toggle('active', showBtc);
  }}
  rebuildCharts();
}}

function rebuildCharts() {{
  Object.values(charts).forEach(c => c.destroy());
  charts = {{}};
  Object.values(expandedCharts).forEach(c => c.destroy());
  expandedCharts = {{}};
  createCharts();
}}

createCharts();

// ── Section navigation ──────────────────────────────────────────────────────

function scrollToSection(id) {{
  const el = document.getElementById(id);
  if (el) el.scrollIntoView({{ behavior: 'smooth' }});
}}

// Highlight active nav pill via IntersectionObserver
const _sectionIds = ['section-brief','section-hero','section-mrmi','section-seasons'];
const _navBtns = {{}};
document.querySelectorAll('.snav-btn[data-target]').forEach(b => {{
  _navBtns[b.dataset.target] = b;
}});

const _observer = new IntersectionObserver((entries) => {{
  entries.forEach(e => {{
    if (e.isIntersecting) {{
      Object.values(_navBtns).forEach(b => b.classList.remove('active'));
      const btn = _navBtns[e.target.id];
      if (btn) btn.classList.add('active');
    }}
  }});
}}, {{ rootMargin: '-52px 0px -70% 0px', threshold: 0 }});

_sectionIds.forEach(id => {{
  const el = document.getElementById(id);
  if (el) _observer.observe(el);
}});

// ── Mini floating regime badge ───────────────────────────────────────────────

const _badge = document.getElementById('mini-badge');
const _badgeLabel = document.getElementById('mini-badge-label');
const _badgeVal = document.getElementById('mini-badge-val');

// Populate badge once regime data is set (reuse existing regime-label element)
function _updateBadge() {{
  const label = document.getElementById('regime-label');
  const val = document.getElementById('composite-val');
  if (label && val) {{
    _badgeLabel.textContent = label.textContent;
    _badgeLabel.style.color = label.style.color;
    _badgeVal.textContent = val.textContent;
  }}
}}
setTimeout(_updateBadge, 300);

const _heroObserver = new IntersectionObserver((entries) => {{
  _updateBadge();
  _badge.classList.toggle('visible', !entries[0].isIntersecting);
}}, {{ threshold: 0.1 }});
const _heroEl = document.getElementById('regime-banner');
if (_heroEl) _heroObserver.observe(_heroEl);

// ── Brief card collapse ──────────────────────────────────────────────────────

function _initBriefCollapse() {{
  const card = document.querySelector('.brief-card');
  if (!card) return;

  // Wrap everything after .brief-head in a collapsible body div
  const head = card.querySelector('.brief-head');
  if (!head) return;
  const body = document.createElement('div');
  body.className = 'brief-body';
  while (head.nextSibling) body.appendChild(head.nextSibling);
  card.appendChild(body);

  // Add section anchor for nav
  card.id = 'section-brief';
  card.style.scrollMarginTop = '52px';

  // Add toggle button to head
  const btn = document.createElement('button');
  btn.className = 'brief-collapse-btn';
  btn.title = 'Toggle brief (B)';
  btn.innerHTML = '&#9660;';
  btn.onclick = toggleBrief;
  head.appendChild(btn);

  // Restore collapsed state
  if (localStorage.getItem('brief-collapsed') === '1') {{
    card.classList.add('collapsed');
  }}
}}

function toggleDrivers(id) {{
  const body = document.getElementById(id);
  const btn  = document.getElementById('toggle-' + id);
  const open = body.classList.toggle('open');
  btn.classList.toggle('open', open);
  localStorage.setItem('drivers-' + id, open ? '1' : '0');
}}

// Restore driver toggle states (collapsed by default)
['mrmi-drivers', 'compass-inputs', 'cycle-chart'].forEach(id => {{
  if (localStorage.getItem('drivers-' + id) === '1') {{
    document.getElementById(id).classList.add('open');
    document.getElementById('toggle-' + id).classList.add('open');
  }}
}});

function toggleBrief() {{
  const card = document.querySelector('.brief-card');
  if (!card) return;
  card.classList.toggle('collapsed');
  localStorage.setItem('brief-collapsed', card.classList.contains('collapsed') ? '1' : '0');
}}

_initBriefCollapse();

// ── Macro Seasons ────────────────────────────────────────────────────────────

// ── Info icon tooltips ───────────────────────────────────────────────────────

const CHART_DESCS = {{
  mrmi: 'The <strong>Milk Road Momentum Index (MRMI)</strong> is an alpha-weighted composite of three regime indicators: <strong>GII</strong> (growth & global momentum, 37%), <strong>Breadth</strong> (market breadth across 7 ETFs, 35%), and <strong>FinCon</strong> (financial conditions via VIX, MOVE, HY spreads, 28%). <strong>Green = risk-on</strong> (MRMI above zero), <strong>red = risk-off</strong> (below zero). Price overlays show how assets performed in each regime. OOS alpha vs buy-and-hold: SPX +14%, IWM +22.4%, BTC +23.4%.',
  mrci: 'The <strong>Growth composite</strong> drives the Y-axis of the Macro Seasons. It combines <strong>Real Economy</strong> (CFNAI activity index, industrial production, housing starts, building permits — all z-scored) and <strong>Labor</strong> (inverted jobless claims). <strong>Above zero = expanding</strong>, <strong>below zero = contracting</strong>. The time-series chart below shows how both growth and Core CPI have trended over time. This is a structural, slow-moving indicator — context for the macro backdrop, not a timing signal.',
  compass: 'The <strong>Macro Seasons</strong> chart maps where the economy sits across two dimensions. <strong>Y-axis (vertical)</strong> = Growth composite (Real Economy + Labor) — above zero is expanding, below is contracting. <strong>X-axis (horizontal)</strong> = Core CPI YoY minus the Fed 2% target — right of center is above target, left is below. The four quadrants are macro seasons: <strong>Spring</strong> (growth ↑, inflation below target), <strong>Summer</strong> (growth ↑, above target), <strong>Fall</strong> (growth ↓, above target), <strong>Winter</strong> (growth ↓, below target). Labeled dots mark where the economy was 1, 3, 6, and 12 months ago. <strong>This is context only</strong> — it describes the macro environment but is not a buy/sell signal.',
}};

(function() {{
  const tip = document.getElementById('info-tooltip');
  function getDesc(key) {{
    if (CHART_DESCS[key]) return CHART_DESCS[key];
    return (DATA.scorecard[key] && DATA.scorecard[key].desc) || '';
  }}
  document.addEventListener('mouseover', function(e) {{
    const icon = e.target.closest('.info-icon');
    if (icon) {{
      const desc = getDesc(icon.dataset.key);
      if (desc) {{ tip.innerHTML = desc; tip.style.display = 'block'; }}
    }} else {{
      tip.style.display = 'none';
    }}
  }});
  document.addEventListener('mouseout', function(e) {{
    if (e.target.closest('.info-icon')) tip.style.display = 'none';
  }});
  document.addEventListener('mousemove', function(e) {{
    if (tip.style.display !== 'block') return;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    const vw = window.innerWidth, vh = window.innerHeight;
    let left = e.clientX + 14, top = e.clientY - th / 2;
    if (left + tw > vw - 8) left = e.clientX - tw - 14;
    if (top < 8) top = 8;
    if (top + th > vh - 8) top = vh - th - 8;
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
  }});
}})();

// ── Keyboard shortcuts ───────────────────────────────────────────────────────

document.addEventListener('keydown', (e) => {{
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch(e.key) {{
    case '1': scrollToSection('section-hero'); break;
    case '2': scrollToSection('section-mrmi'); break;
    case '3': scrollToSection('section-seasons'); break;
    case 'b': case 'B': toggleBrief(); break;
    case 't': case 'T': window.scrollTo({{ top: 0, behavior: 'smooth' }}); break;
  }}
}});

</script>
</body>
</html>"""


# ============================================================================
# SECTION 5: MAIN
# ============================================================================

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


def save_snapshot(data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx=None, mrmi_combined=None) -> Path:
    """Save a compact JSON snapshot of today's key metrics for daily-brief diffing."""
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # Latest composite / drivers (from our z-scored signals)
    composite_v = _latest(composite)
    snapshot = {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "build_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
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
    }

    # Milk Road Macro Index (combined headline signal)
    if mrmi_combined:
        mrmi_v = _latest(mrmi_combined["mrmi"])
        snapshot["mrmi_combined"] = {
            "value": mrmi_v,
            "state": ("LONG" if (mrmi_v is not None and mrmi_v > 0)
                      else "CASH" if mrmi_v is not None else None),
            "momentum": _latest(mrmi_combined["momentum"]),
            "stress_intensity": _latest(mrmi_combined["stress_intensity"]),
            "macro_buffer": _latest(mrmi_combined["macro_buffer"]),
            "buffer_size": mrmi_combined.get("buffer_size", 2.0),
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


def main():
    use_cache = "--no-cache" not in sys.argv
    open_browser = "--open" in sys.argv

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Fetch data
    data = fetch_all_data(use_cache=use_cache)

    # Calculate indicators
    print("Calculating indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    composite = calc_composite(gii, fincon, breadth)
    biz_cycle = calc_business_cycle(data)
    infl_ctx = calc_inflation_context(data)
    macro_ctx = calc_macro_context(data, lookback_years=3)
    mrmi_combined = calc_milk_road_macro_index(composite, macro_ctx, buffer_size=1.0, threshold=0.5)

    print(f"  Composite:  {composite.dropna().shape[0]} valid rows, latest={composite.dropna().iloc[-1]:.2f}")
    print(f"  GII:        {gii.dropna().shape[0]} valid rows, latest fast={gii['fast'].dropna().iloc[-1]:.2f}")
    print(f"  FinCon:     {fincon['composite'].dropna().shape[0] if 'composite' in fincon else 0} valid rows")
    print(f"  Breadth:    {breadth['composite'].dropna().shape[0] if 'composite' in breadth else 0} valid rows")
    print(f"  Biz Cycle:  {biz_cycle['composite'].dropna().shape[0] if 'composite' in biz_cycle else 0} valid rows")
    print(f"  Inflation:  {infl_ctx['composite'].dropna().shape[0] if 'composite' in infl_ctx else 0} valid rows")
    mrmi_series = mrmi_combined['mrmi'].dropna()
    if len(mrmi_series):
        latest = mrmi_series.iloc[-1]
        state = "STAY LONG" if latest > 0 else "CASH"
        stress_now = mrmi_combined['stress_intensity'].dropna().iloc[-1] if len(mrmi_combined['stress_intensity'].dropna()) else 0
        print(f"  ▶ MRMI:     {latest:+.2f} → {state}  (Momentum {composite.dropna().iloc[-1]:+.2f}  Buffer {mrmi_combined['macro_buffer'].dropna().iloc[-1]:+.2f}  Stress {stress_now:.2f})")
    re_score = macro_ctx['real_economy_score'].dropna()
    inf_dir = macro_ctx['inflation_dir_pp'].dropna()
    if len(re_score):
        print(f"  Macro:      Real Economy Score {re_score.iloc[-1]:+.2f} (z, 3y lookback)")
        comps = macro_ctx['real_economy_components']
        if not comps.empty:
            latest = comps.dropna().iloc[-1] if len(comps.dropna()) else None
            if latest is not None:
                comp_str = "  ".join(f"{k}={v:+.2f}" for k, v in latest.items())
                print(f"              components: {comp_str}")
        if len(inf_dir):
            cpi_y = macro_ctx['core_cpi_yoy_pct'].dropna()
            print(f"              Inflation Dir Δ6m {inf_dir.iloc[-1]:+.2f}pp  (Core CPI YoY {cpi_y.iloc[-1]:.2f}%)")

    # Save daily snapshot for brief diffing
    save_snapshot(data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, mrmi_combined)

    # Auto-generate commentary using Claude + web search
    try:
        from generate_commentary import generate_commentary
        generate_commentary()
    except Exception as e:
        print(f"  Warning: failed to generate commentary: {e}")

    # Regenerate daily brief from snapshot history
    try:
        from generate_brief import generate_brief
        generate_brief()
    except Exception as e:
        print(f"  Warning: failed to generate brief: {e}")

    # Prepare chart data
    chart_json, seasons_current = prepare_chart_data(
        data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, mrmi_combined
    )

    # Read daily brief (if present) to inject at top of dashboard
    brief_html = ""
    if BRIEF_FILE.exists():
        try:
            brief_html = BRIEF_FILE.read_text()
        except Exception as e:
            print(f"  Warning: failed to read brief file: {e}")

    # Build HTML
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = build_html(chart_json, now, brief_html, seasons_current)

    with open(OUTPUT_FILE, "w") as f:
        f.write(html)
    print(f"\nDashboard saved to {OUTPUT_FILE}")

    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
