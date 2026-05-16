#!/usr/bin/env python3
"""
analyze_walkforward.py

Out-of-sample stability check. We picked 3y RE lookback and 6m inflation Δ
on the full sample (2017–2026). Test: do those parameters still win on a
held-out window?

Train period: flips on/before 2022-12-31
Test period:  flips after 2022-12-31

For each parameter combination, compute the conditioning gap (Reflation−Stagflation)
on TRAIN and TEST separately. Stable parameters should perform similarly in both.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from macro_framework.build import (
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_macro_context,
    calc_sector_breadth,
    fetch_all_data,
)


def run_one(data, mrmi, lookback_years, inflation_window_days, split_date):
    macro = calc_macro_context(data, lookback_years=lookback_years, apply_release_lags=True)
    re_score = macro["real_economy_score"]
    core_cpi_yoy = macro["core_cpi_yoy_pct"]
    inf_dir = core_cpi_yoy.diff(inflation_window_days)

    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    green_flips = mrmi.index[delta == 1]

    spx = data["^GSPC"]
    spx_90d = (spx.shift(-90) / spx - 1) * 100

    rows = []
    for date in green_flips:
        rows.append({
            "date": date,
            "re_score": re_score.get(date) if date in re_score.index else None,
            "inf_dir":  inf_dir.get(date) if date in inf_dir.index else None,
            "SPX_90d":  spx_90d.get(date) if date in spx_90d.index else None,
        })
    df = pd.DataFrame(rows).dropna(subset=["re_score", "inf_dir", "SPX_90d"])

    train = df[df["date"] <= split_date]
    test = df[df["date"] > split_date]

    def gap(sub):
        ref = sub[(sub["re_score"] >= 0) & (sub["inf_dir"] < 0)]["SPX_90d"].mean()
        stag = sub[(sub["re_score"] < 0) & (sub["inf_dir"] >= 0)]["SPX_90d"].mean()
        ref_n = len(sub[(sub["re_score"] >= 0) & (sub["inf_dir"] < 0)])
        stag_n = len(sub[(sub["re_score"] < 0) & (sub["inf_dir"] >= 0)])
        return ref, stag, (ref or 0) - (stag or 0), ref_n, stag_n

    return gap(train), gap(test), len(train), len(test)


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()

    split_date = pd.Timestamp("2022-12-31")
    print(f"Split date: {split_date.date()}\n")

    combos = [
        (3,  90,  "3y / 3m"),
        (3, 180,  "3y / 6m"),  # current default
        (3, 365,  "3y / 12m"),
        (5, 180,  "5y / 6m"),
        (10, 180, "10y / 6m"),
    ]

    print("═" * 100)
    print("WALK-FORWARD STABILITY · Reflation−Stagflation gap on TRAIN vs TEST")
    print("─" * 100)
    print(f"{'Combo':<14} │ {'TRAIN ref':>10} {'stag':>8} {'gap':>8} {'(n)':>8}  │ {'TEST ref':>10} {'stag':>8} {'gap':>8} {'(n)':>8}  │ {'Stable?':>10}")
    print("─" * 100)

    for lb, inf_w, label in combos:
        (tr_ref, tr_stag, tr_gap, tr_ref_n, tr_stag_n), \
        (ts_ref, ts_stag, ts_gap, ts_ref_n, ts_stag_n), \
        n_train, n_test = run_one(data, mrmi, lb, inf_w, split_date)

        def fmt(v):
            return f"{v:+5.1f}%" if v is not None and pd.notna(v) else "  —  "
        def fmt_gap(g):
            return f"{g:+5.1f}pp" if pd.notna(g) and g != 0 else "  — "

        # Stability: do TRAIN and TEST agree directionally?
        stable = "✓" if (tr_gap > 0 and ts_gap > 0) else "✗"
        consistency = abs(ts_gap - tr_gap) if pd.notna(tr_gap) and pd.notna(ts_gap) else 999
        marker = "✓ stable" if stable == "✓" and consistency < 6 else ("⚠ degraded" if stable == "✓" else "✗ broken")

        train_stats = f"{fmt(tr_ref):>10} {fmt(tr_stag):>8} {fmt_gap(tr_gap):>8} ({tr_ref_n}/{tr_stag_n}):>8"
        test_stats = f"{fmt(ts_ref):>10} {fmt(ts_stag):>8} {fmt_gap(ts_gap):>8} ({ts_ref_n}/{ts_stag_n}):>8"

        print(f"{label:<14} │ {fmt(tr_ref):>10} {fmt(tr_stag):>8} {fmt_gap(tr_gap):>8} ({tr_ref_n:>2}/{tr_stag_n:>2})  │ {fmt(ts_ref):>10} {fmt(ts_stag):>8} {fmt_gap(ts_gap):>8} ({ts_ref_n:>2}/{ts_stag_n:>2})  │ {marker:>10}")

    print()
    print("Reading: TRAIN = flips ≤ 2022-12-31, TEST = flips > 2022-12-31")
    print("ref/stag = Reflation / Stagflation bucket SPX 90d mean. Gap = ref − stag.")
    print("Numbers in parentheses = (Reflation N / Stagflation N).")


if __name__ == "__main__":
    main()
