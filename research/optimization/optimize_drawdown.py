#!/usr/bin/env python3
"""
optimize_drawdown.py

Re-optimize for DRAWDOWN REDUCTION rather than alpha. Score = average Calmar
ratio (CAGR / |Max DD|) across SPX/IWM/BTC. Penalize configurations where
absolute alpha drag exceeds -5pp (we accept some drag, but not unlimited).

Search space:
  - MMI fast_roc: 14, 21, 30, 42
  - Breadth lookback: 30, 63, 90, 126
  - FinCon lookback: 126, 252, 504
  - MMI weights: equal / alpha / MMI-heavy / breadth-heavy
  - Buffer: 0 (no macro filter), 1.0, 2.0
  - Threshold: 0, +0.5 (more aggressive de-risking)
"""

import itertools
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

from build import calc_macro_context, fetch_all_data


def stats_full(asset_returns, signal, threshold=0):
    pos = (signal > threshold).astype(float).shift(1).fillna(0)
    eq_strat = (1 + asset_returns.fillna(0) * pos).cumprod()
    eq_bh = (1 + asset_returns.fillna(0)).cumprod()
    if len(eq_strat) < 30:
        return None
    years = (eq_strat.index[-1] - eq_strat.index[0]).days / 365.25
    cagr_strat = eq_strat.iloc[-1] ** (1 / years) - 1
    cagr_bh = eq_bh.iloc[-1] ** (1 / years) - 1
    max_dd = (eq_strat / eq_strat.cummax() - 1).min()
    bh_dd = (eq_bh / eq_bh.cummax() - 1).min()
    calmar = cagr_strat / abs(max_dd) if max_dd != 0 else 0
    return {
        "cagr_strat": cagr_strat * 100, "cagr_bh": cagr_bh * 100,
        "alpha": (cagr_strat - cagr_bh) * 100,
        "max_dd": max_dd * 100, "bh_dd": bh_dd * 100,
        "dd_reduction_pp": (max_dd - bh_dd) * 100,  # positive = strategy lost less
        "calmar": calmar,
        "cash_pct": (1 - pos).mean() * 100,
    }


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)
    macro = calc_macro_context(data, lookback_years=3, apply_release_lags=True)

    asset_returns = {
        "SPX": data["^GSPC"].pct_change(),
        "IWM": data["IWM"].pct_change(),
        "BTC": data["BTC-USD"].pct_change(),
    }

    param_grid = {
        "fast_roc": [14, 21, 30, 42],
        "breadth_lb": [30, 63, 90, 126],
        "fincon_lb": [126, 252, 504],
        "weights": [(0.33, 0.33, 0.34), (0.37, 0.35, 0.28), (0.50, 0.25, 0.25), (0.25, 0.50, 0.25)],
        "buffer": [0.0, 1.0, 2.0],     # buffer 0 = pure MMI (no macro filter)
        "threshold": [0.0, 0.5],         # higher threshold = more aggressive de-risking
    }

    n_combos = 1
    for k, v in param_grid.items():
        n_combos *= len(v)
    print(f"Searching {n_combos} parameter combinations...\n")

    results = []
    progress = 0
    for fast_roc, breadth_lb, fincon_lb, weights, buffer, threshold in itertools.product(
        param_grid["fast_roc"], param_grid["breadth_lb"], param_grid["fincon_lb"],
        param_grid["weights"], param_grid["buffer"], param_grid["threshold"]
    ):
        gii = calc_gii_custom(data, fast_roc=fast_roc)
        breadth = calc_breadth_custom(data, lookback=breadth_lb)
        fincon = calc_fincon_custom(data, lookback=fincon_lb)
        mmi, mrmi, _ = calc_combined_mrmi(gii["fast"], breadth, fincon, macro,
                                           weights=weights, buffer_size=buffer)
        signal = mrmi.dropna()
        if len(signal) < 252:
            continue

        per_asset = {}
        avg_calmar = 0
        avg_alpha = 0
        avg_dd_reduction = 0
        n = 0
        for asset_name, ret in asset_returns.items():
            ret_aligned = ret.reindex(signal.index)
            r = stats_full(ret_aligned, signal, threshold=threshold)
            if r is None: continue
            per_asset[asset_name] = r
            avg_calmar += r["calmar"]
            avg_alpha += r["alpha"]
            avg_dd_reduction += r["dd_reduction_pp"]
            n += 1
        if n == 0: continue
        avg_calmar /= n
        avg_alpha /= n
        avg_dd_reduction /= n

        # Score: maximize Calmar, but penalize if avg alpha < -5pp
        alpha_penalty = 0
        if avg_alpha < -5:
            alpha_penalty = (avg_alpha + 5) * 0.1  # smooth penalty below -5pp

        score = avg_calmar + alpha_penalty

        spx_cash_pct = per_asset.get("SPX", {}).get("cash_pct", 0)

        results.append({
            "fast_roc": fast_roc, "breadth_lb": breadth_lb, "fincon_lb": fincon_lb,
            "weights": weights, "buffer": buffer, "threshold": threshold,
            "avg_calmar": avg_calmar, "avg_alpha": avg_alpha,
            "avg_dd_reduction": avg_dd_reduction,
            "spx_cash_pct": spx_cash_pct, "score": score,
            **{f"{k}_alpha": v["alpha"] for k, v in per_asset.items()},
            **{f"{k}_dd": v["max_dd"] for k, v in per_asset.items()},
            **{f"{k}_calmar": v["calmar"] for k, v in per_asset.items()},
        })
        progress += 1
        if progress % 100 == 0:
            print(f"  ... {progress}/{n_combos}")

    print(f"Completed {len(results)} valid combinations.\n")
    df = pd.DataFrame(results).sort_values("score", ascending=False)

    # B&H baseline for reference
    print("Buy-and-hold baseline (full period):")
    for asset_name, ret in asset_returns.items():
        # Use first available index
        ret_clean = ret.dropna()
        eq_bh = (1 + ret_clean).cumprod()
        years = (eq_bh.index[-1] - eq_bh.index[0]).days / 365.25
        cagr = eq_bh.iloc[-1] ** (1 / years) - 1
        max_dd = (eq_bh / eq_bh.cummax() - 1).min()
        calmar = cagr / abs(max_dd)
        print(f"  {asset_name}: CAGR {cagr*100:.1f}%  MaxDD {max_dd*100:.1f}%  Calmar {calmar:.2f}")

    print("\n" + "─" * 130)
    print("TOP 15 BY DRAWDOWN-OPTIMIZED SCORE (avg Calmar across SPX/IWM/BTC, alpha-penalized below -5pp)")
    print("─" * 130)
    print(f"{'fast':>5} {'brdth':>6} {'fcon':>5} {'weights':<22} {'buf':>4} {'thr':>4} {'cash%':>6} {'avg α':>7} {'avg ΔDD':>9} {'avg Calmar':>11} {'SPX C':>7} {'IWM C':>7} {'BTC C':>7}")
    print("─" * 130)
    for _, r in df.head(15).iterrows():
        w = r["weights"]
        wstr = f"{w[0]:.2f}/{w[1]:.2f}/{w[2]:.2f}"
        print(f"{r['fast_roc']:>5} {r['breadth_lb']:>6} {r['fincon_lb']:>5} {wstr:<22} {r['buffer']:>4.1f} {r['threshold']:>4.1f} {r['spx_cash_pct']:>5.1f}% {r['avg_alpha']:>+6.1f}pp {r['avg_dd_reduction']:>+7.1f}pp {r['avg_calmar']:>10.2f} {r.get('SPX_calmar', 0):>6.2f} {r.get('IWM_calmar', 0):>6.2f} {r.get('BTC_calmar', 0):>6.2f}")

    out_path = Path(__file__).parent / ".cache" / "drawdown_optimization.csv"
    df.to_csv(out_path, index=False)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()
