"""Grid-search the macro buffer for both stress models.

Compares the framework's two candidate stress signals on equal terms:

    1. HARD CLIP (current production):
         stress = min(1, max(0, -RE) × max(0, Inf_Dir))
       Stress is exactly 0 whenever growth is OK or inflation is falling.

    2. SMOOTHED (sigmoid):
         stress = sigmoid(-k · RE) × sigmoid(k · Inf_Dir),  k = 2
       Always non-zero; gradually responds to gradual shifts.

For each stress model the script grid-searches over (buffer_size, threshold)
to find the best params for the MRMI signal:

    MRMI = MMI + buffer_size × (1 − stress) − threshold

Strategy: invested when MRMI > 0, cash when MRMI < 0. Backtest on SPX, IWM,
BTC. 70/30 in-sample / out-of-sample split.

Run with: .venv/bin/python optimize_stress.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from build import (
    fetch_all_data,
    calc_growth_impulse,
    calc_financial_conditions,
    calc_sector_breadth,
    calc_composite,
    calc_macro_context,
)
from optimize import evaluate_signal


# ── stress models ──────────────────────────────────────────────────────────

def stress_hard(re: pd.Series, inf: pd.Series) -> pd.Series:
    re_neg = (-re).clip(lower=0)
    inf_pos = inf.clip(lower=0)
    return (re_neg * inf_pos).clip(upper=1.0)


def _sigmoid(x: pd.Series) -> pd.Series:
    return 1.0 / (1.0 + np.exp(-x))


def stress_smooth(re: pd.Series, inf: pd.Series, k: float = 2.0) -> pd.Series:
    return _sigmoid(-k * re) * _sigmoid(k * inf)


# ── MRMI builder ───────────────────────────────────────────────────────────

def build_mrmi(mmi: pd.Series, stress: pd.Series,
               buffer_size: float, threshold: float) -> pd.Series:
    buffer = buffer_size * (1.0 - stress)
    return mmi + buffer - threshold


# ── grid search ────────────────────────────────────────────────────────────

BUFFER_GRID = [0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00]
THRESHOLD_GRID = [0.00, 0.10, 0.25, 0.40, 0.50, 0.60, 0.75, 1.00]


def calmar(strat_ann: float, maxdd_pct: float) -> float:
    """Calmar ratio: ann return / |max drawdown|. Higher = better risk-adjusted."""
    dd = abs(maxdd_pct)
    if dd < 1.0:
        return strat_ann  # avoid blowing up when DD is tiny
    return strat_ann / dd


def grid_search(label: str, mmi: pd.Series, stress: pd.Series,
                asset_rets: dict[str, pd.Series], split_idx: int) -> list[dict]:
    rows = []
    for bs in BUFFER_GRID:
        for thr in THRESHOLD_GRID:
            mrmi = build_mrmi(mmi, stress, bs, thr)

            is_eval = evaluate_signal(
                mrmi.iloc[:split_idx],
                {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                green_above=True,
            )
            if is_eval is None:
                continue

            oos_eval = evaluate_signal(
                mrmi.iloc[split_idx:],
                {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                green_above=True,
            )
            if oos_eval is None:
                continue

            # Composite metric: average Calmar across SPX/IWM/BTC, plus alpha.
            cal_spx = calmar(is_eval["strat_spx_ann"], is_eval["strat_maxdd_spx"])
            cal_iwm = calmar(is_eval["strat_iwm_ann"], is_eval["strat_maxdd_iwm"])
            cal_btc = calmar(is_eval["strat_btc_ann"], is_eval["strat_maxdd_btc"])
            avg_calmar = (cal_spx + cal_iwm + cal_btc) / 3

            alpha_spx = is_eval["strat_spx_ann"] - is_eval["bh_spx_ann"]
            alpha_iwm = is_eval["strat_iwm_ann"] - is_eval["bh_iwm_ann"]
            alpha_btc = is_eval["strat_btc_ann"] - is_eval["bh_btc_ann"]
            avg_alpha = (alpha_spx + alpha_iwm + alpha_btc) / 3

            oos_alpha_spx = oos_eval["strat_spx_ann"] - oos_eval["bh_spx_ann"]
            oos_alpha_iwm = oos_eval["strat_iwm_ann"] - oos_eval["bh_iwm_ann"]
            oos_alpha_btc = oos_eval["strat_btc_ann"] - oos_eval["bh_btc_ann"]
            avg_oos_alpha = (oos_alpha_spx + oos_alpha_iwm + oos_alpha_btc) / 3

            rows.append({
                "model": label,
                "buffer": bs,
                "threshold": thr,
                "calmar": avg_calmar,
                "is_alpha": avg_alpha,
                "oos_alpha": avg_oos_alpha,
                "is_alpha_spx": alpha_spx,
                "is_alpha_iwm": alpha_iwm,
                "is_alpha_btc": alpha_btc,
                "oos_alpha_spx": oos_alpha_spx,
                "oos_alpha_iwm": oos_alpha_iwm,
                "oos_alpha_btc": oos_alpha_btc,
                "is_dd_spx": is_eval["strat_maxdd_spx"],
                "is_dd_iwm": is_eval["strat_maxdd_iwm"],
                "is_dd_btc": is_eval["strat_maxdd_btc"],
                "green_pct": is_eval["green_pct"],
                "flips_per_year": is_eval["flips_per_year"],
            })
    return rows


# ── reporting ──────────────────────────────────────────────────────────────

def fmt(v: float, dec: int = 2) -> str:
    return f"{v:+.{dec}f}"


def print_top(rows: list[dict], n: int = 8, sort_by: str = "calmar") -> None:
    rows.sort(key=lambda r: r[sort_by], reverse=True)
    print(f"\n  Top {n} by {sort_by}:\n")
    print(f"  {'rank':>4}  {'buf':>5}  {'thr':>5}  {'calmar':>7}  "
          f"{'IS α':>8}  {'OOS α':>8}  {'green%':>7}  {'flips/y':>8}")
    print(f"  {'-'*4}  {'-'*5}  {'-'*5}  {'-'*7}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8}")
    for i, r in enumerate(rows[:n], 1):
        print(f"  {i:>4}  {r['buffer']:>5.2f}  {r['threshold']:>5.2f}  "
              f"{r['calmar']:>7.2f}  {fmt(r['is_alpha']):>8}  {fmt(r['oos_alpha']):>8}  "
              f"{r['green_pct']:>6.1f}%  {r['flips_per_year']:>7.1f}")


def print_detail(label: str, row: dict) -> None:
    print(f"\n  {label}:")
    print(f"    Best params: buffer_size={row['buffer']:.2f}, threshold={row['threshold']:.2f}")
    print(f"    Avg Calmar (IS):  {row['calmar']:.2f}")
    print(f"    Active fraction:  {row['green_pct']:.1f}%   Flips/year: {row['flips_per_year']:.1f}")
    print(f"    {'asset':<8} {'IS alpha':>10} {'OOS alpha':>10} {'IS max DD':>10}")
    print(f"    {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
    for asset in ("spx", "iwm", "btc"):
        print(f"    {asset.upper():<8} {fmt(row[f'is_alpha_{asset}']):>10} "
              f"{fmt(row[f'oos_alpha_{asset}']):>10} {fmt(row[f'is_dd_{asset}'], 1):>9}%")


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print("=" * 80)
    print("Macro Stress Optimizer — Hard Clip vs Smoothed Sigmoid")
    print("=" * 80)

    print("\n  Loading data...", flush=True)
    data = fetch_all_data(use_cache=True)
    print(f"  Loaded {len(data)} rows from {data.index[0].date()} to {data.index[-1].date()}")

    print("  Computing indicators (GII / FinCon / Breadth / MMI)...", flush=True)
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mmi = calc_composite(gii, fincon, breadth)

    print("  Computing macro context (Real Economy Score, Inflation Direction)...", flush=True)
    macro_ctx = calc_macro_context(data)
    re_score = macro_ctx.get("real_economy_score")
    inf_dir = macro_ctx.get("inflation_dir_pp")
    if re_score is None or inf_dir is None:
        raise SystemExit("Macro context missing — cannot run stress optimization.")

    re = re_score.reindex(mmi.index)
    inf = inf_dir.reindex(mmi.index)

    # Build both stress series
    stress_h = stress_hard(re, inf)
    stress_s = stress_smooth(re, inf, k=2.0)

    # Asset returns + 70/30 split
    asset_rets = {
        "spx": data["^GSPC"].pct_change().reindex(mmi.index),
        "iwm": data["IWM"].pct_change().reindex(mmi.index),
        "btc": data["BTC-USD"].pct_change().reindex(mmi.index),
    }
    aligned = pd.DataFrame({"mmi": mmi, "stress_h": stress_h, "stress_s": stress_s,
                            **asset_rets}).dropna()
    n = len(aligned)
    split_idx = int(n * 0.70)
    print(f"\n  Aligned {n} rows. IS = first 70% ({n - (n - split_idx)} bars), "
          f"OOS = last 30% ({n - split_idx} bars).")
    print(f"  Search grid: {len(BUFFER_GRID)}×{len(THRESHOLD_GRID)} = "
          f"{len(BUFFER_GRID) * len(THRESHOLD_GRID)} combos × 2 stress models.\n")

    asset_rets_aligned = {k: aligned[k] for k in ("spx", "iwm", "btc")}

    print("  [1/2] Grid-searching HARD CLIP stress...", flush=True)
    rows_h = grid_search("hard", aligned["mmi"], aligned["stress_h"],
                          asset_rets_aligned, split_idx)

    print("  [2/2] Grid-searching SMOOTHED (sigmoid k=2) stress...", flush=True)
    rows_s = grid_search("smooth", aligned["mmi"], aligned["stress_s"],
                          asset_rets_aligned, split_idx)

    # Reports
    print("\n" + "=" * 80)
    print("HARD CLIP STRESS — Top results")
    print("=" * 80)
    print_top(rows_h, n=8, sort_by="calmar")

    print("\n" + "=" * 80)
    print("SMOOTHED STRESS — Top results")
    print("=" * 80)
    print_top(rows_s, n=8, sort_by="calmar")

    # Best of each
    rows_h.sort(key=lambda r: r["calmar"], reverse=True)
    rows_s.sort(key=lambda r: r["calmar"], reverse=True)
    best_h = rows_h[0]
    best_s = rows_s[0]

    print("\n" + "=" * 80)
    print("HEAD-TO-HEAD: Best of each model")
    print("=" * 80)
    print_detail("HARD CLIP — best", best_h)
    print_detail("SMOOTHED  — best", best_s)

    # Current production params for reference
    current_h = next((r for r in rows_h if r["buffer"] == 1.00 and r["threshold"] == 0.50), None)
    if current_h:
        print("\n  CURRENT PRODUCTION (hard-clip, buffer=1.00, threshold=0.50):")
        print_detail("HARD CLIP — current production params", current_h)

    print("\n" + "=" * 80)
    print("VERDICT")
    print("=" * 80)
    print(f"  Best hard-clip Calmar : {best_h['calmar']:.2f}  (buf={best_h['buffer']:.2f}, thr={best_h['threshold']:.2f})")
    print(f"  Best smoothed Calmar  : {best_s['calmar']:.2f}  (buf={best_s['buffer']:.2f}, thr={best_s['threshold']:.2f})")
    print(f"  Best hard-clip OOS α  : {best_h['oos_alpha']:+.2f}%/yr (avg of SPX/IWM/BTC)")
    print(f"  Best smoothed OOS α   : {best_s['oos_alpha']:+.2f}%/yr (avg of SPX/IWM/BTC)")
    diff = best_s["oos_alpha"] - best_h["oos_alpha"]
    print(f"  OOS α delta (smoothed − hard): {diff:+.2f}%/yr")
    if abs(diff) < 0.5:
        verdict = "no meaningful edge — keep production hard-clip"
    elif diff > 0:
        verdict = "smoothed wins on OOS alpha — worth considering switching"
    else:
        verdict = "hard-clip wins on OOS alpha — keep production"
    print(f"  → {verdict}")
    print()


if __name__ == "__main__":
    main()
