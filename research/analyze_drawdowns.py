#!/usr/bin/env python3
"""
analyze_drawdowns.py

For each MRMI green flip, compute the max drawdown experienced in the 90 days
AFTER the flip. Bucket by macro regime. Average return alone hides path quality —
a "+6%" mean return with -15% mid-period drawdown is very different from "+6%"
with -2% drawdown.

Helps answer: which macro contexts produce CLEAN green-flip rallies vs PAINFUL ones?
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build import (
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


def fwd_drawdown(price_series, date, days):
    """Max % drawdown observed in [date, date+days] vs price at date."""
    try:
        idx = price_series.index.get_loc(date)
    except KeyError:
        return None
    end_idx = min(idx + days, len(price_series) - 1)
    window = price_series.iloc[idx:end_idx + 1]
    if len(window) < 2 or pd.isna(window.iloc[0]):
        return None
    base = window.iloc[0]
    rolling_min = window.cummin()
    dd = (rolling_min / base - 1) * 100
    return float(dd.min())


def fwd_return(price_series, date, days):
    try:
        idx = price_series.index.get_loc(date)
    except KeyError:
        return None
    target = idx + days
    if target >= len(price_series):
        return None
    p0 = price_series.iloc[idx]
    p1 = price_series.iloc[target]
    if pd.isna(p0) or pd.isna(p1):
        return None
    return float((p1 / p0 - 1) * 100)


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

    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    green_flips = mrmi.index[delta == 1]

    spx = data["^GSPC"]

    rows = []
    for date in green_flips:
        g = re_score.get(date) if date in re_score.index else None
        i = inf_dir.get(date) if date in inf_dir.index else None
        regime = quadrant(g, i)
        if regime is None:
            continue
        rows.append({
            "date": date, "regime": regime,
            "ret_90d": fwd_return(spx, date, 90),
            "dd_90d": fwd_drawdown(spx, date, 90),
        })

    df = pd.DataFrame(rows).dropna(subset=["ret_90d", "dd_90d"])

    print("\n" + "═" * 90)
    print("DRAWDOWN BY REGIME · GREEN flips, 90-day forward window")
    print("─" * 90)
    print("'Calmar' here = mean return / |max drawdown|. Higher = cleaner gains.")
    print()
    print(f"{'Regime':<14} {'N':>3}  {'Mean ret':>10}  {'Med ret':>10}  {'Mean DD':>10}  {'Worst DD':>10}  {'Calmar':>8}")
    print("─" * 90)
    for regime in ["Reflation", "Disinflation", "Expansion", "Stagflation"]:
        sub = df[df["regime"] == regime]
        if len(sub) == 0:
            continue
        mean_ret = sub["ret_90d"].mean()
        med_ret = sub["ret_90d"].median()
        mean_dd = sub["dd_90d"].mean()
        worst_dd = sub["dd_90d"].min()
        calmar = mean_ret / abs(mean_dd) if mean_dd != 0 else float("inf")
        print(f"{regime:<14} {len(sub):>3}  {mean_ret:+9.1f}%  {med_ret:+9.1f}%  {mean_dd:+9.1f}%  {worst_dd:+9.1f}%  {calmar:+7.2f}")

    print()
    print("Reading: low Mean DD (less negative) = smoother gains for that regime.")
    print("High Calmar (return / |DD|) = best risk-reward green flip context.")


if __name__ == "__main__":
    main()
