#!/usr/bin/env python3
"""
analyze_conviction_score.py

Tests a multi-factor MRMI Conviction Score:
  - Regime (Reflation / Expansion / Stagflation / Disinflation) — proven primary factor
  - Credit (HY spread direction)
  - Liquidity (M2 YoY growth)
  - Labor (initial jobless claims trend)
  - Yield curve (10Y − 2Y spread, level)

For each MRMI flip:
  1. Snapshot the 5 factor signals
  2. Compute conviction = signed sum (positive favors green-flip success / red-flip success)
  3. Bucket flips by conviction
  4. Compute forward SPX/BTC returns by bucket

Also runs isolated per-factor analysis to see which factors earn their place.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    fetch_all_data,
    calc_growth_impulse, calc_financial_conditions, calc_sector_breadth,
    calc_composite, calc_seasons_axes,
)


REGIME_NAMES = {
    "Spring": "Reflation",   # Growth ↑ Inflation ↓
    "Summer": "Expansion",   # Growth ↑ Inflation ↑
    "Fall":   "Stagflation", # Growth ↓ Inflation ↑
    "Winter": "Disinflation",# Growth ↓ Inflation ↓
}


def quadrant(g, i):
    if pd.isna(g) or pd.isna(i):
        return None
    if g >= 0 and i < 0:  return "Reflation"
    if g >= 0 and i >= 0: return "Expansion"
    if g < 0  and i < 0:  return "Disinflation"
    return "Stagflation"


def regime_signal(regime, flip_dir):
    """Score the regime as a confirming factor for the MRMI flip direction."""
    if regime is None:
        return 0
    if flip_dir == "green":
        # Backtest showed: Reflation/Disinflation/Expansion all positive, Stagflation negative
        return {"Reflation": 1, "Disinflation": 1, "Expansion": 0, "Stagflation": -1}[regime]
    else:  # red flip
        # Mirror: Stagflation confirms red, others fade red
        return {"Reflation": -1, "Disinflation": -1, "Expansion": 0, "Stagflation": 1}[regime]


def sign_signal(value, flip_dir, *, lower_is_bullish=False):
    """+1 if value's sign confirms the flip direction. Lower-is-bullish flips."""
    if pd.isna(value):
        return 0
    s = np.sign(value)
    if lower_is_bullish:
        s = -s
    if flip_dir == "green":
        return int(s)
    return int(-s)


def compute_factor_signals(data, dates, growth_change, inflation_change, flip_dir):
    """Snapshot the 5 factor signals at each flip date for the given direction."""
    YEAR = 365

    # Pre-compute factor series
    hy_chg_30d = data["BAMLH0A0HYM2"].diff(30) if "BAMLH0A0HYM2" in data else None
    m2_yoy = data["M2SL"].pct_change(YEAR) * 100 if "M2SL" in data else None
    claims_ma4 = data["ICSA"].rolling(28).mean() if "ICSA" in data else None
    claims_chg_30d = claims_ma4.diff(30) if claims_ma4 is not None else None
    curve = (data["DGS10"] - data["DGS2"]) if ("DGS10" in data and "DGS2" in data) else None

    rows = []
    for date in dates:
        g = growth_change.get(date) if date in growth_change.index else None
        i = inflation_change.get(date) if date in inflation_change.index else None
        regime = quadrant(g, i)

        # Regime signal (the proven factor)
        s_regime = regime_signal(regime, flip_dir)

        # Credit: HY spread tightening (negative 30-day change) is bullish for risk
        hy_chg = hy_chg_30d.get(date) if hy_chg_30d is not None and date in hy_chg_30d.index else None
        s_credit = sign_signal(hy_chg, flip_dir, lower_is_bullish=True)

        # Liquidity: M2 YoY > 2% is bullish (using deviation from 2%)
        m2_v = m2_yoy.get(date) if m2_yoy is not None and date in m2_yoy.index else None
        s_liquidity = sign_signal(m2_v - 2.0 if m2_v is not None else None, flip_dir, lower_is_bullish=False)

        # Labor: claims falling (negative 30-day change in 4-wk MA) is bullish
        claims_chg = claims_chg_30d.get(date) if claims_chg_30d is not None and date in claims_chg_30d.index else None
        s_labor = sign_signal(claims_chg, flip_dir, lower_is_bullish=True)

        # Curve: positive (steep) spread is bullish for growth, inverted is bearish
        curve_v = curve.get(date) if curve is not None and date in curve.index else None
        s_curve = sign_signal(curve_v, flip_dir, lower_is_bullish=False)

        conviction = s_regime + s_credit + s_liquidity + s_labor + s_curve

        rows.append({
            "date": date, "flip": flip_dir, "regime": regime,
            "s_regime": s_regime, "s_credit": s_credit, "s_liquidity": s_liquidity,
            "s_labor": s_labor, "s_curve": s_curve, "conviction": conviction,
        })

    return pd.DataFrame(rows)


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()

    seasons = calc_seasons_axes(data)
    growth_change = seasons["by_window"]["6m"]["growth_change_pp"]
    inflation_change = seasons["by_window"]["6m"]["inflation_change_pp"]

    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    green_flips = mrmi.index[delta == 1]
    red_flips = mrmi.index[delta == -1]
    print(f"Found {len(green_flips)} green flips, {len(red_flips)} red flips\n")

    # Forward returns
    horizons = {"30d": 30, "90d": 90, "180d": 180}
    assets = {"SPX": "^GSPC", "BTC": "BTC-USD"}
    fwd = {}
    for asset_label, col in assets.items():
        if col not in data:
            continue
        for h_label, n in horizons.items():
            fwd[f"{asset_label}_{h_label}"] = (data[col].shift(-n) / data[col] - 1) * 100

    # Build flip-level dataset
    df_g = compute_factor_signals(data, green_flips, growth_change, inflation_change, "green")
    df_r = compute_factor_signals(data, red_flips, growth_change, inflation_change, "red")

    for label, df_x in [("green", df_g), ("red", df_r)]:
        for k, series in fwd.items():
            df_x[k] = [series.get(d) if d in series.index else None for d in df_x["date"]]

    df_g = df_g.dropna(subset=["regime", "SPX_90d"])
    df_r = df_r.dropna(subset=["regime", "SPX_90d"])

    # ── 1. ISOLATED FACTOR ANALYSIS ──
    print("═" * 90)
    print("ISOLATED FACTOR ANALYSIS · does each factor add value on its own?")
    print("─" * 90)
    print("Bucketed by sign of the factor's signal (for green flips)")
    print()
    factors = ["s_regime", "s_credit", "s_liquidity", "s_labor", "s_curve"]
    factor_labels = {
        "s_regime": "Regime",
        "s_credit": "Credit (HY spread Δ30d)",
        "s_liquidity": "Liquidity (M2 YoY)",
        "s_labor": "Labor (claims Δ30d)",
        "s_curve": "Curve (10Y−2Y level)",
    }

    print(f"{'Factor':<32}  {'Bucket':<10} {'N':>3}  {'SPX 90d mean':>14}  {'hit rate':>10}")
    print("─" * 90)
    for f in factors:
        for bucket_name, mask_fn in [
            ("confirms (+)", lambda x: x > 0),
            ("neutral (0)",  lambda x: x == 0),
            ("contradicts (−)", lambda x: x < 0),
        ]:
            sub = df_g[mask_fn(df_g[f])]
            n = len(sub)
            if n == 0:
                continue
            vals = sub["SPX_90d"].dropna()
            mean_ret = vals.mean()
            hit = (vals > 0).mean() * 100
            print(f"{factor_labels[f]:<32}  {bucket_name:<10} {n:>3}  {mean_ret:+11.1f}%   {hit:>7.0f}%")
        print()

    # ── 2. COMBINED CONVICTION SCORE ──
    print("═" * 90)
    print("COMBINED CONVICTION SCORE · sum of all 5 factor signals (range −5 to +5)")
    print("─" * 90)

    for label, df_x in [("GREEN", df_g), ("RED", df_r)]:
        action = "RISK-ON" if label == "GREEN" else "RISK-OFF"
        print(f"\n── {label} flips (→ {action}) ──")
        print(f"{'Conviction bucket':<22} {'N':>3}  {'SPX 30d':>10} {'SPX 90d':>10} {'SPX 180d':>10} {'BTC 90d':>10} {'BTC 180d':>10}  {'hit 90d':>8}")
        print("─" * 100)
        # Bucket by conviction score
        buckets = [
            ("Very High (≥+3)", lambda x: x >= 3),
            ("High (+1 to +2)", lambda x: (x >= 1) & (x <= 2)),
            ("Mixed (−1 to 0)", lambda x: (x >= -1) & (x <= 0)),
            ("Low (−2 to −3)", lambda x: (x >= -3) & (x <= -2)),
            ("Very Low (≤−4)", lambda x: x <= -4),
        ]
        for bname, mask_fn in buckets:
            sub = df_x[mask_fn(df_x["conviction"])]
            n = len(sub)
            if n == 0:
                continue
            line = f"{bname:<22} {n:>3} "
            for col in ["SPX_30d", "SPX_90d", "SPX_180d", "BTC_90d", "BTC_180d"]:
                vals = sub[col].dropna()
                m = vals.mean() if len(vals) else None
                line += f" {m:+8.1f}%" if m is not None else f"   {'—':>7}"
            vals90 = sub["SPX_90d"].dropna()
            if label == "GREEN":
                hit = (vals90 > 0).mean() * 100 if len(vals90) else 0
            else:
                hit = (vals90 < 0).mean() * 100 if len(vals90) else 0
            line += f"   {hit:>5.0f}%"
            print(line)

    # ── 3. CONVICTION VS REGIME-ONLY ──
    print("\n" + "═" * 90)
    print("ADD-ON VALUE · does the conviction score beat regime-only conditioning?")
    print("─" * 90)
    print("Compare: GREEN flips with same regime, but high vs low full-conviction score")
    print()
    print(f"{'Regime':<14}  {'Conviction':<10}  {'N':>3}  {'SPX 90d mean':>14}  {'hit rate':>10}")
    print("─" * 70)
    for regime in ["Reflation", "Expansion", "Disinflation", "Stagflation"]:
        sub_r = df_g[df_g["regime"] == regime]
        if len(sub_r) == 0:
            continue
        # Excluding the regime contribution to see marginal value of other factors
        sub_r = sub_r.copy()
        sub_r["conv_ex_regime"] = sub_r["conviction"] - sub_r["s_regime"]
        for label, mask_fn in [
            ("high (≥+1)", lambda x: x >= 1),
            ("low (≤−1)", lambda x: x <= -1),
        ]:
            sub = sub_r[mask_fn(sub_r["conv_ex_regime"])]
            n = len(sub)
            if n == 0:
                print(f"{regime:<14}  {label:<10}  {n:>3}  {'—':>14}   {'—':>10}")
                continue
            vals = sub["SPX_90d"].dropna()
            m = vals.mean()
            hit = (vals > 0).mean() * 100
            print(f"{regime:<14}  {label:<10}  {n:>3}  {m:+11.1f}%   {hit:>7.0f}%")

    # Save
    out_g = Path(__file__).parent / ".cache" / "conviction_green_flips.csv"
    out_r = Path(__file__).parent / ".cache" / "conviction_red_flips.csv"
    df_g.to_csv(out_g, index=False)
    df_r.to_csv(out_r, index=False)
    print(f"\nGreen flip-level data: {out_g}")
    print(f"Red flip-level data:   {out_r}")


if __name__ == "__main__":
    main()
