#!/usr/bin/env python3
"""
analyze_position_sizing.py

Compares three position-sizing strategies, all built on top of MRMI flips:

  Binary (current):  Long 100% on green, cash on red.
  Bucket-sized:      Position size scaled by historical bucket performance:
                       Reflation green   → 100%
                       Disinflation green → 80%
                       Expansion green    → 50%
                       Stagflation green  → 0% (skip)
  Conviction-gated:  Bucket-sized + drop the position to 0 if MRMI whipsaws
                       back to red within 10 days of the flip.

For each strategy, simulates a continuous trading record across the full
sample and reports cumulative return, max drawdown, Sharpe-ish ratio.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    fetch_all_data,
    calc_growth_impulse, calc_financial_conditions, calc_sector_breadth,
    calc_composite, calc_macro_context,
)


def quadrant(g, i):
    if pd.isna(g) or pd.isna(i):
        return None
    if g >= 0 and i < 0: return "Reflation"
    if g >= 0 and i >= 0: return "Expansion"
    if g < 0 and i < 0: return "Disinflation"
    return "Stagflation"


# Empirical position sizes from the lagged backtest (Reflation/Disinflation/Expansion/Stagflation)
SIZING_BY_BUCKET = {
    "Reflation": 1.0,
    "Disinflation": 0.8,
    "Expansion": 0.5,
    "Stagflation": 0.0,
    None: 0.5,  # default if regime can't be classified
}


def simulate(asset_returns, position_series):
    """Apply position weights to daily returns; return equity curve."""
    daily_pnl = asset_returns.fillna(0) * position_series.shift(1).fillna(0)
    equity = (1 + daily_pnl).cumprod()
    return equity


def stats(equity):
    if len(equity) == 0:
        return None
    cum = equity.iloc[-1] - 1
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (1 + cum) ** (1 / years) - 1 if years > 0 else 0
    rolling_max = equity.cummax()
    drawdown = (equity / rolling_max - 1)
    max_dd = drawdown.min()
    daily_ret = equity.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    return {"cum": cum, "cagr": cagr, "max_dd": max_dd, "sharpe": sharpe}


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

    spx = data["^GSPC"]
    spx_ret = spx.pct_change().reindex(mrmi.index)

    # Build per-day regime classification
    regime = pd.Series([quadrant(re_score.get(d), inf_dir.get(d)) for d in mrmi.index],
                       index=mrmi.index)

    # ── Strategy 1: Binary ──
    pos_binary = (mrmi > 0).astype(float)

    # ── Strategy 2: Bucket-sized ──
    pos_sized = pd.Series(0.0, index=mrmi.index)
    for d in mrmi.index:
        if mrmi.get(d) > 0:
            r = regime.get(d)
            pos_sized[d] = SIZING_BY_BUCKET.get(r, 0.5)

    # ── Strategy 3: Conviction-gated ──
    # Identify flip dates and check if MRMI held for 10 days
    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    pos_gated = pos_sized.copy()
    for d in mrmi.index[delta == 1]:  # green flips
        idx_pos = mrmi.index.get_loc(d)
        if idx_pos + 10 < len(mrmi):
            mrmi_10d = mrmi.iloc[idx_pos + 10]
            if pd.notna(mrmi_10d) and mrmi_10d < 0:
                # Whipsawed back — zero out the position from this flip until next state change
                next_flip_pos = idx_pos
                for j in range(idx_pos, len(mrmi)):
                    if sign.iloc[j] == 0:  # back to red
                        next_flip_pos = j
                        break
                else:
                    next_flip_pos = len(mrmi)
                pos_gated.iloc[idx_pos:next_flip_pos] = 0.0

    # Buy & hold benchmark
    pos_bh = pd.Series(1.0, index=mrmi.index)

    # Simulate
    eq_bh = simulate(spx_ret, pos_bh)
    eq_binary = simulate(spx_ret, pos_binary)
    eq_sized = simulate(spx_ret, pos_sized)
    eq_gated = simulate(spx_ret, pos_gated)

    print("\n" + "═" * 80)
    print("POSITION SIZING — SPX strategies, 2017–2026 (lagged macro context)")
    print("═" * 80)
    print(f"{'Strategy':<32} {'CAGR':>8} {'CumRet':>10} {'MaxDD':>10} {'Sharpe':>8}")
    print("─" * 80)
    for label, eq in [
        ("Buy & Hold SPX", eq_bh),
        ("Binary (current MRMI)", eq_binary),
        ("Bucket-sized by regime", eq_sized),
        ("Bucket-sized + conviction gate", eq_gated),
    ]:
        s = stats(eq)
        if s is None:
            continue
        print(f"{label:<32} {s['cagr']*100:>7.1f}% {s['cum']*100:>9.1f}% {s['max_dd']*100:>9.1f}% {s['sharpe']:>7.2f}")

    print()
    print("Bucket sizes used:")
    for k, v in SIZING_BY_BUCKET.items():
        if k is not None:
            print(f"  {k:<14} → {v*100:>4.0f}%")


if __name__ == "__main__":
    main()
