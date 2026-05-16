#!/usr/bin/env python3
"""Validate top optimization candidates on IS / OOS split."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from optimize_mrmi import (
    calc_breadth_custom,
    calc_combined_mrmi,
    calc_fincon_custom,
    calc_gii_custom,
)

from macro_framework.build import calc_macro_context, fetch_all_data


def stats_period(asset_returns, mrmi, start, end, threshold=0.0):
    idx = mrmi.index
    if start: idx = idx[idx >= start]
    if end:   idx = idx[idx <= end]
    if len(idx) < 60: return None
    ret = asset_returns.reindex(idx).fillna(0)
    pos = (mrmi > threshold).astype(float).shift(1).fillna(0).reindex(idx).fillna(0)
    eq_strat = (1 + ret * pos).cumprod()
    eq_bh = (1 + ret).cumprod()
    years = (idx[-1] - idx[0]).days / 365.25
    cagr_strat = eq_strat.iloc[-1] ** (1 / years) - 1
    cagr_bh = eq_bh.iloc[-1] ** (1 / years) - 1
    max_dd = (eq_strat / eq_strat.cummax() - 1).min()
    bh_dd = (eq_bh / eq_bh.cummax() - 1).min()
    return {"alpha": (cagr_strat - cagr_bh) * 100,
            "cagr": cagr_strat * 100, "bh_cagr": cagr_bh * 100,
            "max_dd": max_dd * 100, "bh_dd": bh_dd * 100,
            "dd_red": (max_dd - bh_dd) * 100,
            "cash_pct": (1 - pos).mean() * 100}


def main():
    data = fetch_all_data(use_cache=True)
    macro = calc_macro_context(data, lookback_years=3, apply_release_lags=True)

    candidates = [
        ("Current (thr=0)",      dict(fast_roc=21, breadth_lb=63, fincon_lb=252, weights=(0.37,0.35,0.28), buffer=2.0, threshold=0.0)),
        ("DD-Top1 (thr=0.5)",    dict(fast_roc=21, breadth_lb=90, fincon_lb=252, weights=(0.33,0.33,0.34), buffer=1.0, threshold=0.5)),
        ("DD-Top2 (thr=0.5)",    dict(fast_roc=21, breadth_lb=90, fincon_lb=504, weights=(0.37,0.35,0.28), buffer=1.0, threshold=0.5)),
        ("DD-PureMMI (no buf)",  dict(fast_roc=30, breadth_lb=30, fincon_lb=504, weights=(0.25,0.50,0.25), buffer=0.0, threshold=0.0)),
        ("DD-PureMMI alt",       dict(fast_roc=21, breadth_lb=90, fincon_lb=252, weights=(0.33,0.33,0.34), buffer=0.0, threshold=0.0)),
    ]

    asset_returns = {
        "SPX": data["^GSPC"].pct_change(),
        "IWM": data["IWM"].pct_change(),
        "BTC": data["BTC-USD"].pct_change(),
    }

    split = pd.Timestamp("2022-12-31")

    print("\n" + "=" * 130)
    print(f"{'Candidate':<22} {'Asset':<5} {'Period':<6} {'B&H CAGR':>9} {'Strat':>8} {'Alpha':>9} {'B&H DD':>8} {'Strat DD':>9} {'ΔDD':>7} {'Cash%':>6}")
    print("-" * 130)
    for name, params in candidates:
        gii = calc_gii_custom(data, fast_roc=params["fast_roc"])
        breadth = calc_breadth_custom(data, lookback=params["breadth_lb"])
        fincon = calc_fincon_custom(data, lookback=params["fincon_lb"])
        _, mrmi, _ = calc_combined_mrmi(gii["fast"], breadth, fincon, macro,
                                         weights=params["weights"], buffer_size=params["buffer"])
        mrmi = mrmi.dropna()

        for asset_name, ret in asset_returns.items():
            for period_label, start, end in [("FULL", None, None), ("IS", None, split), ("OOS", split, None)]:
                r = stats_period(ret, mrmi, start, end, threshold=params.get("threshold", 0.0))
                if r is None: continue
                mark = " ★" if r["alpha"] > 0.5 else "  "
                print(f"{name:<22} {asset_name:<5} {period_label:<6} {r['bh_cagr']:>8.1f}% {r['cagr']:>7.1f}% {r['alpha']:>+7.1f}pp{mark} {r['bh_dd']:>7.1f}% {r['max_dd']:>8.1f}% {r['dd_red']:>+5.1f}pp {r['cash_pct']:>4.1f}%")
        print("-" * 130)


if __name__ == "__main__":
    main()
