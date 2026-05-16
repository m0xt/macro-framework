#!/usr/bin/env python3
"""
analyze_multi_signal.py

No-leverage strategies that combine MRMI with multiple macro signals to find
robust alpha across SPX, IWM, BTC.

Hypothesis: MRMI gives drawdown protection but loses absolute return going
to cash 35% of the time. The fix: stay long by default, reduce position only
when MULTIPLE warning signs align. Each signal reduces position incrementally
rather than binary on/off.

Signals tested (each warning = position reduction):
  - MRMI red                             (current binary signal)
  - Macro regime is Stagflation          (regime conditioning)
  - Sahm Rule triggered (≥+0.5pp)        (forward-looking labor stress)
  - Yield curve inverted (10Y-2Y < 0)    (recession warning)
  - HY credit spreads in top 20%         (credit stress)

Strategies:
  A. Pure default-long (B&H)
  B. Pure MRMI binary
  C. Cash ONLY if MRMI red AND Stag (current winner — Strategy #5)
  D. Half-position if MRMI red AND Stag (less aggressive de-risk)
  E. Multi-signal scoring: position = (5 - #warnings) / 5 (graduated)
  F. Multi-signal binary: cash if 3+ warnings active
  G. Weighted multi-signal: MRMI 40%, Stag 30%, Sahm 20%, Curve 10%
  H. Default-long + cash on (MRMI red AND any 2 macro warnings)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from macro_framework.build import (
    _sahm_rule,
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_macro_context,
    calc_sector_breadth,
    fetch_all_data,
)


def quadrant(g, i):
    if pd.isna(g) or pd.isna(i):
        return None
    if g >= 0 and i < 0: return "Reflation"
    if g >= 0 and i >= 0: return "Expansion"
    if g < 0 and i < 0: return "Disinflation"
    return "Stagflation"


def stats(equity):
    if len(equity) == 0 or equity.iloc[0] == 0:
        return None
    cum = equity.iloc[-1] - 1
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (1 + cum) ** (1 / years) - 1 if years > 0 else 0
    rolling_max = equity.cummax()
    drawdown = equity / rolling_max - 1
    max_dd = drawdown.min()
    daily_ret = equity.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    return {"cagr": cagr, "cum": cum, "max_dd": max_dd, "sharpe": sharpe}


def run_asset(asset_name, asset_returns, signals, periods):
    """signals = dict of pre-computed boolean Series; all aligned to same index."""
    mrmi_red = signals["mrmi_red"]
    is_stag  = signals["is_stag"]
    sahm_on  = signals["sahm_on"]
    curve_inv = signals["curve_inv"]
    credit_stress = signals["credit_stress"]

    print("\n" + "█" * 100)
    print(f"█  {asset_name}")
    print("█" * 100)

    for period_label, start, end in periods:
        idx = asset_returns.index
        if start is not None: idx = idx[idx >= start]
        if end is not None:   idx = idx[idx <= end]
        if len(idx) < 60:
            continue

        ret = asset_returns.reindex(idx).fillna(0)

        # All signals on the period index, lagged by 1 day to avoid look-ahead
        s = {k: v.reindex(idx).shift(1).fillna(False) for k, v in signals.items()}

        # Number of active warnings
        warnings_count = (
            s["mrmi_red"].astype(int)
            + s["is_stag"].astype(int)
            + s["sahm_on"].astype(int)
            + s["curve_inv"].astype(int)
            + s["credit_stress"].astype(int)
        )

        strategies = {
            "A. B&H":                                           pd.Series(1.0, index=idx),
            "B. Pure MRMI binary":                              pd.Series(np.where(s["mrmi_red"], 0.0, 1.0), index=idx),
            "C. Cash if MRMI red AND Stag":                     pd.Series(np.where(s["mrmi_red"] & s["is_stag"], 0.0, 1.0), index=idx),
            "D. 50% if MRMI red AND Stag":                      pd.Series(np.where(s["mrmi_red"] & s["is_stag"], 0.5, 1.0), index=idx),
            "E. Graduated: pos = (5−warnings)/5":               (5 - warnings_count).clip(lower=0) / 5,
            "F. Cash if 3+ warnings":                            pd.Series(np.where(warnings_count >= 3, 0.0, 1.0), index=idx),
            "G. Weighted: MRMI40+Stag30+Sahm20+Curve10":        (1.0 - 0.40*s["mrmi_red"].astype(int) - 0.30*s["is_stag"].astype(int) - 0.20*s["sahm_on"].astype(int) - 0.10*s["curve_inv"].astype(int)).clip(lower=0, upper=1),
            "H. Cash if MRMI red AND ≥2 macro warnings":         pd.Series(np.where(s["mrmi_red"] & ((s["is_stag"].astype(int) + s["sahm_on"].astype(int) + s["curve_inv"].astype(int) + s["credit_stress"].astype(int)) >= 2), 0.0, 1.0), index=idx),
            "I. 50% if MRMI red, cash if MRMI red AND Stag":     pd.Series(np.where(s["mrmi_red"] & s["is_stag"], 0.0, np.where(s["mrmi_red"], 0.5, 1.0)), index=idx),
        }

        bh_eq = (1 + ret).cumprod()
        bh = stats(bh_eq)

        print(f"\n  {period_label} ({idx[0].date()} → {idx[-1].date()}, {(idx[-1]-idx[0]).days/365.25:.1f}y)  ·  B&H CAGR {bh['cagr']*100:.1f}%")
        print(f"  {'Strategy':<48}  {'CAGR':>7}  {'Alpha':>8}  {'MaxDD':>8}  {'Sharpe':>7}")
        print("  " + "─" * 90)

        rows = []
        for name, pos in strategies.items():
            eq = (1 + ret * pos).cumprod()
            st = stats(eq)
            if st is None:
                continue
            alpha = (st["cagr"] - bh["cagr"]) * 100
            rows.append({"name": name, "cagr": st["cagr"]*100, "alpha": alpha,
                          "max_dd": st["max_dd"]*100, "sharpe": st["sharpe"]})
        rows.sort(key=lambda r: r["alpha"], reverse=True)
        for r in rows:
            mark = " ★" if r["alpha"] > 0.5 else "  "
            print(f"  {r['name']:<48}  {r['cagr']:>6.1f}% {r['alpha']:>+7.1f}pp{mark}  {r['max_dd']:>7.1f}%  {r['sharpe']:>6.2f}")


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()

    macro = calc_macro_context(data, lookback_years=3, apply_release_lags=True)
    re_score = macro["real_economy_score"]
    inf_dir = macro["inflation_dir_pp"]

    # Daily regime classification
    regime_series = pd.Series(
        [quadrant(re_score.get(d), inf_dir.get(d)) for d in mrmi.index],
        index=mrmi.index,
    )

    # Sahm Rule (lagged for honesty)
    unrate_lagged = data["UNRATE"].shift(35) if "UNRATE" in data else None
    sahm = _sahm_rule(unrate_lagged) if unrate_lagged is not None else pd.Series(np.nan, index=mrmi.index)
    sahm_triggered = (sahm >= 0.5).reindex(mrmi.index, fill_value=False)

    # Yield curve (10Y - 2Y, no lag — daily market data)
    curve = (data["DGS10"] - data["DGS2"]).reindex(mrmi.index)
    curve_inverted = (curve < 0).fillna(False)

    # Credit stress: HY spread in top 20% of trailing 5y
    hy = data["BAMLH0A0HYM2"].reindex(mrmi.index)
    hy_5y_p80 = hy.rolling(365*5, min_periods=365).quantile(0.80)
    credit_stress = (hy >= hy_5y_p80).fillna(False)

    signals = {
        "mrmi_red":      (mrmi <= 0),
        "is_stag":       (regime_series == "Stagflation").fillna(False),
        "sahm_on":       sahm_triggered,
        "curve_inv":     curve_inverted,
        "credit_stress": credit_stress,
    }

    periods = [
        ("FULL",   None,                      None),
        ("IS",     None,                      pd.Timestamp("2022-12-31")),
        ("OOS",    pd.Timestamp("2023-01-01"), None),
    ]

    for asset_name, col in [("SPX", "^GSPC"), ("IWM", "IWM"), ("BTC", "BTC-USD")]:
        if col not in data:
            continue
        ret = data[col].pct_change().reindex(mrmi.index)
        run_asset(asset_name, ret, signals, periods)


if __name__ == "__main__":
    main()
