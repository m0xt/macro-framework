#!/usr/bin/env python3
"""
analyze_real_economy_conditioning.py

Tests the new Real Economy Composite + Inflation Direction conditioning vs the
old 4-quadrant Macro Seasons approach.

For each historical MRMI flip:
  1. Snapshot Real Economy Score (continuous z) and Inflation Direction (pp)
  2. Compute forward SPX/BTC returns
  3. Bucket by (Real Economy quartile × Inflation direction sign) and compare returns
  4. Also test Real Economy alone, and the simple sign-based grid
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


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()
    macro = calc_macro_context(data)

    re_score = macro["real_economy_score"]
    inf_dir  = macro["inflation_dir_pp"]

    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    green_flips = mrmi.index[delta == 1]
    red_flips   = mrmi.index[delta == -1]
    print(f"Found {len(green_flips)} green flips, {len(red_flips)} red flips")

    horizons = {"30d": 30, "90d": 90, "180d": 180}
    assets = {"SPX": "^GSPC", "BTC": "BTC-USD"}
    fwd = {}
    for asset_label, col in assets.items():
        if col not in data:
            continue
        for h_label, n in horizons.items():
            fwd[f"{asset_label}_{h_label}"] = (data[col].shift(-n) / data[col] - 1) * 100

    rows = []
    for flip_dir, flip_dates in [("green", green_flips), ("red", red_flips)]:
        for date in flip_dates:
            row = {
                "date": date, "flip": flip_dir,
                "re_score": re_score.get(date) if date in re_score.index else None,
                "inf_dir":  inf_dir.get(date) if date in inf_dir.index else None,
            }
            for k, series in fwd.items():
                row[k] = series.get(date) if date in series.index else None
            rows.append(row)

    df = pd.DataFrame(rows).dropna(subset=["re_score", "inf_dir"])
    print(f"Flips with both signals available: {len(df)}")

    # ── 1. Real Economy alone (continuous bucketing) ──
    print("\n" + "═" * 90)
    print("1. REAL ECONOMY SCORE alone — green flips only")
    print("─" * 90)
    g = df[df["flip"] == "green"]
    g = g.copy()
    # Bucket by Real Economy Score: rising/healthy vs falling/weak (sign + magnitude)
    buckets = [
        ("RE strong (≥+0.5)", lambda x: x >= 0.5),
        ("RE positive (0 to +0.5)", lambda x: (x >= 0) & (x < 0.5)),
        ("RE weak (−0.5 to 0)", lambda x: (x >= -0.5) & (x < 0)),
        ("RE deeply negative (<−0.5)", lambda x: x < -0.5),
    ]
    print(f"{'Bucket':<32} {'N':>3}  {'SPX 90d mean':>14}  {'hit':>6}")
    print("─" * 70)
    for bname, mask_fn in buckets:
        sub = g[mask_fn(g["re_score"])]
        if len(sub) == 0:
            continue
        vals = sub["SPX_90d"].dropna()
        m = vals.mean()
        hit = (vals > 0).mean() * 100
        print(f"{bname:<32} {len(sub):>3}  {m:+11.1f}%   {hit:>4.0f}%")

    # ── 2. Combined: Real Economy × Inflation Direction (sign-based grid) ──
    print("\n" + "═" * 90)
    print("2. SIGN-BASED GRID — Real Economy sign × Inflation Direction sign (green flips)")
    print("─" * 90)
    print("Equivalent to the old 4-quadrant logic but with the new growth measure.")
    print()
    print(f"{'RE / Inf':<28} {'N':>3}  {'SPX 30d':>10} {'SPX 90d':>10} {'SPX 180d':>10}  {'hit 90d':>8}")
    print("─" * 80)
    quadrants_g = [
        ("RE+ / Inf−  (Reflation-like)",  lambda x, y: (x >= 0) & (y < 0)),
        ("RE+ / Inf+  (Expansion-like)",  lambda x, y: (x >= 0) & (y >= 0)),
        ("RE− / Inf+  (Stagflation-like)",lambda x, y: (x < 0)  & (y >= 0)),
        ("RE− / Inf−  (Disinflation-like)",lambda x, y: (x < 0)  & (y < 0)),
    ]
    for qname, mask_fn in quadrants_g:
        sub = g[mask_fn(g["re_score"], g["inf_dir"])]
        n = len(sub)
        if n == 0:
            continue
        line = f"{qname:<28} {n:>3} "
        for col in ["SPX_30d", "SPX_90d", "SPX_180d"]:
            vals = sub[col].dropna()
            m = vals.mean() if len(vals) else None
            line += f" {m:+8.1f}%" if m is not None else f"   {'—':>7}"
        vals90 = sub["SPX_90d"].dropna()
        hit = (vals90 > 0).mean() * 100 if len(vals90) else 0
        line += f"   {hit:>5.0f}%"
        print(line)

    # ── 3. Same for red flips ──
    print("\n── RED flips ──")
    print(f"{'RE / Inf':<28} {'N':>3}  {'SPX 30d':>10} {'SPX 90d':>10} {'SPX 180d':>10}  {'hit 90d':>8}")
    print("─" * 80)
    r = df[df["flip"] == "red"]
    for qname, mask_fn in quadrants_g:
        sub = r[mask_fn(r["re_score"], r["inf_dir"])]
        n = len(sub)
        if n == 0:
            continue
        line = f"{qname:<28} {n:>3} "
        for col in ["SPX_30d", "SPX_90d", "SPX_180d"]:
            vals = sub[col].dropna()
            m = vals.mean() if len(vals) else None
            line += f" {m:+8.1f}%" if m is not None else f"   {'—':>7}"
        vals90 = sub["SPX_90d"].dropna()
        # red flip "wins" when SPX falls
        hit = (vals90 < 0).mean() * 100 if len(vals90) else 0
        line += f"   {hit:>5.0f}%"
        print(line)

    # ── 4. Save ──
    out = Path(__file__).parent / ".cache" / "real_economy_conditioning.csv"
    df.to_csv(out, index=False)
    print(f"\nFlip-level data saved to {out}")


if __name__ == "__main__":
    main()
