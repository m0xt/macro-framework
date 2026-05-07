#!/usr/bin/env python3
"""
optimize_mrmi.py

Re-optimize MMI parameters specifically for the COMBINED MRMI strategy
(long unless MRMI < 0). Different from the original optimize.py which
optimized standalone MMI alpha.

Searches over:
  - GII fast window (21 / 30 / 42 / 60)
  - Breadth lookback (30 / 63 / 90 / 126)
  - FinCon lookback (126 / 252 / 504)
  - MMI weights: equal vs alpha-weighted
  - MRMI buffer (1.0 / 1.5 / 2.0)

For each combo:
  1. Compute MMI, then MRMI = MMI + buffer × (1 − stress)
  2. Backtest "long if MRMI > 0, cash otherwise" on SPX/IWM/BTC
  3. Score by: avg full-period alpha across assets + cash-frequency penalty
     (we want SOME activity, not just always-long)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import itertools

sys.path.insert(0, str(Path(__file__).parent))
from build import (
    fetch_all_data,
    calc_financial_conditions, calc_sector_breadth,
    calc_macro_context, _zscore, clip_series,
)


def _roc(series: pd.Series, period: int) -> pd.Series:
    return series.pct_change(period) * 100


def _chg(series: pd.Series, period: int) -> pd.Series:
    return series - series.shift(period)


def calc_gii_custom(data: pd.DataFrame, fast_roc: int = 21, slow_roc: int = 126,
                    z_len: int = 504, clip_z: float = 3.0) -> pd.DataFrame:
    """GII with parametrized windows."""
    components_list = [
        ("HYG_inv", lambda d: -d["HYG"] if "HYG" in d else None),
        ("HY_spread_inv", lambda d: -d["BAMLH0A0HYM2"] if "BAMLH0A0HYM2" in d else None),
        ("XLY_XLP", lambda d: d["XLY"] / d["XLP"] if "XLY" in d and "XLP" in d else None),
        ("XLI_XLU", lambda d: d["XLI"] / d["XLU"] if "XLI" in d and "XLU" in d else None),
        ("SPHB_SPLV", lambda d: d["SPHB"] / d["SPLV"] if "SPHB" in d and "SPLV" in d else None),
        ("HG", lambda d: d["HG=F"] if "HG=F" in d else None),
        ("VIX_inv", lambda d: -d["^VIX"] if "^VIX" in d else None),
        ("YC", lambda d: (d["DGS10"] - d["DGS2"]) if "DGS10" in d and "DGS2" in d else None),
        ("WEI", lambda d: d["WEI"] if "WEI" in d else None),
    ]
    z_fasts, z_slows = [], []
    for _, fn in components_list:
        s = fn(data)
        if s is None:
            continue
        if (s <= 0).any():
            sf, ss = _chg(s, fast_roc), _chg(s, slow_roc)
        else:
            sf, ss = _roc(s, fast_roc), _roc(s, slow_roc)
        z_fasts.append(clip_series(_zscore(sf, z_len), clip_z))
        z_slows.append(clip_series(_zscore(ss, z_len), clip_z))

    fast = pd.DataFrame(z_fasts).T.mean(axis=1, skipna=True)
    slow = pd.DataFrame(z_slows).T.mean(axis=1, skipna=True)
    return pd.DataFrame({"fast": fast, "slow": slow}, index=data.index)


def calc_breadth_custom(data: pd.DataFrame, lookback: int = 63) -> pd.Series:
    tickers = ["SMH", "IWM", "IYT", "IBB", "XHB", "KBE", "XRT"]
    components = {}
    for t in tickers:
        if t in data:
            components[t] = _zscore(data[t], lookback)
    if not components:
        return pd.Series(dtype=float)
    return pd.DataFrame(components).mean(axis=1, skipna=True)


def calc_fincon_custom(data: pd.DataFrame, lookback: int = 252) -> pd.Series:
    components = {}
    for col in ["^VIX", "^MOVE", "BAMLH0A0HYM2"]:
        if col in data:
            components[col] = -_zscore(data[col], lookback)
    if not components:
        return pd.Series(dtype=float)
    return pd.DataFrame(components).mean(axis=1, skipna=True)


def calc_combined_mrmi(mmi_fast, breadth, fincon, macro_ctx, weights=(0.37, 0.35, 0.28), buffer_size=2.0):
    w_g, w_b, w_f = weights
    w_t = w_g + w_b + w_f
    mmi = (mmi_fast * w_g + breadth * w_b + fincon * w_f) / w_t

    re = macro_ctx["real_economy_score"].reindex(mmi.index)
    inf_dir = macro_ctx["inflation_dir_pp"].reindex(mmi.index)
    re_neg = (-re).clip(lower=0)
    inf_pos = inf_dir.clip(lower=0)
    stress = (re_neg * inf_pos).clip(upper=1.0)
    mrmi = mmi + buffer_size * (1 - stress)
    return mmi, mrmi, stress


def backtest_strategy(mrmi, asset_returns):
    pos = (mrmi > 0).astype(float).shift(1).fillna(0)
    eq_strategy = (1 + asset_returns.fillna(0) * pos).cumprod()
    eq_bh = (1 + asset_returns.fillna(0)).cumprod()
    if len(eq_bh) < 30:
        return None
    years = (eq_bh.index[-1] - eq_bh.index[0]).days / 365.25
    if years <= 0:
        return None
    cagr_bh = (eq_bh.iloc[-1]) ** (1 / years) - 1
    cagr_strat = (eq_strategy.iloc[-1]) ** (1 / years) - 1
    rolling_max = eq_strategy.cummax()
    max_dd = (eq_strategy / rolling_max - 1).min()
    return {"alpha": (cagr_strat - cagr_bh) * 100, "cagr": cagr_strat * 100,
            "max_dd": max_dd * 100, "pct_cash": (1 - pos).mean() * 100}


def main():
    print("Loading data...")
    data = fetch_all_data(use_cache=True)
    macro = calc_macro_context(data, lookback_years=3, apply_release_lags=True)

    asset_returns = {
        "SPX": data["^GSPC"].pct_change(),
        "IWM": data["IWM"].pct_change() if "IWM" in data else None,
        "BTC": data["BTC-USD"].pct_change() if "BTC-USD" in data else None,
    }

    # Parameter grid
    param_grid = {
        "fast_roc": [14, 21, 30, 42, 60],
        "breadth_lb": [30, 63, 90, 126],
        "fincon_lb": [126, 252, 504],
        "weights": [(0.33, 0.33, 0.34), (0.37, 0.35, 0.28), (0.50, 0.25, 0.25), (0.25, 0.50, 0.25), (0.25, 0.25, 0.50)],
        "buffer": [1.0, 1.5, 2.0],
    }

    n_combos = (len(param_grid["fast_roc"]) * len(param_grid["breadth_lb"]) *
                len(param_grid["fincon_lb"]) * len(param_grid["weights"]) * len(param_grid["buffer"]))
    print(f"Searching {n_combos} parameter combinations...\n")

    results = []
    progress = 0
    for fast_roc, breadth_lb, fincon_lb, weights, buffer in itertools.product(
        param_grid["fast_roc"], param_grid["breadth_lb"], param_grid["fincon_lb"],
        param_grid["weights"], param_grid["buffer"]
    ):
        gii = calc_gii_custom(data, fast_roc=fast_roc)
        breadth = calc_breadth_custom(data, lookback=breadth_lb)
        fincon = calc_fincon_custom(data, lookback=fincon_lb)
        mmi, mrmi, stress = calc_combined_mrmi(gii["fast"], breadth, fincon, macro,
                                                 weights=weights, buffer_size=buffer)
        mrmi = mrmi.dropna()
        if len(mrmi) < 252:
            continue
        # Common index for all assets
        common_idx = mrmi.index
        per_asset = {}
        avg_alpha = 0
        n_alpha = 0
        for asset_name, ret in asset_returns.items():
            if ret is None: continue
            ret_aligned = ret.reindex(common_idx)
            res = backtest_strategy(mrmi, ret_aligned)
            if res is None: continue
            per_asset[asset_name] = res
            avg_alpha += res["alpha"]
            n_alpha += 1
        if n_alpha == 0: continue
        avg_alpha /= n_alpha

        # Activity: % of time in cash. Want at least 5%, penalize less than that.
        spx_cash_pct = per_asset.get("SPX", {}).get("pct_cash", 0)
        # Score: alpha + small bonus for activity above 5%, penalty if too passive
        activity_bonus = 0
        if spx_cash_pct < 3:
            activity_bonus = -2  # penalize too-passive frameworks
        elif 5 <= spx_cash_pct <= 25:
            activity_bonus = 1  # reward modest activity
        score = avg_alpha + activity_bonus

        results.append({
            "fast_roc": fast_roc, "breadth_lb": breadth_lb, "fincon_lb": fincon_lb,
            "weights": weights, "buffer": buffer,
            "avg_alpha": avg_alpha, "score": score, "spx_cash_pct": spx_cash_pct,
            **{f"{k}_alpha": v["alpha"] for k, v in per_asset.items()},
            **{f"{k}_dd": v["max_dd"] for k, v in per_asset.items()},
        })
        progress += 1
        if progress % 50 == 0:
            print(f"  ... {progress}/{n_combos}")

    print(f"Completed {len(results)} valid combinations.\n")
    df = pd.DataFrame(results).sort_values("score", ascending=False)

    print("─" * 110)
    print("TOP 15 BY COMBINED SCORE (avg alpha + activity bonus)")
    print("─" * 110)
    print(f"{'fast':>5} {'brdth':>6} {'fcon':>5} {'weights':<22} {'buf':>4} {'cash%':>6} {'SPX α':>7} {'IWM α':>7} {'BTC α':>7} {'avg α':>7} {'score':>7}")
    print("─" * 110)
    for _, r in df.head(15).iterrows():
        w = r["weights"]
        wstr = f"{w[0]:.2f}/{w[1]:.2f}/{w[2]:.2f}"
        print(f"{r['fast_roc']:>5} {r['breadth_lb']:>6} {r['fincon_lb']:>5} {wstr:<22} {r['buffer']:>4} {r['spx_cash_pct']:>5.1f}% {r.get('SPX_alpha', 0):>+6.1f}pp {r.get('IWM_alpha', 0):>+6.1f}pp {r.get('BTC_alpha', 0):>+6.1f}pp {r['avg_alpha']:>+6.1f}pp {r['score']:>+6.1f}")

    out_path = Path(__file__).parent / ".cache" / "mrmi_optimization.csv"
    df.to_csv(out_path, index=False)
    print(f"\nFull results saved to {out_path}")


if __name__ == "__main__":
    main()
