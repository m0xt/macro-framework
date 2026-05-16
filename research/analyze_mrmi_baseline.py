#!/usr/bin/env python3
"""
analyze_mrmi_baseline.py

Pure MRMI backtest. No conditioning, no macro context, no conviction filter.
Just: long the asset when MRMI > 0, in cash when MRMI < 0.
Compare to buy & hold across SPX, IWM, BTC.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_sector_breadth,
    fetch_all_data,
)


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
    return {"cum": cum, "cagr": cagr, "max_dd": max_dd, "sharpe": sharpe, "years": years}


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)

    print("Computing MRMI...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mrmi = calc_composite(gii, fincon, breadth).dropna()

    # MRMI metadata
    sign = (mrmi > 0).astype(int)
    delta = sign.diff().fillna(0)
    flips = mrmi.index[delta != 0]
    pct_green = (mrmi > 0).mean() * 100
    flips_per_year = len(flips) / ((mrmi.index[-1] - mrmi.index[0]).days / 365.25)

    print(f"\nMRMI period: {mrmi.index[0].date()} → {mrmi.index[-1].date()}  ({(mrmi.index[-1]-mrmi.index[0]).days/365.25:.1f} years)")
    print(f"Time in green: {pct_green:.0f}%  ·  Flips/yr: {flips_per_year:.1f}  ·  Total flips: {len(flips)}")

    periods = [
        ("FULL PERIOD",   None,                  None),
        ("IN-SAMPLE",     None,                  pd.Timestamp("2022-12-31")),
        ("OUT-OF-SAMPLE", pd.Timestamp("2023-01-01"), None),
    ]

    for period_label, start, end in periods:
        sub_index = mrmi.index
        if start is not None:
            sub_index = sub_index[sub_index >= start]
        if end is not None:
            sub_index = sub_index[sub_index <= end]
        if len(sub_index) < 30:
            continue
        period_mrmi = mrmi.reindex(sub_index)

        print("\n" + "═" * 88)
        years_in_period = (sub_index[-1] - sub_index[0]).days / 365.25
        print(f"{period_label} · {sub_index[0].date()} → {sub_index[-1].date()} ({years_in_period:.1f} years)")
        print("─" * 88)
        print(f"{'Asset':<8} {'Strategy':<22}  {'CAGR':>8}  {'CumRet':>10}  {'MaxDD':>9}  {'Sharpe':>7}  {'Alpha':>8}  {'ΔDD':>8}")
        print("─" * 88)

        for asset_label, col in [("SPX", "^GSPC"), ("IWM", "IWM"), ("BTC", "BTC-USD")]:
            if col not in data:
                continue
            ret = data[col].pct_change().reindex(sub_index)
            pos = (period_mrmi > 0).astype(float).shift(1).fillna(0)

            eq_bh = (1 + ret.fillna(0)).cumprod()
            eq_mrmi = (1 + ret.fillna(0) * pos).cumprod()

            s_bh = stats(eq_bh)
            s_mrmi = stats(eq_mrmi)
            if s_bh is None or s_mrmi is None:
                continue

            alpha = (s_mrmi["cagr"] - s_bh["cagr"]) * 100
            dd_imp = (s_mrmi["max_dd"] - s_bh["max_dd"]) * 100

            print(f"{asset_label:<8} {'Buy & Hold':<22}  {s_bh['cagr']*100:>7.1f}%  {s_bh['cum']*100:>9.1f}%  {s_bh['max_dd']*100:>8.1f}%  {s_bh['sharpe']:>7.2f}  {'—':>8}  {'—':>8}")
            print(f"{asset_label:<8} {'MRMI (long-when-grn)':<22}  {s_mrmi['cagr']*100:>7.1f}%  {s_mrmi['cum']*100:>9.1f}%  {s_mrmi['max_dd']*100:>8.1f}%  {s_mrmi['sharpe']:>7.2f}  {alpha:>+7.1f}pp  {dd_imp:>+7.1f}pp")
            print()

    print()
    print("Notes:")
    print("- 'long-when-green' uses prior day's MRMI sign (no look-ahead).")
    print("- IN-SAMPLE = optimization era. OUT-OF-SAMPLE = unseen test years.")
    print("- The presentation reported OOS numbers (2023+).")


if __name__ == "__main__":
    main()
