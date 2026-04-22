#!/usr/bin/env python3
"""
Parameter optimizer for macro indicators.
Runs grid search over parameter combinations, evaluates each on in-sample data,
validates best candidates on out-of-sample data.

Usage:
  python optimize.py fincon    # Optimize Financial Conditions
"""

import json
import sys
import itertools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

CACHE_DIR = Path(__file__).parent / ".cache"
DATA_CACHE = CACHE_DIR / "raw_data.pkl"

# ============================================================================
# HELPERS
# ============================================================================

def zscore(series: pd.Series, lookback: int) -> pd.Series:
    m = series.rolling(lookback, min_periods=lookback // 2).mean()
    s = series.rolling(lookback, min_periods=lookback // 2).std()
    return (series - m) / s.replace(0, np.nan)


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


@dataclass
class BacktestResult:
    params: dict
    is_eval: dict   # in-sample evaluation
    oos_eval: dict  # out-of-sample evaluation
    score: float


def calc_max_drawdown(returns: pd.Series) -> float:
    """Max drawdown from a series of daily returns."""
    cum = (1 + returns).cumprod()
    peak = cum.cummax()
    dd = (cum - peak) / peak
    return float(dd.min()) if len(dd) > 0 else 0.0


def calc_sharpe(returns: pd.Series) -> float:
    """Annualized Sharpe ratio."""
    if len(returns) < 20 or returns.std() == 0:
        return 0.0
    return float(returns.mean() / returns.std() * np.sqrt(252))


def count_flips(signal: pd.Series) -> int:
    """Count number of regime changes."""
    regime = (signal > 0).astype(int)
    return int((regime.diff().abs() > 0).sum())


def avg_regime_duration(signal: pd.Series) -> float:
    """Average number of days per regime."""
    regime = (signal > 0).astype(int)
    changes = regime.diff().abs() > 0
    n_flips = changes.sum()
    if n_flips == 0:
        return len(signal)
    return len(signal) / (n_flips + 1)


def evaluate_signal(signal: pd.Series, asset_rets: dict[str, pd.Series],
                    green_above: bool = True) -> dict:
    """Evaluate a signal against multiple asset returns."""
    df = {"signal": signal}
    df.update(asset_rets)
    aligned = pd.DataFrame(df).dropna()

    if len(aligned) < 100:
        return None

    if green_above:
        green = aligned["signal"] > 0
    else:
        green = aligned["signal"] < 0

    n_years = len(aligned) / 252

    result = {
        "green_pct": float(green.sum() / len(aligned) * 100),
        "flips_per_year": count_flips(aligned["signal"]) / n_years if n_years > 0 else 0,
        "avg_duration": avg_regime_duration(aligned["signal"]),
    }

    for name in asset_rets:
        green_r = aligned.loc[green, name]
        red_r = aligned.loc[~green, name]
        strat_r = aligned[name].where(green, 0)

        bh_cum = (1 + aligned[name]).cumprod()
        strat_cum = (1 + strat_r).cumprod()

        bh_total = (bh_cum.iloc[-1] - 1) * 100
        strat_total = (strat_cum.iloc[-1] - 1) * 100

        bh_ann = ((1 + bh_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
        strat_ann = ((1 + strat_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

        result[f"green_ann_{name}"] = float(green_r.mean() * 252 * 100) if len(green_r) > 0 else 0
        result[f"red_ann_{name}"] = float(red_r.mean() * 252 * 100) if len(red_r) > 0 else 0
        result[f"green_sharpe_{name}"] = calc_sharpe(green_r)
        result[f"red_sharpe_{name}"] = calc_sharpe(red_r)
        result[f"strat_maxdd_{name}"] = calc_max_drawdown(strat_r) * 100
        result[f"bh_maxdd_{name}"] = calc_max_drawdown(aligned[name]) * 100
        result[f"bh_{name}_ann"] = float(bh_ann)
        result[f"strat_{name}_ann"] = float(strat_ann)
        result[f"bh_{name}_total"] = float(bh_total)
        result[f"strat_{name}_total"] = float(strat_total)
        result[f"strat_sharpe_{name}"] = calc_sharpe(strat_r)
        result[f"bh_sharpe_{name}"] = calc_sharpe(aligned[name])

    return result


# ============================================================================
# FINANCIAL CONDITIONS OPTIMIZER
# ============================================================================

def optimize_fincon(data: pd.DataFrame, target: str = "spx"):
    """
    Grid search over Financial Conditions parameters.

    Parameters to optimize:
      - lookback: z-score window (63, 126, 189, 252, 378, 504)
      - smoothing: EMA applied to composite (1=none, 5, 10, 21)
      - threshold: dead zone entry/exit (0, 0.1, 0.2, 0.3, 0.5)
      - components: which of the 4 to include
    """
    components = {
        "VIX": data["^VIX"],
        "MOVE": data["^MOVE"],
        "HY": data["BAMLH0A0HYM2"],
        "IG": data["BAMLC0A0CM"],
    }

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    # In-sample / out-of-sample split (70/30)
    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()} ({split_idx} rows)")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()} ({n - split_idx} rows)")

    # Parameter grid
    lookbacks = [63, 126, 189, 252, 378, 504]
    smoothings = [1, 5, 10, 21]
    thresholds = [0, 0.1, 0.2, 0.3, 0.5]

    # Component subsets: all 4, and each combination of 3+
    component_sets = [
        ["VIX", "MOVE", "HY", "IG"],           # all 4
        ["VIX", "MOVE", "HY"],                  # drop IG
        ["VIX", "MOVE", "IG"],                  # drop HY
        ["VIX", "HY", "IG"],                    # drop MOVE
        ["MOVE", "HY", "IG"],                   # drop VIX
        ["VIX", "MOVE"],                        # just vol
        ["HY", "IG"],                           # just credit
    ]

    total = len(lookbacks) * len(smoothings) * len(thresholds) * len(component_sets)
    print(f"  Grid: {total} combinations\n")

    results = []
    best_score = -999
    tested = 0

    for lookback in lookbacks:
        for smooth in smoothings:
            for threshold in thresholds:
                for comp_names in component_sets:
                    tested += 1

                    # Build composite
                    zscores = []
                    for name in comp_names:
                        zscores.append(zscore(components[name], lookback))

                    composite = pd.concat(zscores, axis=1).mean(axis=1, skipna=True)
                    if smooth > 1:
                        composite = ema(composite, smooth)

                    # Apply threshold with hysteresis
                    if threshold > 0:
                        signal = pd.Series(np.nan, index=composite.index)
                        regime = 0  # 0 = neutral/red, 1 = green
                        for i in range(len(composite)):
                            v = composite.iloc[i]
                            if pd.isna(v):
                                signal.iloc[i] = np.nan
                                continue
                            # For fincon: BELOW -threshold = green (loose), ABOVE +threshold = red (tight)
                            if regime == 0 and v < -threshold:
                                regime = 1
                            elif regime == 1 and v > threshold:
                                regime = 0
                            signal.iloc[i] = 1.0 if regime == 1 else -1.0
                    else:
                        signal = composite.copy()
                        # For fincon: negative = green (loose conditions)

                    # Evaluate in-sample
                    is_signal = signal.iloc[:split_idx]
                    is_assets = {k: v.iloc[:split_idx] for k, v in asset_rets.items()}
                    is_eval = evaluate_signal(is_signal, is_assets, green_above=False)

                    if is_eval is None:
                        continue

                    # Evaluate out-of-sample
                    oos_signal = signal.iloc[split_idx:]
                    oos_assets = {k: v.iloc[split_idx:] for k, v in asset_rets.items()}
                    oos_eval = evaluate_signal(oos_signal, oos_assets, green_above=False)

                    if oos_eval is None:
                        continue

                    # Score depends on target asset
                    flip_penalty = max(0, is_eval["flips_per_year"] - 10) * 2
                    t = target  # spx, btc, or iwm

                    spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                    alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]

                    if target == "btc":
                        spread_spx = is_eval["green_ann_spx"] - is_eval["red_ann_spx"]
                        score = (
                            spread_t * 0.4 +
                            spread_spx * 0.1 +
                            alpha_t * 0.3 +
                            -abs(is_eval["green_pct"] - 55) * 0.5 +
                            -flip_penalty
                        )
                    else:
                        score = (
                            spread_t * 0.4 +
                            alpha_t * 0.3 +
                            is_eval[f"green_sharpe_{t}"] * 10 +
                            -abs(is_eval["green_pct"] - 60) * 0.5 +
                            -flip_penalty
                        )

                    params = {
                        "lookback": lookback,
                        "smoothing": smooth,
                        "threshold": threshold,
                        "components": comp_names,
                    }

                    r = BacktestResult(
                        params=params,
                        is_eval=is_eval,
                        oos_eval=oos_eval,
                        score=round(score, 1),
                    )
                    results.append(r)

                    if score > best_score:
                        best_score = score

    # Sort by score
    results.sort(key=lambda r: r.score, reverse=True)

    # Print top 5
    print(f"{'':─<120}")
    print(f"  TOP 5 PARAMETER SETS (out of {tested} tested)")
    print(f"{'':─<120}")

    for i, r in enumerate(results[:5]):
        p = r.params
        e = r.is_eval
        o = r.oos_eval
        comps = " + ".join(p["components"])
        print(f"\n  #{i+1}  Score: {r.score}")
        print(f"  Params: lookback={p['lookback']}, smooth={p['smoothing']}, threshold={p['threshold']}")
        print(f"  Components: {comps}")

        print(f"\n  {'':─<90}")
        print(f"  {'IN-SAMPLE (2016–2023)':^44} │ {'OUT-OF-SAMPLE (2023–2026)':^43}")
        print(f"  {'':─<44}─┼─{'':─<43}")

        for asset, label in [("spx", "SPX"), ("iwm", "IWM"), ("btc", "BTC")]:
            bh_is = e.get(f"bh_{asset}_ann", 0)
            bh_is_t = e.get(f"bh_{asset}_total", 0)
            st_is = e.get(f"strat_{asset}_ann", 0)
            st_is_t = e.get(f"strat_{asset}_total", 0)
            bh_oos = o.get(f"bh_{asset}_ann", 0)
            bh_oos_t = o.get(f"bh_{asset}_total", 0)
            st_oos = o.get(f"strat_{asset}_ann", 0)
            st_oos_t = o.get(f"strat_{asset}_total", 0)
            alpha_is = st_is - bh_is
            alpha_oos = st_oos - bh_oos

            print(f"  {label} Buy & Hold:   {bh_is:+6.1f}%/yr  ({bh_is_t:+.0f}% total)    │  {bh_oos:+6.1f}%/yr  ({bh_oos_t:+.0f}% total)")
            print(f"  {label} Signal-Only:  {st_is:+6.1f}%/yr  ({st_is_t:+.0f}% total)    │  {st_oos:+6.1f}%/yr  ({st_oos_t:+.0f}% total)")
            print(f"  {label} Alpha:        {alpha_is:+6.1f}%/yr                       │  {alpha_oos:+6.1f}%/yr")

            sh_is = e.get(f"strat_sharpe_{asset}", 0)
            bh_sh_is = e.get(f"bh_sharpe_{asset}", 0)
            sh_oos = o.get(f"strat_sharpe_{asset}", 0)
            bh_sh_oos = o.get(f"bh_sharpe_{asset}", 0)
            dd_is = e.get(f"strat_maxdd_{asset}", 0)
            bh_dd_is = e.get(f"bh_maxdd_{asset}", 0)
            dd_oos = o.get(f"strat_maxdd_{asset}", 0)
            bh_dd_oos = o.get(f"bh_maxdd_{asset}", 0)

            print(f"  {label} Sharpe:  strat {sh_is:.2f} vs B&H {bh_sh_is:.2f}            │  strat {sh_oos:.2f} vs B&H {bh_sh_oos:.2f}")
            print(f"  {label} MaxDD:   strat {dd_is:.1f}% vs B&H {bh_dd_is:.1f}%         │  strat {dd_oos:.1f}% vs B&H {bh_dd_oos:.1f}%")
            print(f"  {'':─<44}─┼─{'':─<43}")

        # Signal quality
        print(f"  Green % of time:  {e['green_pct']:.0f}%                               │  {o['green_pct']:.0f}%")
        print(f"  Flips per year:   {e['flips_per_year']:.0f}                                │  {o['flips_per_year']:.0f}")
        print(f"  Avg regime:       {e['avg_duration']:.0f} days                            │  —")
        print()

    # Check parameter stability of top result
    top = results[0]
    tp = top.params
    print(f"{'':─<120}")
    print(f"  PARAMETER STABILITY CHECK (neighbors of #1)")
    print(f"{'':─<120}")

    neighbors = [r for r in results if (
        abs(r.params["lookback"] - tp["lookback"]) <= 63 and
        abs(r.params["smoothing"] - tp["smoothing"]) <= 10 and
        r.params["components"] == tp["components"]
    )]

    if len(neighbors) >= 3:
        scores = [r.score for r in neighbors]
        print(f"  {len(neighbors)} nearby parameter sets, scores: {min(scores):.1f} to {max(scores):.1f}")
        print(f"  Top score: {top.score:.1f} — {'STABLE (plateau)' if (max(scores) - min(scores)) < top.score * 0.3 else 'FRAGILE (isolated peak)'}")
    else:
        print(f"  Only {len(neighbors)} neighbors found — limited stability check")

    print()

    return results


# ============================================================================
# GROWTH IMPULSES INDEX OPTIMIZER
# ============================================================================

def optimize_gii(data: pd.DataFrame, target: str = "spx"):
    """
    Grid search over GII parameters.
    The GII has fast + slow ROC composites. The regime signal can be:
      - fast > 0 (responsive)
      - both > 0 (conservative)
    """
    from build import calc_growth_impulse, zscore as bz, roc as broc, chg as bchg, ema as bema, clip_series

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    fast_rocs = [21, 42, 63, 84]
    slow_rocs = [126, 189, 252, 378]
    z_lens = [252, 378, 504]
    ema_lens = [1, 5, 10, 21]
    thresholds = [0, 0.2]
    signal_modes = ["fast", "slow", "avg", "both"]  # avg = mean of fast+slow

    total = len(fast_rocs) * len(slow_rocs) * len(z_lens) * len(ema_lens) * len(thresholds) * len(signal_modes)
    print(f"  Grid: {total} combinations\n")

    # Precompute component series
    components = {}
    if "HYG" in data: components["HYG"] = data["HYG"]
    if "BAMLH0A0HYM2" in data: components["BAML_INV"] = -data["BAMLH0A0HYM2"]
    if "XLY" in data and "XLP" in data: components["XLY_XLP"] = data["XLY"] / data["XLP"].replace(0, np.nan)
    if "XLI" in data and "XLU" in data: components["XLI_XLU"] = data["XLI"] / data["XLU"].replace(0, np.nan)
    if "SPHB" in data and "SPLV" in data: components["SPHB_SPLV"] = data["SPHB"] / data["SPLV"].replace(0, np.nan)
    if "HG=F" in data: components["COPPER"] = data["HG=F"]
    if "^VIX" in data: components["VIX_INV"] = -data["^VIX"]
    if "DGS10" in data and "DGS2" in data: components["YC"] = data["DGS10"] - data["DGS2"]
    if "WEI" in data: components["WEI"] = data["WEI"]

    change_components = {"YC", "WEI", "BAML_INV", "VIX_INV"}

    results = []
    tested = 0

    for fast_roc in fast_rocs:
        for slow_roc in slow_rocs:
            if fast_roc >= slow_roc:
                continue
            for z_len in z_lens:
                for ema_len in ema_lens:
                    # Precompute composites for this param set
                    fast_zs, slow_zs = [], []
                    for name, series in components.items():
                        if name in change_components:
                            sf = bchg(series, fast_roc)
                            ss = bchg(series, slow_roc)
                        else:
                            sf = broc(series, fast_roc)
                            ss = broc(series, slow_roc)
                        fast_zs.append(clip_series(bz(sf, z_len), 3.0))
                        slow_zs.append(clip_series(bz(ss, z_len), 3.0))

                    gii_fast_raw = pd.concat(fast_zs, axis=1).mean(axis=1, skipna=True)
                    gii_slow_raw = pd.concat(slow_zs, axis=1).mean(axis=1, skipna=True)
                    gii_fast = bema(gii_fast_raw, ema_len) if ema_len > 1 else gii_fast_raw
                    gii_slow = bema(gii_slow_raw, ema_len) if ema_len > 1 else gii_slow_raw

                    for threshold in thresholds:
                        for mode in signal_modes:
                            tested += 1

                            if mode == "fast":
                                signal = gii_fast.copy()
                            elif mode == "slow":
                                signal = gii_slow.copy()
                            elif mode == "avg":
                                signal = (gii_fast + gii_slow) / 2
                            else:
                                # Both must be positive for green
                                signal = pd.Series(np.where(
                                    (gii_fast > threshold) & (gii_slow > threshold), 1.0,
                                    np.where((gii_fast < -threshold) & (gii_slow < -threshold), -1.0, 0.0)
                                ), index=gii_fast.index)
                                signal = signal.replace(0.0, -0.01)

                            is_eval = evaluate_signal(signal.iloc[:split_idx],
                                                     {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                                     green_above=True)
                            if is_eval is None:
                                continue

                            oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                                      {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                                      green_above=True)
                            if oos_eval is None:
                                continue

                            t = target
                            spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                            alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
                            oos_alpha_t = oos_eval[f"strat_{t}_ann"] - oos_eval[f"bh_{t}_ann"]
                            flip_penalty = max(0, is_eval["flips_per_year"] - 15) * 2
                            gp = is_eval["green_pct"]
                            green_penalty = 50 if gp < 30 else abs(gp - 55) * 0.5

                            score = (
                                spread_t * 0.3 +
                                alpha_t * 0.3 +
                                oos_alpha_t * 0.3 +  # reward OOS alpha
                                is_eval[f"green_sharpe_{t}"] * 8 +
                                -green_penalty +
                                -flip_penalty
                            )

                            results.append(BacktestResult(
                                params={"fast_roc": fast_roc, "slow_roc": slow_roc, "z_len": z_len,
                                        "ema": ema_len, "threshold": threshold, "mode": mode},
                                is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
                            ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "GII")
    return results


# ============================================================================
# SECTOR BREADTH OPTIMIZER
# ============================================================================

def optimize_breadth(data: pd.DataFrame, target: str = "spx"):
    """Grid search over Sector Breadth parameters."""
    tickers = ["SMH", "IWM", "IYT", "IBB", "XHB", "KBE", "XRT", "SLX"]

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    lookbacks = [63, 126, 189, 252, 378, 504]
    smoothings = [1, 5, 10, 21]
    thresholds = [0, 0.1, 0.2, 0.3]

    # Component subsets: all 8, and drop each one
    component_sets = [tickers]
    for drop in tickers:
        component_sets.append([t for t in tickers if t != drop])

    total = len(lookbacks) * len(smoothings) * len(thresholds) * len(component_sets)
    print(f"  Grid: {total} combinations\n")

    results = []
    tested = 0

    for lookback in lookbacks:
        for smooth in smoothings:
            for threshold in thresholds:
                for comp_set in component_sets:
                    tested += 1

                    zscores_list = []
                    for t in comp_set:
                        if t in data:
                            zscores_list.append(zscore(data[t], lookback))

                    if not zscores_list:
                        continue

                    composite = pd.concat(zscores_list, axis=1).mean(axis=1, skipna=True)
                    if smooth > 1:
                        composite = ema(composite, smooth)

                    signal = composite

                    is_eval = evaluate_signal(signal.iloc[:split_idx],
                                             {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                             green_above=True)
                    if is_eval is None:
                        continue

                    oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                              {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                              green_above=True)
                    if oos_eval is None:
                        continue

                    t = target
                    spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                    alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
                    flip_penalty = max(0, is_eval["flips_per_year"] - 10) * 2

                    score = (
                        spread_t * 0.4 +
                        alpha_t * 0.3 +
                        is_eval[f"green_sharpe_{t}"] * 10 +
                        -abs(is_eval["green_pct"] - 60) * 0.5 +
                        -flip_penalty
                    )

                    dropped = set(tickers) - set(comp_set)
                    results.append(BacktestResult(
                        params={"lookback": lookback, "smoothing": smooth, "threshold": threshold,
                                "components": comp_set, "dropped": list(dropped) if dropped else None},
                        is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
                    ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "Sector Breadth")
    return results


# ============================================================================
# BDI OPTIMIZER
# ============================================================================

def optimize_bdi(data: pd.DataFrame, target: str = "spx"):
    """Grid search over BDI (seasonally adjusted) parameters."""
    if "BDRY" not in data:
        print("  BDRY not in data — skipping BDI optimization")
        return []

    bdry = data["BDRY"]

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    year_lags = [63, 126, 189, 252]
    baseline_years = [2, 3, 4, 5]
    z_lens = [126, 189, 252, 378]
    smoothings = [1, 5, 10, 21]
    thresholds = [0, 0.2, 0.5]

    total = len(year_lags) * len(baseline_years) * len(z_lens) * len(smoothings) * len(thresholds)
    print(f"  Grid: {total} combinations\n")

    results = []
    tested = 0

    # Also test raw z-score (no seasonal adjustment) — just BDRY ROC z-scored
    roc_lens = [42, 63, 126, 189, 252]
    raw_sources = []
    for rl in roc_lens:
        raw_sources.append(("roc", rl, bdry.pct_change(rl) * 100))

    # Seasonal-adjusted sources
    sa_sources = []
    for lag in year_lags:
        for n_years in baseline_years:
            baseline = pd.Series(0.0, index=bdry.index)
            count = pd.Series(0, index=bdry.index)
            for yr in range(1, n_years + 1):
                shifted = bdry.shift(lag * yr)
                valid = shifted > 0
                baseline += shifted.where(valid, 0)
                count += valid.astype(int)
            baseline = baseline / count.replace(0, np.nan)
            pct_vs = (bdry / baseline.replace(0, np.nan)) - 1.0
            sa_sources.append(("sa", f"lag{lag}_yr{n_years}", pct_vs))

    all_sources = raw_sources + sa_sources
    total = len(all_sources) * len(z_lens) * len(smoothings) * len(thresholds)
    print(f"  Grid: {total} combinations (incl. raw ROC + seasonal adj)\n")

    for src_type, src_label, src_series in all_sources:
        for z_len in z_lens:
            z = zscore(src_series, z_len)

            for smooth in smoothings:
                signal = ema(z, smooth) if smooth > 1 else z

                for threshold in thresholds:
                    tested += 1

                    is_eval = evaluate_signal(signal.iloc[:split_idx],
                                             {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                             green_above=True)
                    if is_eval is None:
                        continue

                    oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                              {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                              green_above=True)
                    if oos_eval is None:
                        continue

                    t = target
                    spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                    alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
                    oos_alpha_t = oos_eval[f"strat_{t}_ann"] - oos_eval[f"bh_{t}_ann"]
                    flip_penalty = max(0, is_eval["flips_per_year"] - 10) * 2
                    gp = is_eval["green_pct"]
                    green_penalty = 50 if gp < 30 else abs(gp - 55) * 0.5

                    score = (
                        spread_t * 0.3 +
                        alpha_t * 0.3 +
                        oos_alpha_t * 0.3 +
                        is_eval[f"green_sharpe_{t}"] * 8 +
                        -green_penalty +
                        -flip_penalty
                    )

                    results.append(BacktestResult(
                        params={"source": src_type, "label": src_label, "z_len": z_len,
                                "smoothing": smooth, "threshold": threshold},
                        is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
                    ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "BDI")
    return results


# ============================================================================
# COMPOSITE INDEX OPTIMIZER
# ============================================================================

def optimize_composite(data: pd.DataFrame, target: str = "spx"):
    """
    Test different ways to combine the 3 working indicators into one signal.
    Uses the already-optimized parameters for each individual indicator.
    """
    from build import (calc_growth_impulse, calc_financial_conditions,
                       calc_sector_breadth)

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    # Compute the 3 indicators with optimized params
    print("  Computing individual indicators...", flush=True)
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)

    # Normalize signals to +1 (green) / -1 (red) binary
    gii_binary = (gii["fast"] > 0).astype(float) * 2 - 1       # fast > 0 = green
    fincon_binary = (fincon["composite"] < 0).astype(float) * 2 - 1  # below 0 = green (loose)
    breadth_binary = (breadth["composite"] > 0).astype(float) * 2 - 1  # above 0 = green

    # Also get continuous signals (for weighted average)
    gii_cont = gii["fast"]
    fincon_cont = -fincon["composite"]  # flip so positive = green
    breadth_cont = breadth["composite"]

    # Align all to common index
    signals = pd.DataFrame({
        "gii_b": gii_binary,
        "fincon_b": fincon_binary,
        "breadth_b": breadth_binary,
        "gii_c": gii_cont,
        "fincon_c": fincon_cont,
        "breadth_c": breadth_cont,
    }).dropna()

    print(f"  Aligned signals: {len(signals)} rows\n")

    # Combination methods to test
    methods = []

    # 1. Majority vote: green when 2+ of 3 are green
    vote = signals[["gii_b", "fincon_b", "breadth_b"]].sum(axis=1)
    methods.append(("Majority vote (2 of 3)", vote))  # > 0 means 2+ green

    # 2. Unanimous: all 3 must be green
    unanimous = ((signals["gii_b"] > 0) & (signals["fincon_b"] > 0) & (signals["breadth_b"] > 0)).astype(float) * 2 - 1
    methods.append(("Unanimous (3 of 3)", unanimous))

    # 3. Equal-weight continuous average
    eq_avg = (signals["gii_c"] + signals["fincon_c"] + signals["breadth_c"]) / 3
    methods.append(("Equal-weight average", eq_avg))

    # 4. Alpha-weighted average (weight by OOS alpha: GII 7.6, Breadth 7.3, FinCon 5.8)
    w_gii, w_breadth, w_fincon = 7.6, 7.3, 5.8
    w_total = w_gii + w_breadth + w_fincon
    alpha_avg = (signals["gii_c"] * w_gii + signals["breadth_c"] * w_breadth + signals["fincon_c"] * w_fincon) / w_total
    methods.append(("Alpha-weighted average", alpha_avg))

    # 5. FinCon as gate + Breadth/GII average
    # Only green when FinCon is green AND avg of GII+Breadth is green
    fast_avg = (signals["gii_c"] + signals["breadth_c"]) / 2
    gated = fast_avg.copy()
    gated[signals["fincon_b"] < 0] = -abs(gated[signals["fincon_b"] < 0])  # force red when FinCon is red
    methods.append(("FinCon gate + GII/Breadth avg", gated))

    # 6-8. EMA smoothed versions of the best methods
    for span in [5, 10]:
        smoothed = ema(eq_avg, span)
        methods.append((f"Equal-weight avg, EMA {span}", smoothed))
        smoothed_alpha = ema(alpha_avg, span)
        methods.append((f"Alpha-weighted avg, EMA {span}", smoothed_alpha))

    # 9. At least 1 of 3 green (most permissive)
    any_green = ((signals["gii_b"] > 0) | (signals["fincon_b"] > 0) | (signals["breadth_b"] > 0)).astype(float) * 2 - 1
    methods.append(("Any green (1 of 3)", any_green))

    results = []
    tested = 0

    for name, signal in methods:
        tested += 1

        is_eval = evaluate_signal(signal.iloc[:split_idx],
                                 {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                 green_above=True)
        if is_eval is None:
            continue

        oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                  {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                  green_above=True)
        if oos_eval is None:
            continue

        t = target
        spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
        alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
        oos_alpha_t = oos_eval[f"strat_{t}_ann"] - oos_eval[f"bh_{t}_ann"]
        flip_penalty = max(0, is_eval["flips_per_year"] - 15) * 2
        gp = is_eval["green_pct"]
        green_penalty = 50 if gp < 30 else abs(gp - 55) * 0.5

        score = (
            spread_t * 0.3 +
            alpha_t * 0.3 +
            oos_alpha_t * 0.3 +
            is_eval[f"green_sharpe_{t}"] * 8 +
            -green_penalty +
            -flip_penalty
        )

        results.append(BacktestResult(
            params={"method": name},
            is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
        ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "Composite")
    return results


# ============================================================================
# LIQUIDITY OPTIMIZER
# ============================================================================

def optimize_liquidity(data: pd.DataFrame, target: str = "spx"):
    """
    Grid search over liquidity indicator parameters.
    Tests: net liquidity ROC z-score, level z-score, and combinations.
    """
    from build import zscore as bz, roc as broc, ema as bema

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    has_all = all(col in data for col in ["WALCL", "WTREGEN", "RRPONTSYD"])
    if not has_all:
        print("  Missing liquidity data — skipping")
        return []

    net_liq = data["WALCL"] - data["WTREGEN"] - data["RRPONTSYD"]

    roc_lens = [21, 42, 63, 126, 189, 252]
    z_lookbacks = [126, 189, 252, 378, 504]
    smoothings = [1, 5, 10, 21]
    signal_types = ["roc", "level", "avg"]  # ROC z-score, level z-score, average of both

    total = len(roc_lens) * len(z_lookbacks) * len(smoothings) * len(signal_types)
    print(f"  Grid: {total} combinations\n")

    results = []
    tested = 0

    for roc_len in roc_lens:
        net_roc = broc(net_liq, roc_len)

        for z_lb in z_lookbacks:
            z_roc = bz(net_roc, z_lb)
            z_level = bz(net_liq, z_lb)

            for smooth in smoothings:
                for sig_type in signal_types:
                    tested += 1

                    if sig_type == "roc":
                        raw = z_roc
                    elif sig_type == "level":
                        raw = z_level
                    else:
                        raw = (z_roc + z_level) / 2

                    signal = bema(raw, smooth) if smooth > 1 else raw

                    is_eval = evaluate_signal(signal.iloc[:split_idx],
                                             {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                             green_above=True)
                    if is_eval is None:
                        continue

                    oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                              {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                              green_above=True)
                    if oos_eval is None:
                        continue

                    t = target
                    spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                    alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
                    oos_alpha_t = oos_eval[f"strat_{t}_ann"] - oos_eval[f"bh_{t}_ann"]
                    flip_penalty = max(0, is_eval["flips_per_year"] - 15) * 2
                    gp = is_eval["green_pct"]
                    green_penalty = 50 if gp < 30 else abs(gp - 55) * 0.5

                    score = (
                        spread_t * 0.3 +
                        alpha_t * 0.3 +
                        oos_alpha_t * 0.3 +
                        is_eval[f"green_sharpe_{t}"] * 8 +
                        -green_penalty +
                        -flip_penalty
                    )

                    results.append(BacktestResult(
                        params={"roc_len": roc_len, "z_lookback": z_lb,
                                "smoothing": smooth, "signal": sig_type},
                        is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
                    ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "Liquidity")
    return results


# ============================================================================
# BUSINESS CYCLE INDICATORS BACKTEST
# ============================================================================

def optimize_gei(data: pd.DataFrame, target: str = "spx"):
    """
    Backtest the Global Economy Index with different lookbacks and smoothing.
    GEI is weekly-calibrated but we compute on daily data.
    """
    from build import zscore as bz, ema as bema

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    # Build GEI components
    components = {}
    if "BDRY" in data: components["BDI"] = data["BDRY"]
    if "DTWEXBGS" in data: components["USD_INV"] = 1.0 / data["DTWEXBGS"].replace(0, np.nan)
    if "CBON" in data: components["CN10Y"] = 1.0 / data["CBON"].replace(0, np.nan)
    if "^TNX" in data: components["US10Y"] = data["^TNX"]
    if "HG=F" in data and "GC=F" in data:
        components["CU_GOLD"] = data["HG=F"] / data["GC=F"].replace(0, np.nan)
    if "DBC" in data: components["DBC"] = data["DBC"]

    lookbacks = [126, 189, 252, 378, 504]
    smoothings = [1, 5, 10, 21, 42]
    thresholds = [0, 0.2, 0.5]

    total = len(lookbacks) * len(smoothings) * len(thresholds)
    print(f"  Grid: {total} combinations\n")

    results = []
    tested = 0

    for lookback in lookbacks:
        zscores_list = []
        for name, series in components.items():
            zscores_list.append(bz(series, lookback))
        # USD counted twice (faithful to original)
        if "USD_INV" in components:
            zscores_list.append(bz(components["USD_INV"], lookback))

        raw_composite = pd.concat(zscores_list, axis=1).mean(axis=1, skipna=True)

        for smooth in smoothings:
            signal = bema(raw_composite, smooth) if smooth > 1 else raw_composite

            for threshold in thresholds:
                tested += 1

                is_eval = evaluate_signal(signal.iloc[:split_idx],
                                         {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                         green_above=True)
                if is_eval is None:
                    continue

                oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                          {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                          green_above=True)
                if oos_eval is None:
                    continue

                t = target
                spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
                oos_alpha_t = oos_eval[f"strat_{t}_ann"] - oos_eval[f"bh_{t}_ann"]
                flip_penalty = max(0, is_eval["flips_per_year"] - 10) * 2
                gp = is_eval["green_pct"]
                green_penalty = 50 if gp < 30 else abs(gp - 55) * 0.5

                score = (
                    spread_t * 0.3 +
                    alpha_t * 0.3 +
                    oos_alpha_t * 0.3 +
                    is_eval[f"green_sharpe_{t}"] * 8 +
                    -green_penalty +
                    -flip_penalty
                )

                results.append(BacktestResult(
                    params={"lookback": lookback, "smoothing": smooth, "threshold": threshold},
                    is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
                ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "GEI (Global Economy)")
    return results


def optimize_mktcycle(data: pd.DataFrame, target: str = "spx"):
    """
    Backtest the Market-Derived Business Cycle Index with different lookbacks and smoothing.
    """
    from build import zscore as bz, ema as bema

    asset_rets = {
        "spx": data["^GSPC"].pct_change(),
        "btc": data["BTC-USD"].pct_change(),
        "iwm": data["IWM"].pct_change(),
    }

    spx = data["^GSPC"] if "^GSPC" in data else None
    if spx is None:
        print("  No SPX data — skipping")
        return []

    n = len(data)
    split_idx = int(n * 0.7)
    split_date = data.index[split_idx]

    print(f"  Data: {data.index[0].date()} to {data.index[-1].date()} ({n} rows)")
    print(f"  In-sample:  {data.index[0].date()} to {split_date.date()}")
    print(f"  Out-of-sample: {split_date.date()} to {data.index[-1].date()}")

    # Build components (all relative to SPX)
    base_components = {}

    industrials = ["UPS", "FDX", "CAT", "HON", "DOV", "FAST"]
    available = [t for t in industrials if t in data]
    if available:
        basket = sum(data[t] for t in available)
        base_components["Industrial"] = basket / spx.replace(0, np.nan)

    if "IWC" in data:
        base_components["IWC_SPX"] = data["IWC"] / spx.replace(0, np.nan)
    if "DJT" in data:
        base_components["DJT_SPX"] = data["DJT"] / spx.replace(0, np.nan)
    if "IWM" in data:
        base_components["IWM_SPX"] = data["IWM"] / spx.replace(0, np.nan)

    lookbacks = [126, 252, 378, 504, 756]
    smoothings = [1, 5, 10, 21, 42]
    thresholds = [0, 0.2, 0.5]

    total = len(lookbacks) * len(smoothings) * len(thresholds)
    print(f"  Grid: {total} combinations\n")

    results = []
    tested = 0

    for lookback in lookbacks:
        zscores_list = []
        for name, series in base_components.items():
            zscores_list.append(bz(series, lookback))

        raw_composite = pd.concat(zscores_list, axis=1).mean(axis=1, skipna=True)

        for smooth in smoothings:
            signal = bema(raw_composite, smooth) if smooth > 1 else raw_composite

            for threshold in thresholds:
                tested += 1

                is_eval = evaluate_signal(signal.iloc[:split_idx],
                                         {k: v.iloc[:split_idx] for k, v in asset_rets.items()},
                                         green_above=True)
                if is_eval is None:
                    continue

                oos_eval = evaluate_signal(signal.iloc[split_idx:],
                                          {k: v.iloc[split_idx:] for k, v in asset_rets.items()},
                                          green_above=True)
                if oos_eval is None:
                    continue

                t = target
                spread_t = is_eval[f"green_ann_{t}"] - is_eval[f"red_ann_{t}"]
                alpha_t = is_eval[f"strat_{t}_ann"] - is_eval[f"bh_{t}_ann"]
                oos_alpha_t = oos_eval[f"strat_{t}_ann"] - oos_eval[f"bh_{t}_ann"]
                flip_penalty = max(0, is_eval["flips_per_year"] - 10) * 2
                gp = is_eval["green_pct"]
                green_penalty = 50 if gp < 30 else abs(gp - 55) * 0.5

                score = (
                    spread_t * 0.3 +
                    alpha_t * 0.3 +
                    oos_alpha_t * 0.3 +
                    is_eval[f"green_sharpe_{t}"] * 8 +
                    -green_penalty +
                    -flip_penalty
                )

                results.append(BacktestResult(
                    params={"lookback": lookback, "smoothing": smooth, "threshold": threshold},
                    is_eval=is_eval, oos_eval=oos_eval, score=round(score, 1),
                ))

    results.sort(key=lambda r: r.score, reverse=True)
    print_results(results, tested, "Market Cycle")
    return results


# ============================================================================
# SHARED RESULTS PRINTER
# ============================================================================

def print_results(results, tested, name):
    print(f"{'':─<120}")
    print(f"  TOP 3 PARAMETER SETS — {name} (out of {tested} tested)")
    print(f"{'':─<120}")

    for i, r in enumerate(results[:3]):
        p = r.params
        e = r.is_eval
        o = r.oos_eval

        # Format params
        param_str = ", ".join(f"{k}={v}" for k, v in p.items()
                             if k != "components" and k != "dropped" and v is not None)
        if "components" in p:
            dropped = p.get("dropped")
            if dropped:
                param_str += f", dropped={'+'.join(dropped)}"
            else:
                param_str += ", all components"
        print(f"\n  #{i+1}  Score: {r.score}")
        print(f"  Params: {param_str}")

        print(f"\n  {'':─<90}")
        print(f"  {'IN-SAMPLE':^44} │ {'OUT-OF-SAMPLE':^43}")
        print(f"  {'':─<44}─┼─{'':─<43}")

        for asset, label in [("spx", "SPX"), ("iwm", "IWM"), ("btc", "BTC")]:
            bh_is = e.get(f"bh_{asset}_ann", 0)
            bh_is_t = e.get(f"bh_{asset}_total", 0)
            st_is = e.get(f"strat_{asset}_ann", 0)
            st_is_t = e.get(f"strat_{asset}_total", 0)
            bh_oos = o.get(f"bh_{asset}_ann", 0)
            bh_oos_t = o.get(f"bh_{asset}_total", 0)
            st_oos = o.get(f"strat_{asset}_ann", 0)
            st_oos_t = o.get(f"strat_{asset}_total", 0)
            alpha_is = st_is - bh_is
            alpha_oos = st_oos - bh_oos

            print(f"  {label} B&H:  {bh_is:+6.1f}%/yr ({bh_is_t:+.0f}%)  Signal: {st_is:+6.1f}%/yr ({st_is_t:+.0f}%)  │  B&H: {bh_oos:+6.1f}%/yr  Signal: {st_oos:+6.1f}%/yr  Alpha: {alpha_oos:+.1f}%")
            dd_is = e.get(f"strat_maxdd_{asset}", 0)
            bh_dd_is = e.get(f"bh_maxdd_{asset}", 0)
            dd_oos = o.get(f"strat_maxdd_{asset}", 0)
            bh_dd_oos = o.get(f"bh_maxdd_{asset}", 0)
            print(f"         MaxDD: strat {dd_is:.1f}% vs B&H {bh_dd_is:.1f}%              │  MaxDD: strat {dd_oos:.1f}% vs B&H {bh_dd_oos:.1f}%")

        print(f"  {'':─<44}─┼─{'':─<43}")
        print(f"  Green {e['green_pct']:.0f}%, {e['flips_per_year']:.0f} flips/yr, {e['avg_duration']:.0f}d avg    │  Green {o['green_pct']:.0f}%, {o['flips_per_year']:.0f} flips/yr")
        print()


# ============================================================================
# MAIN
# ============================================================================

def main():
    if not DATA_CACHE.exists():
        print("No cached data. Run build.py first.")
        sys.exit(1)

    data = pd.read_pickle(DATA_CACHE)
    print(f"Loaded {len(data)} rows of data\n")

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    indicator = args[0] if args else "fincon"
    target = "btc" if "--btc" in flags else "iwm" if "--iwm" in flags else "spx"

    indicators = {
        "fincon": ("Financial Conditions Composite", optimize_fincon),
        "gii": ("Growth Impulses Index", optimize_gii),
        "breadth": ("US Equity Sector Breadth", optimize_breadth),
        "bdi": ("Baltic Dry Index (seasonal adj)", optimize_bdi),
        "liquidity": ("Liquidity (Net Fed Liquidity)", optimize_liquidity),
        "composite": ("Composite (GII + FinCon + Breadth)", optimize_composite),
        "gei": ("Global Economy Index", optimize_gei),
        "mktcycle": ("Market-Derived Business Cycle", optimize_mktcycle),
        "cycle": None,
        "all": None,
    }

    if indicator == "all":
        run_list = ["gii", "breadth", "bdi"]
    elif indicator == "cycle":
        run_list = ["gei", "mktcycle"]
    elif indicator in indicators:
        run_list = [indicator]
    else:
        print(f"Unknown indicator: {indicator}")
        print(f"Available: {', '.join(indicators.keys())}")
        sys.exit(1)

    for ind in run_list:
        name, func = indicators[ind]
        print("=" * 120)
        print(f"  OPTIMIZING: {name} (target: {target.upper()})")
        print("=" * 120)
        print()
        func(data, target=target)
        print("\n")


if __name__ == "__main__":
    main()
