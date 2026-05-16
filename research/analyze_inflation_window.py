#!/usr/bin/env python3
"""
analyze_inflation_window.py

Tests different inflation Δ windows (3m / 6m / 12m) holding the Real Economy
Composite fixed at its current 5y z-score lookback. For each (Inflation window),
runs the same conditioning backtest and shows:
  - 4-bucket conditioning grid (RE± × Inf±)
  - Gap between best (RE+/Inf−) and worst (RE−/Inf+) buckets
  - Sample sizes
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
    core_cpi_yoy = macro["core_cpi_yoy_pct"]

    YEAR = 365
    inflation_variants = {
        "3m":  core_cpi_yoy.diff(90),
        "6m":  core_cpi_yoy.diff(180),
        "12m": core_cpi_yoy.diff(365),
    }

    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    green_flips = mrmi.index[delta == 1]
    red_flips   = mrmi.index[delta == -1]

    horizons = {"30d": 30, "90d": 90, "180d": 180}
    fwd = {}
    for col, label in [("^GSPC", "SPX"), ("BTC-USD", "BTC")]:
        if col not in data:
            continue
        for h_label, n in horizons.items():
            fwd[f"{label}_{h_label}"] = (data[col].shift(-n) / data[col] - 1) * 100

    print()
    summary_rows = []

    for w_key, inf_dir in inflation_variants.items():
        # Build per-flip records
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
        g = df[df["flip"] == "green"]

        print("═" * 90)
        print(f"INFLATION Δ WINDOW: {w_key}    (n={len(df)} flips classified)")
        print("─" * 90)

        quadrants = [
            ("RE+ / Inf−  (Reflation-like)",   lambda x, y: (x >= 0) & (y < 0)),
            ("RE+ / Inf+  (Expansion-like)",   lambda x, y: (x >= 0) & (y >= 0)),
            ("RE− / Inf+  (Stagflation-like)", lambda x, y: (x < 0)  & (y >= 0)),
            ("RE− / Inf−  (Disinflation-like)",lambda x, y: (x < 0)  & (y < 0)),
        ]

        bucket_means = {}
        bucket_hits = {}
        bucket_ns = {}

        print("  GREEN flips:")
        print(f"  {'RE / Inf':<32} {'N':>3}  {'SPX 30d':>9} {'SPX 90d':>9} {'SPX 180d':>9}  {'hit 90d':>8}")
        print("  " + "─" * 80)
        for qname, mask_fn in quadrants:
            sub = g[mask_fn(g["re_score"], g["inf_dir"])]
            n = len(sub)
            if n == 0:
                continue
            line = f"  {qname:<32} {n:>3} "
            for col in ["SPX_30d", "SPX_90d", "SPX_180d"]:
                vals = sub[col].dropna()
                m = vals.mean() if len(vals) else None
                line += f"  {m:+6.1f}%" if m is not None else f"   {'—':>6}"
            vals90 = sub["SPX_90d"].dropna()
            hit = (vals90 > 0).mean() * 100 if len(vals90) else 0
            line += f"   {hit:>5.0f}%"
            print(line)
            bucket_means[qname] = vals90.mean() if len(vals90) else None
            bucket_hits[qname] = hit
            bucket_ns[qname] = n

        # Summary metrics for this window
        ref = bucket_means.get("RE+ / Inf−  (Reflation-like)") or 0
        stag = bucket_means.get("RE− / Inf+  (Stagflation-like)") or 0
        gap = ref - stag
        ref_hit = bucket_hits.get("RE+ / Inf−  (Reflation-like)", 0)
        stag_hit = bucket_hits.get("RE− / Inf+  (Stagflation-like)", 0)
        min_n = min((bucket_ns.get(q, 999) for q in [k for k, _ in quadrants]), default=0)

        summary_rows.append({
            "window": w_key,
            "ref_mean": ref, "stag_mean": stag, "gap": gap,
            "ref_hit": ref_hit, "stag_hit": stag_hit,
            "min_n": min_n,
        })

        print()

    # ── Cross-window summary ──
    print("═" * 90)
    print("CROSS-WINDOW SUMMARY · which inflation Δ window maximizes the conditioning effect?")
    print("─" * 90)
    print(f"{'Window':<8} {'Reflation 90d':>16} {'Stagflation 90d':>17} {'Gap':>10} {'Ref hit':>10} {'Stag hit':>10} {'min N':>6}")
    print("─" * 90)
    for r in summary_rows:
        print(
            f"{r['window']:<8} "
            f"{r['ref_mean']:+9.1f}% (n=...)  "
            f"{r['stag_mean']:+9.1f}%       "
            f"{r['gap']:+7.1f}pp  "
            f"{r['ref_hit']:>7.0f}%   "
            f"{r['stag_hit']:>7.0f}%   "
            f"{r['min_n']:>5}"
        )
    print()
    print("Higher 'Gap' = stronger conditioning effect.")
    print("Lower 'Stag hit' = more reliably-bad stagflation bucket.")
    print("Higher 'Ref hit' = more reliably-good reflation bucket.")


if __name__ == "__main__":
    main()
