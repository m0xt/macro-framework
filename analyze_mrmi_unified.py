#!/usr/bin/env python3
"""Validate that the unified MRMI (with threshold 0) reproduces Strategy C performance."""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    fetch_all_data,
    calc_growth_impulse, calc_financial_conditions, calc_sector_breadth,
    calc_composite, calc_macro_context, calc_milk_road_macro_index,
)


def stats(equity):
    if len(equity) == 0:
        return None
    cum = equity.iloc[-1] - 1
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (1 + cum) ** (1 / years) - 1 if years > 0 else 0
    rolling_max = equity.cummax()
    max_dd = (equity / rolling_max - 1).min()
    daily_ret = equity.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    return {"cagr": cagr * 100, "max_dd": max_dd * 100, "sharpe": sharpe}


def main():
    data = fetch_all_data(use_cache=True)
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    momentum = calc_composite(gii, fincon, breadth).dropna()
    macro = calc_macro_context(data, lookback_years=3, apply_release_lags=True)

    for buffer_size in [1.0, 1.5, 2.0]:
        print(f"\n{'═' * 90}")
        print(f"BUFFER SIZE = {buffer_size}")
        print('═' * 90)
        mrmi_combined = calc_milk_road_macro_index(momentum, macro, buffer_size=buffer_size)
        run_buffer(data, momentum, mrmi_combined, buffer_size)


def run_buffer(data, momentum, mrmi_combined, buffer_size):
    mrmi = mrmi_combined["mrmi"].dropna()

    # Position: long when MRMI > 0
    pos = (mrmi > 0).astype(float).shift(1).fillna(0)

    periods = [
        ("FULL", None, None),
        ("IS",   None, pd.Timestamp("2022-12-31")),
        ("OOS",  pd.Timestamp("2023-01-01"), None),
    ]

    print(f"\nUnified MRMI (buffer={buffer_size}) · long when MRMI > 0, cash when MRMI < 0")
    print("─" * 90)
    print(f"{'Asset/Period':<22} {'B&H CAGR':>10} {'MRMI CAGR':>11} {'Alpha':>9} {'B&H DD':>9} {'MRMI DD':>10} {'Sharpe':>8}")
    print("-" * 90)

    for asset_name, col in [("SPX", "^GSPC"), ("IWM", "IWM"), ("BTC", "BTC-USD")]:
        if col not in data:
            continue
        ret = data[col].pct_change().reindex(mrmi.index).fillna(0)
        for period_label, start, end in periods:
            idx = mrmi.index
            if start is not None: idx = idx[idx >= start]
            if end is not None:   idx = idx[idx <= end]
            ret_p = ret.reindex(idx).fillna(0)
            pos_p = pos.reindex(idx).fillna(0)

            eq_bh = (1 + ret_p).cumprod()
            eq_mrmi = (1 + ret_p * pos_p).cumprod()
            s_bh = stats(eq_bh)
            s_mrmi = stats(eq_mrmi)
            if s_bh is None or s_mrmi is None:
                continue
            alpha = s_mrmi["cagr"] - s_bh["cagr"]
            mark = " ★" if alpha > 0.5 else "  "
            print(f"{asset_name+' '+period_label:<22} {s_bh['cagr']:>9.1f}% {s_mrmi['cagr']:>10.1f}% {alpha:>+7.1f}pp{mark} {s_bh['max_dd']:>8.1f}% {s_mrmi['max_dd']:>9.1f}% {s_mrmi['sharpe']:>7.2f}")
        print()


if __name__ == "__main__":
    main()
