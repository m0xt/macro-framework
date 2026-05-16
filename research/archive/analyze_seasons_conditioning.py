#!/usr/bin/env python3
"""
analyze_seasons_conditioning.py

Tests the conditioning hypothesis: does the macro season at the moment of an
MRMI flip predict different forward outcomes?

For each historical MRMI flip (green→red or red→green), classify the season at
that moment (using the direction-of-change axes at the 6m window) and measure
1m / 3m / 6m forward returns on SPX, IWM, BTC.
Aggregate by (flip direction × season) and display.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from macro_framework.build import (
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_seasons_axes,
    calc_sector_breadth,
    fetch_all_data,
)


def quadrant(g, i):
    if pd.isna(g) or pd.isna(i):
        return None
    if g >= 0 and i < 0:  return "Spring"
    if g >= 0 and i >= 0: return "Summer"
    if g < 0  and i < 0:  return "Winter"
    return "Fall"


def analyze_window(data, mrmi, seasons, window_key, green_flips, red_flips, fwd):
    """Run the conditioning analysis at one Δ window. Returns aggregated DataFrame."""
    growth_change = seasons["by_window"][window_key]["growth_change_pp"]
    inflation_change = seasons["by_window"][window_key]["inflation_change_pp"]

    rows = []
    for flip_dir, flip_dates in [("green", green_flips), ("red", red_flips)]:
        for date in flip_dates:
            g = growth_change.get(date) if date in growth_change.index else None
            i = inflation_change.get(date) if date in inflation_change.index else None
            season = quadrant(g, i)
            row = {"date": date, "flip": flip_dir, "season": season, "window": window_key}
            for k, series in fwd.items():
                row[k] = series.get(date) if date in series.index else None
            rows.append(row)

    return pd.DataFrame(rows).dropna(subset=["season"])


def print_window_table(df, window_key, metric_cols):
    print(f"\n┏{'━' * 110}┓")
    print(f"┃  Δ WINDOW: {window_key:<8}  ({len(df)} flips classified)" + " " * (110 - 30 - len(str(len(df)))) + " ┃")
    print(f"┗{'━' * 110}┛")

    for flip_dir in ["green", "red"]:
        sub = df[df["flip"] == flip_dir]
        agg = sub.groupby("season")[metric_cols].agg(["count", "mean"])
        action_word = "RISK-ON" if flip_dir == "green" else "RISK-OFF"
        print(f"\n  {flip_dir.upper()} flips (→ {action_word}):")
        header = f"  {'Season':<10} {'N':>3}"
        for col in metric_cols:
            header += f" │ {col:>11}  hit"
        print(header)
        print("  " + "─" * (len(header) - 2))
        for season in ["Spring", "Summer", "Fall", "Winter"]:
            sub_s = sub[sub["season"] == season]
            if len(sub_s) == 0:
                continue
            n = len(sub_s)
            line = f"  {season:<10} {n:>3}"
            for col in metric_cols:
                vals = sub_s[col].dropna()
                if len(vals) == 0:
                    line += f" │ {'  —':>11}     "
                    continue
                m = vals.mean()
                if flip_dir == "green":
                    hit = (vals > 0).mean() * 100
                else:
                    hit = (vals < 0).mean() * 100
                line += f" │ {m:+6.1f}%      {hit:>3.0f}%"
            print(line)


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()

    seasons = calc_seasons_axes(data)

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

    metric_cols = ["SPX_30d", "SPX_90d", "SPX_180d", "BTC_90d", "BTC_180d"]

    all_dfs = {}
    for window in ["3m", "6m", "12m"]:
        df_w = analyze_window(data, mrmi, seasons, window, green_flips, red_flips, fwd)
        all_dfs[window] = df_w
        print_window_table(df_w, window, metric_cols)

    # Cross-window comparison: focus on the headline result —
    # SPX 90d return after a green flip, by season, across all 3 windows
    print("\n\n" + "═" * 80)
    print("CROSS-WINDOW COMPARISON · GREEN flip → SPX 90d (mean / hit rate)")
    print("═" * 80)
    print(f"{'Season':<10} │ {'3m window':>22} │ {'6m window':>22} │ {'12m window':>22}")
    print("─" * 80)
    for season in ["Spring", "Summer", "Fall", "Winter"]:
        line = f"{season:<10}"
        for window in ["3m", "6m", "12m"]:
            sub = all_dfs[window][(all_dfs[window]["flip"] == "green") &
                                   (all_dfs[window]["season"] == season)]
            if len(sub) == 0:
                line += f" │ {'  —':>22}"
                continue
            vals = sub["SPX_90d"].dropna()
            m = vals.mean()
            hit = (vals > 0).mean() * 100
            line += f" │ {m:+5.1f}%  hit {hit:>3.0f}%  n={len(sub):<3}"
        print(line)

    # Save 6m as default
    out_path = Path(__file__).parent / ".cache" / "seasons_conditioning.csv"
    all_dfs["6m"].to_csv(out_path, index=False)
    print(f"\n6m flip-level data saved to {out_path}")


if __name__ == "__main__":
    main()
