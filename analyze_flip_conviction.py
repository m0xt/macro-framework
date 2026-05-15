#!/usr/bin/env python3
"""
analyze_flip_conviction.py

Tests whether MRMI's behavior AROUND the flip moment predicts forward returns.
Hypothesis: a "strong" flip (with momentum) should outperform a "weak" flip
(barely crossed zero, could whipsaw back). Tests three measures of conviction:

  - Slope at flip:  MRMI value 5 days after flip (positive = building)
  - 30d momentum:   MRMI value 30 days after flip
  - Magnitude:      |MRMI| 10 days after flip (how far it pulled away from 0)

Within each conditioning bucket (Reflation / Stagflation etc.), bucket flips
into HIGH vs LOW conviction and compare forward returns.
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


def compute_conviction(mrmi, flip_dates, flip_dir, days_after=10):
    """For each flip, compute MRMI value `days_after` days later as conviction."""
    convictions = {}
    for d in flip_dates:
        try:
            idx_pos = mrmi.index.get_loc(d)
            target_pos = idx_pos + days_after
            if target_pos >= len(mrmi):
                convictions[d] = None
                continue
            v = mrmi.iloc[target_pos]
            convictions[d] = float(v) if pd.notna(v) else None
        except KeyError:
            convictions[d] = None
    return convictions


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
    red_flips = mrmi.index[delta == -1]

    horizons = {"30d": 30, "90d": 90, "180d": 180}
    fwd = {}
    for col, label in [("^GSPC", "SPX"), ("BTC-USD", "BTC")]:
        if col not in data:
            continue
        for h_label, n in horizons.items():
            fwd[f"{label}_{h_label}"] = (data[col].shift(-n) / data[col] - 1) * 100

    # Conviction = MRMI value 10 days after the flip (signed in flip direction)
    rows = []
    for flip_dir, flip_dates in [("green", green_flips), ("red", red_flips)]:
        conviction_5d = compute_conviction(mrmi, flip_dates, flip_dir, days_after=5)
        conviction_10d = compute_conviction(mrmi, flip_dates, flip_dir, days_after=10)
        conviction_30d = compute_conviction(mrmi, flip_dates, flip_dir, days_after=30)
        for date in flip_dates:
            c5 = conviction_5d.get(date)
            c10 = conviction_10d.get(date)
            c30 = conviction_30d.get(date)
            # Signed conviction in flip direction (positive = signal held / strengthened)
            if c10 is None:
                continue
            signed_c5 = c5 if (flip_dir == "green") else -c5 if c5 is not None else None
            signed_c10 = c10 if (flip_dir == "green") else -c10
            signed_c30 = c30 if (flip_dir == "green") else -c30 if c30 is not None else None

            row = {
                "date": date, "flip": flip_dir,
                "re_score": re_score.get(date) if date in re_score.index else None,
                "inf_dir": inf_dir.get(date) if date in inf_dir.index else None,
                "conviction_5d": signed_c5,
                "conviction_10d": signed_c10,
                "conviction_30d": signed_c30,
            }
            for k, series in fwd.items():
                row[k] = series.get(date) if date in series.index else None
            rows.append(row)

    df = pd.DataFrame(rows).dropna(subset=["re_score", "inf_dir", "conviction_10d"])
    print(f"Flips with full data: {len(df)}\n")

    # ── 1. Conviction effect (alone, ignoring regime) ──
    print("═" * 90)
    print("1. CONVICTION EFFECT — MRMI value 10d after flip (signed in flip direction)")
    print("─" * 90)
    print("Hypothesis: when MRMI keeps moving in the flip direction over the next 10 days,")
    print("the signal is more reliable than when it whipsaws back.\n")

    g = df[df["flip"] == "green"]
    print("  GREEN flips:")
    print(f"  {'Bucket':<32} {'N':>3}  {'SPX 90d mean':>14}  {'hit':>5}")
    print("  " + "─" * 64)
    buckets = [
        ("Strong conviction (≥+0.5)", lambda x: x >= 0.5),
        ("Held (0 to +0.5)",          lambda x: (x >= 0) & (x < 0.5)),
        ("Whipsaw back (<0)",          lambda x: x < 0),
    ]
    for bname, mask_fn in buckets:
        sub = g[mask_fn(g["conviction_10d"])]
        if len(sub) == 0:
            continue
        vals = sub["SPX_90d"].dropna()
        m = vals.mean()
        hit = (vals > 0).mean() * 100
        print(f"  {bname:<32} {len(sub):>3}  {m:+11.1f}%   {hit:>3.0f}%")

    # ── 2. Conviction WITHIN each regime bucket ──
    print("\n" + "═" * 90)
    print("2. CONVICTION × REGIME — does conviction add value on top of regime?")
    print("─" * 90)
    quadrants = [
        ("Reflation",   lambda x, y: (x >= 0) & (y < 0)),
        ("Disinflation",lambda x, y: (x < 0)  & (y < 0)),
        ("Expansion",   lambda x, y: (x >= 0) & (y >= 0)),
        ("Stagflation", lambda x, y: (x < 0)  & (y >= 0)),
    ]
    for qname, mask_fn in quadrants:
        sub_q = g[mask_fn(g["re_score"], g["inf_dir"])]
        if len(sub_q) == 0:
            continue
        print(f"\n  {qname}:")
        print(f"  {'Conviction':<22} {'N':>3}  {'SPX 90d mean':>14}  {'hit':>5}")
        print("  " + "─" * 54)
        for bname, mask_fn2 in [
            ("Strong (≥+0.5)",  lambda x: x >= 0.5),
            ("Mild (0 to +0.5)", lambda x: (x >= 0) & (x < 0.5)),
            ("Whipsaw (<0)",      lambda x: x < 0),
        ]:
            sub = sub_q[mask_fn2(sub_q["conviction_10d"])]
            if len(sub) == 0:
                continue
            vals = sub["SPX_90d"].dropna()
            if len(vals) == 0:
                continue
            m = vals.mean()
            hit = (vals > 0).mean() * 100
            print(f"  {bname:<22} {len(sub):>3}  {m:+11.1f}%   {hit:>3.0f}%")


if __name__ == "__main__":
    main()
