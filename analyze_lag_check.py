#!/usr/bin/env python3
"""
analyze_lag_check.py

Compares conditioning effect with vs without release-lag adjustment.
The unlagged version uses contemporaneous data (which wouldn't have been
available in real-time). The lagged version uses only data actually released
by the flip date — this is the honest backtest.

If the conditioning effect survives the lag adjustment, the framework is real.
If it weakens significantly, we were partly fooling ourselves with look-ahead.
"""

import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    fetch_all_data,
    calc_growth_impulse, calc_financial_conditions, calc_sector_breadth,
    calc_composite, calc_macro_context,
)


def run_backtest(data, mrmi, macro):
    re_score = macro["real_economy_score"]
    inf_dir = macro["inflation_dir_pp"]

    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    green_flips = mrmi.index[delta == 1]
    red_flips = mrmi.index[delta == -1]

    horizons = {"30d": 30, "90d": 90, "180d": 180}
    fwd = {}
    for col, label in [("^GSPC", "SPX"), ("BTC-USD", "BTC")]:
        if col not in data:
            continue
        for h_label, n in horizons.items():
            fwd[f"{label}_{h_label}"] = (data[col].shift(-n) / data[col] - 1) * 100

    rows = []
    for flip_dir, flip_dates in [("green", green_flips), ("red", red_flips)]:
        for date in flip_dates:
            row = {
                "date": date, "flip": flip_dir,
                "re_score": re_score.get(date) if date in re_score.index else None,
                "inf_dir": inf_dir.get(date) if date in inf_dir.index else None,
            }
            for k, series in fwd.items():
                row[k] = series.get(date) if date in series.index else None
            rows.append(row)

    return pd.DataFrame(rows).dropna(subset=["re_score", "inf_dir"])


def summarize(df, label):
    g = df[df["flip"] == "green"]
    print(f"\n── {label} (n={len(df)}) ──")
    print(f"  {'RE / Inf':<32} {'N':>3}  {'SPX 90d':>9}  {'hit':>5}")
    print("  " + "─" * 56)
    quadrants = [
        ("RE+ / Inf−  (Reflation)",   lambda x, y: (x >= 0) & (y < 0)),
        ("RE+ / Inf+  (Expansion)",   lambda x, y: (x >= 0) & (y >= 0)),
        ("RE− / Inf+  (Stagflation)", lambda x, y: (x < 0)  & (y >= 0)),
        ("RE− / Inf−  (Disinflation)",lambda x, y: (x < 0)  & (y < 0)),
    ]
    bucket_results = {}
    for qname, mask_fn in quadrants:
        sub = g[mask_fn(g["re_score"], g["inf_dir"])]
        if len(sub) == 0:
            continue
        vals = sub["SPX_90d"].dropna()
        if len(vals) == 0:
            continue
        m = vals.mean()
        hit = (vals > 0).mean() * 100
        bucket_results[qname] = (len(sub), m, hit)
        print(f"  {qname:<32} {len(sub):>3}  {m:+7.1f}%   {hit:>3.0f}%")
    return bucket_results


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()

    # Compute both versions of macro context
    macro_unlagged = calc_macro_context(data, lookback_years=3, apply_release_lags=False)
    macro_lagged = calc_macro_context(data, lookback_years=3, apply_release_lags=True)

    df_unlagged = run_backtest(data, mrmi, macro_unlagged)
    df_lagged = run_backtest(data, mrmi, macro_lagged)

    print("\n" + "═" * 70)
    print("CONDITIONING EFFECT — LAGGED vs UNLAGGED COMPARISON")
    print("═" * 70)

    res_unlagged = summarize(df_unlagged, "UNLAGGED (look-ahead — original backtest)")
    res_lagged = summarize(df_lagged, "LAGGED (only data actually available at flip date)")

    # Side-by-side
    print("\n" + "═" * 90)
    print("SIDE-BY-SIDE — Reflation vs Stagflation key buckets")
    print("─" * 90)
    print(f"{'Bucket':<28}  {'Unlagged':>22}  {'Lagged':>22}  {'Δ effect':>12}")
    print("─" * 90)
    for q in ["RE+ / Inf−  (Reflation)", "RE− / Inf+  (Stagflation)",
              "RE− / Inf−  (Disinflation)", "RE+ / Inf+  (Expansion)"]:
        u = res_unlagged.get(q)
        l = res_lagged.get(q)
        if u is None or l is None:
            continue
        u_str = f"n={u[0]:>2}  {u[1]:+5.1f}%  hit {u[2]:>3.0f}%"
        l_str = f"n={l[0]:>2}  {l[1]:+5.1f}%  hit {l[2]:>3.0f}%"
        ret_diff = l[1] - u[1]
        print(f"{q:<28}  {u_str:>22}  {l_str:>22}  {ret_diff:+8.1f}pp")

    # Gap calculation
    print()
    if "RE+ / Inf−  (Reflation)" in res_unlagged and "RE− / Inf+  (Stagflation)" in res_unlagged:
        u_gap = res_unlagged["RE+ / Inf−  (Reflation)"][1] - res_unlagged["RE− / Inf+  (Stagflation)"][1]
        l_gap = res_lagged["RE+ / Inf−  (Reflation)"][1] - res_lagged["RE− / Inf+  (Stagflation)"][1]
        print(f"Reflation−Stagflation gap:  Unlagged {u_gap:+.1f}pp   Lagged {l_gap:+.1f}pp   (Δ {l_gap - u_gap:+.1f}pp)")


if __name__ == "__main__":
    main()
