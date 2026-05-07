#!/usr/bin/env python3
"""
analyze_alpha_strategies.py

Hunt for strategies that actually beat buy-and-hold.

The pure MRMI binary loses ~5-8pp of CAGR vs B&H. Going to cash 35% of the
time in a bull market is mathematically hard to beat with binary timing.

This script tests multiple alternative configurations that try to capture
upside while only de-risking in genuinely dangerous regimes:

  1. Buy & Hold                                    (baseline)
  2. Pure MRMI binary                              (current standalone)
  3. MRMI + skip stagflation green flips           (filter false-positives)
  4. Default-long + cash only in Stagflation       (regime-veto)
  5. Default-long + cash only when MRMI red AND Stagflation  (joint veto)
  6. Regime-only: long unless Stagflation          (no MRMI)
  7. Asymmetric leverage by regime                 (lean in when reflation)
  8. Default-long + cash on (MRMI red AND Sahm triggered)    (Sahm veto)

For each, computes CAGR, alpha vs B&H, max DD, Sharpe.
Tests on full period, in-sample, out-of-sample.
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    fetch_all_data,
    calc_growth_impulse, calc_financial_conditions, calc_sector_breadth,
    calc_composite, calc_macro_context, _sahm_rule,
)


def quadrant(g, i):
    if pd.isna(g) or pd.isna(i):
        return None
    if g >= 0 and i < 0: return "Reflation"
    if g >= 0 and i >= 0: return "Expansion"
    if g < 0 and i < 0: return "Disinflation"
    return "Stagflation"


def stats(equity):
    if len(equity) == 0 or equity.iloc[0] == 0:
        return None
    cum = equity.iloc[-1] - 1
    years = (equity.index[-1] - equity.index[0]).days / 365.25
    cagr = (1 + cum) ** (1 / years) - 1 if years > 0 else 0
    rolling_max = equity.cummax()
    drawdown = equity / rolling_max - 1
    max_dd = drawdown.min()
    daily_ret = equity.pct_change().dropna()
    sharpe = (daily_ret.mean() / daily_ret.std() * np.sqrt(252)) if daily_ret.std() > 0 else 0
    return {"cagr": cagr, "cum": cum, "max_dd": max_dd, "sharpe": sharpe}


def run_period(label, ret, mrmi, regime_series, sahm_triggered, start=None, end=None):
    """Slice to a period and run all strategies."""
    idx = ret.index
    if start is not None:
        idx = idx[idx >= start]
    if end is not None:
        idx = idx[idx <= end]
    if len(idx) < 60:
        return

    ret_p = ret.reindex(idx).fillna(0)
    mrmi_p = mrmi.reindex(idx)
    regime_p = regime_series.reindex(idx)
    sahm_p = sahm_triggered.reindex(idx)

    mrmi_green = (mrmi_p > 0).shift(1).fillna(False)
    mrmi_red = ~mrmi_green
    is_stag = (regime_p == "Stagflation").shift(1).fillna(False)
    is_refl = (regime_p == "Reflation").shift(1).fillna(False)
    is_disinf = (regime_p == "Disinflation").shift(1).fillna(False)
    is_exp = (regime_p == "Expansion").shift(1).fillna(False)
    sahm_p_lag = sahm_p.shift(1).fillna(False)

    strategies = {}

    # 1. B&H
    strategies["1. Buy & Hold"] = pd.Series(1.0, index=idx)

    # 2. Pure MRMI binary
    strategies["2. Pure MRMI binary"] = mrmi_green.astype(float)

    # 3. MRMI + skip stagflation green flips
    pos = mrmi_green.astype(float).copy()
    pos[mrmi_green & is_stag] = 0.0
    strategies["3. MRMI + skip stag green"] = pos

    # 4. Default-long + cash only in Stagflation
    pos = pd.Series(1.0, index=idx)
    pos[is_stag] = 0.0
    strategies["4. Default-long, cash if stag"] = pos

    # 5. Default-long + cash only when MRMI red AND Stagflation
    pos = pd.Series(1.0, index=idx)
    pos[mrmi_red & is_stag] = 0.0
    strategies["5. Default-long, cash if MRMI red AND stag"] = pos

    # 6. Regime-only: long unless Stagflation
    pos = pd.Series(1.0, index=idx)
    pos[is_stag] = 0.0
    strategies["6. Regime-only: long unless stag"] = pos

    # 7. Asymmetric leverage by regime + MRMI
    # Reflation green=1.3x, Disinflation green=1.0x, Expansion green=0.7x, Stag green=0
    # Cash when MRMI red regardless of regime
    pos = pd.Series(0.0, index=idx)
    pos[mrmi_green & is_refl]  = 1.3
    pos[mrmi_green & is_disinf] = 1.0
    pos[mrmi_green & is_exp]   = 0.7
    pos[mrmi_green & is_stag]  = 0.0
    strategies["7. Leveraged regime sizing"] = pos

    # 8. Default-long + cash on (MRMI red AND Sahm triggered)
    pos = pd.Series(1.0, index=idx)
    pos[mrmi_red & sahm_p_lag] = 0.0
    strategies["8. Default-long, cash if MRMI red AND Sahm"] = pos

    # 9. MRMI green + Stagflation veto only when MRMI red triggers cash
    # (allow stagflation green if MRMI keeps green; only require MRMI red+stag for cash)
    pos = mrmi_green.astype(float).copy()
    # Allow stagflation green to be long (since strong-conviction stag green flips actually returned positive)
    strategies["9. MRMI binary, allow stag green"] = pos

    # 10. Default-long + 1.5x in Reflation+MRMI-green, cash if Stagflation
    pos = pd.Series(1.0, index=idx)
    pos[mrmi_green & is_refl] = 1.5
    pos[is_stag] = 0.0
    strategies["10. Default-long, +1.5x reflation, cash stag"] = pos

    # 11. Default-long + 2x in (Reflation OR Disinflation) AND MRMI green, cash if Stagflation
    pos = pd.Series(1.0, index=idx)
    pos[mrmi_green & (is_refl | is_disinf)] = 2.0
    pos[is_stag] = 0.0
    strategies["11. Default-long, +2x in safe regimes, cash stag"] = pos

    # 12. Aggressive: 2x when MRMI green AND regime != Stag, cash when MRMI red OR Stag
    pos = pd.Series(0.0, index=idx)
    pos[mrmi_green & ~is_stag] = 2.0
    strategies["12. Aggressive: 2x green/nonstag, cash else"] = pos

    # 13. Default 1x + 1.5x only in Reflation regime (no MRMI requirement)
    pos = pd.Series(1.0, index=idx)
    pos[is_refl] = 1.5
    pos[is_stag] = 0.0
    strategies["13. 1x base, +1.5x reflation, cash stag"] = pos

    print("\n" + "═" * 100)
    bh_stats = stats((1 + ret_p).cumprod())
    bh_cagr = bh_stats["cagr"] * 100
    print(f"{label:<24} ({idx[0].date()} → {idx[-1].date()}, {(idx[-1]-idx[0]).days/365.25:.1f}y)  ·  B&H CAGR {bh_cagr:.1f}%")
    print("─" * 100)
    print(f"{'Strategy':<48}  {'CAGR':>7}  {'Alpha':>8}  {'MaxDD':>8}  {'Sharpe':>7}")
    print("─" * 100)

    rows = []
    for name, pos in strategies.items():
        eq = (1 + ret_p * pos).cumprod()
        s = stats(eq)
        if s is None:
            continue
        alpha = (s["cagr"] - bh_stats["cagr"]) * 100
        rows.append({
            "name": name,
            "cagr": s["cagr"] * 100,
            "alpha": alpha,
            "max_dd": s["max_dd"] * 100,
            "sharpe": s["sharpe"],
        })

    # sort by alpha
    rows.sort(key=lambda r: r["alpha"], reverse=True)
    for r in rows:
        marker = " ★" if r["alpha"] > 0.5 else ("  " if r["alpha"] >= -0.5 else "  ")
        print(f"{r['name']:<48}  {r['cagr']:>6.1f}% {r['alpha']:>+7.1f}pp{marker}  {r['max_dd']:>7.1f}%  {r['sharpe']:>6.2f}")


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

    # Daily regime classification
    regime_series = pd.Series(
        [quadrant(re_score.get(d), inf_dir.get(d)) for d in mrmi.index],
        index=mrmi.index,
    )

    # Sahm Rule triggered (≥+0.5pp). Use lagged unrate to avoid look-ahead.
    unrate_lagged = data["UNRATE"].shift(35)  # release lag ~35 days
    sahm = _sahm_rule(unrate_lagged)
    sahm_triggered = (sahm >= 0.5)

    for asset_name, col in [("SPX", "^GSPC"), ("BTC", "BTC-USD")]:
        if col not in data:
            continue
        ret = data[col].pct_change()
        print("\n" + "█" * 100)
        print(f"█ ASSET: {asset_name}")
        print("█" * 100)
        run_period(f"{asset_name} FULL", ret, mrmi, regime_series, sahm_triggered)
        run_period(f"{asset_name} IN-SAMPLE", ret, mrmi, regime_series, sahm_triggered, end=pd.Timestamp("2022-12-31"))
        run_period(f"{asset_name} OOS", ret, mrmi, regime_series, sahm_triggered, start=pd.Timestamp("2023-01-01"))


if __name__ == "__main__":
    main()
