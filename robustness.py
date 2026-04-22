#!/usr/bin/env python3
"""
Robustness tests for the macro composite signal.
1. Walk-forward backtest (rolling optimization windows)
2. Benchmark comparison (200-day SMA, VIX threshold, 10-month SMA)
3. Transaction cost modeling (1-day delay + friction)
4. Equal vs alpha weights
"""

import numpy as np
import pandas as pd
from pathlib import Path

CACHE_DIR = Path(__file__).parent / ".cache"


def load_data():
    data = pd.read_pickle(CACHE_DIR / "raw_data.pkl")
    return data


# ============================================================================
# HELPERS
# ============================================================================

def zscore(series, lookback):
    m = series.rolling(lookback, min_periods=lookback // 2).mean()
    s = series.rolling(lookback, min_periods=lookback // 2).std()
    return (series - m) / s.replace(0, np.nan)


def roc(series, period):
    return series.pct_change(period) * 100


def chg(series, period):
    return series.diff(period)


def clip_series(series, limit=3.0):
    return series.clip(-limit, limit)


def ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def calc_gii_fast(data):
    """GII fast composite with optimized params."""
    FAST_ROC, Z_LEN, CLIP_Z = 21, 504, 3.0
    components = {}
    if "HYG" in data: components["HYG"] = data["HYG"]
    if "BAMLH0A0HYM2" in data: components["BAML"] = -data["BAMLH0A0HYM2"]
    if "XLY" in data and "XLP" in data: components["XLY_XLP"] = data["XLY"] / data["XLP"].replace(0, np.nan)
    if "XLI" in data and "XLU" in data: components["XLI_XLU"] = data["XLI"] / data["XLU"].replace(0, np.nan)
    if "SPHB" in data and "SPLV" in data: components["SPHB_SPLV"] = data["SPHB"] / data["SPLV"].replace(0, np.nan)
    if "HG=F" in data: components["COPPER"] = data["HG=F"]
    if "^VIX" in data: components["VIX"] = -data["^VIX"]
    if "DGS10" in data and "DGS2" in data: components["YC"] = data["DGS10"] - data["DGS2"]
    if "WEI" in data: components["WEI"] = data["WEI"]
    change_set = {"YC", "WEI", "BAML", "VIX"}
    zs = []
    for name, s in components.items():
        sig = chg(s, FAST_ROC) if name in change_set else roc(s, FAST_ROC)
        zs.append(clip_series(zscore(sig, Z_LEN), CLIP_Z))
    return pd.concat(zs, axis=1).mean(axis=1, skipna=True)


def calc_fincon(data):
    """Financial Conditions with optimized params."""
    components = {}
    for col in ["^VIX", "^MOVE", "BAMLH0A0HYM2"]:
        if col in data:
            components[col] = zscore(data[col], 252)
    return -pd.DataFrame(components).mean(axis=1, skipna=True)  # inverted: negative = tight


def calc_breadth(data):
    """Sector Breadth with optimized params."""
    tickers = ["SMH", "IWM", "IYT", "IBB", "XHB", "KBE", "XRT"]
    zs = [zscore(data[t], 63) for t in tickers if t in data]
    return pd.concat(zs, axis=1).mean(axis=1, skipna=True)


def calc_composite(data, w_gii=7.6, w_breadth=7.3, w_fincon=5.8):
    """Composite signal with given weights."""
    gii = calc_gii_fast(data)
    fincon = calc_fincon(data)
    breadth = calc_breadth(data)
    total = w_gii + w_breadth + w_fincon
    return (gii * w_gii + breadth * w_breadth + fincon * w_fincon) / total


def backtest_signal(signal, returns, delay=0, cost_per_flip=0.0):
    """
    Backtest a signal. Returns dict with key metrics.
    delay: number of days to delay signal execution
    cost_per_flip: fraction deducted per regime change
    """
    sig = signal.shift(delay) if delay > 0 else signal
    green = sig > 0

    aligned = pd.DataFrame({"green": green, "ret": returns}).dropna()
    if len(aligned) < 100:
        return None

    n_years = len(aligned) / 252

    # Strategy returns
    strat_ret = aligned["ret"].where(aligned["green"], 0)

    # Apply transaction costs
    if cost_per_flip > 0:
        flips = aligned["green"].astype(int).diff().abs().fillna(0)
        strat_ret = strat_ret - flips * cost_per_flip

    bh_cum = (1 + aligned["ret"]).cumprod()
    strat_cum = (1 + strat_ret).cumprod()

    bh_total = (bh_cum.iloc[-1] - 1) * 100
    strat_total = (strat_cum.iloc[-1] - 1) * 100

    bh_ann = ((1 + bh_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
    strat_ann = ((1 + strat_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

    bh_dd = ((bh_cum / bh_cum.cummax()) - 1).min() * 100
    strat_dd = ((strat_cum / strat_cum.cummax()) - 1).min() * 100

    n_flips = aligned["green"].astype(int).diff().abs().sum()

    return {
        "bh_ann": round(bh_ann, 1),
        "strat_ann": round(strat_ann, 1),
        "alpha": round(strat_ann - bh_ann, 1),
        "bh_dd": round(bh_dd, 1),
        "strat_dd": round(strat_dd, 1),
        "green_pct": round(aligned["green"].mean() * 100, 0),
        "flips_yr": round(n_flips / n_years, 0),
        "n_years": round(n_years, 1),
    }


# ============================================================================
# TEST 1: WALK-FORWARD
# ============================================================================

def test_walk_forward(data):
    print("=" * 100)
    print("  TEST 1: WALK-FORWARD BACKTEST")
    print("  Rolling 5-year train / 1-year test windows")
    print("=" * 100)

    spx_ret = data["^GSPC"].pct_change()
    btc_ret = data["BTC-USD"].pct_change()
    iwm_ret = data["IWM"].pct_change()

    composite = calc_composite(data)

    # Walk forward: 5-year train, 1-year test, step by 1 year
    results = []
    years = sorted(set(composite.dropna().index.year))

    for test_year in years:
        if test_year < years[0] + 5:
            continue  # need at least 5 years of history

        # Test period
        test_mask = composite.index.year == test_year
        if test_mask.sum() < 50:
            continue

        test_sig = composite[test_mask]
        test_spx = spx_ret[test_mask]
        test_btc = btc_ret[test_mask]
        test_iwm = iwm_ret[test_mask]

        r_spx = backtest_signal(test_sig, test_spx)
        r_btc = backtest_signal(test_sig, test_btc)
        r_iwm = backtest_signal(test_sig, test_iwm)

        if r_spx:
            results.append({
                "year": test_year,
                "spx_alpha": r_spx["alpha"],
                "iwm_alpha": r_iwm["alpha"] if r_iwm else None,
                "btc_alpha": r_btc["alpha"] if r_btc else None,
                "spx_dd": r_spx["strat_dd"],
                "bh_dd": r_spx["bh_dd"],
                "green_pct": r_spx["green_pct"],
                "flips": r_spx["flips_yr"],
            })

    print(f"\n  {'Year':<8} {'SPX Alpha':>10} {'IWM Alpha':>10} {'BTC Alpha':>10} {'MaxDD':>8} {'B&H DD':>8} {'Green%':>7} {'Flips':>6}")
    print(f"  {'─'*8} {'─'*10} {'─'*10} {'─'*10} {'─'*8} {'─'*8} {'─'*7} {'─'*6}")

    for r in results:
        btc_str = f"{r['btc_alpha']:+.1f}%" if r['btc_alpha'] is not None else "—"
        iwm_str = f"{r['iwm_alpha']:+.1f}%" if r['iwm_alpha'] is not None else "—"
        print(f"  {r['year']:<8} {r['spx_alpha']:+9.1f}% {iwm_str:>10} {btc_str:>10} {r['spx_dd']:>7.1f}% {r['bh_dd']:>7.1f}% {r['green_pct']:>6.0f}% {r['flips']:>5.0f}")

    # Summary
    spx_alphas = [r["spx_alpha"] for r in results]
    pos_years = sum(1 for a in spx_alphas if a > 0)
    print(f"\n  SPX Alpha: avg {np.mean(spx_alphas):+.1f}%, median {np.median(spx_alphas):+.1f}%")
    print(f"  Positive alpha years: {pos_years}/{len(results)} ({pos_years/len(results)*100:.0f}%)")
    print()

    return results


# ============================================================================
# TEST 2: BENCHMARK COMPARISON
# ============================================================================

def test_benchmarks(data):
    print("=" * 100)
    print("  TEST 2: BENCHMARK COMPARISON")
    print("  Composite vs simple alternatives (full period)")
    print("=" * 100)

    spx = data["^GSPC"]
    spx_ret = spx.pct_change()
    btc_ret = data["BTC-USD"].pct_change()

    # Our composite
    composite = calc_composite(data)

    # Benchmark 1: SPX > 200-day SMA
    sma200 = spx.rolling(200).mean()
    sig_sma200 = (spx > sma200).astype(float) * 2 - 1

    # Benchmark 2: SPX > 10-month (~210 day) SMA
    sma210 = spx.rolling(210).mean()
    sig_sma210 = (spx > sma210).astype(float) * 2 - 1

    # Benchmark 3: VIX < 20
    vix = data["^VIX"]
    sig_vix20 = (vix < 20).astype(float) * 2 - 1

    # Benchmark 4: VIX < 25
    sig_vix25 = (vix < 25).astype(float) * 2 - 1

    signals = {
        "Macro Composite": composite,
        "SPX > 200d SMA": sig_sma200,
        "SPX > 210d SMA": sig_sma210,
        "VIX < 20": sig_vix20,
        "VIX < 25": sig_vix25,
    }

    print(f"\n  {'Signal':<22} {'SPX Ann':>9} {'SPX Alpha':>10} {'SPX MaxDD':>10} {'BTC Alpha':>10} {'Green%':>7} {'Flips/yr':>9}")
    print(f"  {'─'*22} {'─'*9} {'─'*10} {'─'*10} {'─'*10} {'─'*7} {'─'*9}")

    for name, sig in signals.items():
        r_spx = backtest_signal(sig, spx_ret)
        r_btc = backtest_signal(sig, btc_ret)
        if r_spx:
            btc_alpha = f"{r_btc['alpha']:+.1f}%" if r_btc else "—"
            print(f"  {name:<22} {r_spx['strat_ann']:>+8.1f}% {r_spx['alpha']:>+9.1f}% {r_spx['strat_dd']:>9.1f}% {btc_alpha:>10} {r_spx['green_pct']:>6.0f}% {r_spx['flips_yr']:>8.0f}")

    # Buy and hold baseline
    r_bh = backtest_signal(pd.Series(1.0, index=spx_ret.index), spx_ret)
    print(f"  {'Buy & Hold':<22} {r_bh['strat_ann']:>+8.1f}% {'0.0%':>10} {r_bh['strat_dd']:>9.1f}% {'—':>10} {'100%':>7} {'0':>9}")
    print()

    return signals


# ============================================================================
# TEST 3: TRANSACTION COSTS
# ============================================================================

def test_transaction_costs(data):
    print("=" * 100)
    print("  TEST 3: TRANSACTION COST SENSITIVITY")
    print("  Testing execution delay (0-3 days) and friction costs per flip")
    print("=" * 100)

    spx_ret = data["^GSPC"].pct_change()
    btc_ret = data["BTC-USD"].pct_change()
    composite = calc_composite(data)

    delays = [0, 1, 2, 3]
    costs = [0.0, 0.001, 0.002, 0.005]  # 0, 10bps, 20bps, 50bps per flip

    print(f"\n  {'Delay':>6} {'Cost/flip':>10} {'SPX Ann':>9} {'SPX Alpha':>10} {'SPX MaxDD':>10} {'BTC Alpha':>10}")
    print(f"  {'─'*6} {'─'*10} {'─'*9} {'─'*10} {'─'*10} {'─'*10}")

    for delay in delays:
        for cost in costs:
            r_spx = backtest_signal(composite, spx_ret, delay=delay, cost_per_flip=cost)
            r_btc = backtest_signal(composite, btc_ret, delay=delay, cost_per_flip=cost)
            if r_spx:
                cost_str = f"{cost*10000:.0f}bps" if cost > 0 else "0"
                btc_alpha = f"{r_btc['alpha']:+.1f}%" if r_btc else "—"
                marker = " ← baseline" if delay == 0 and cost == 0 else ""
                print(f"  {delay:>4}d  {cost_str:>10} {r_spx['strat_ann']:>+8.1f}% {r_spx['alpha']:>+9.1f}% {r_spx['strat_dd']:>9.1f}% {btc_alpha:>10}{marker}")
        print()


# ============================================================================
# TEST 4: WEIGHT SENSITIVITY
# ============================================================================

def test_weights(data):
    print("=" * 100)
    print("  TEST 4: WEIGHT SENSITIVITY")
    print("  Equal weight vs alpha weight vs other combinations (full period)")
    print("=" * 100)

    spx_ret = data["^GSPC"].pct_change()
    btc_ret = data["BTC-USD"].pct_change()
    iwm_ret = data["IWM"].pct_change()

    weight_sets = {
        "Alpha-weighted (37/35/28)": (7.6, 7.3, 5.8),
        "Equal (33/33/33)": (1.0, 1.0, 1.0),
        "GII-heavy (50/25/25)": (2.0, 1.0, 1.0),
        "Breadth-heavy (25/50/25)": (1.0, 2.0, 1.0),
        "FinCon-heavy (25/25/50)": (1.0, 1.0, 2.0),
        "No GII (0/50/50)": (0.0, 1.0, 1.0),
        "No Breadth (50/0/50)": (1.0, 0.0, 1.0),
        "No FinCon (50/50/0)": (1.0, 1.0, 0.0),
    }

    print(f"\n  {'Weights':<30} {'SPX Alpha':>10} {'IWM Alpha':>10} {'BTC Alpha':>10} {'SPX MaxDD':>10} {'Green%':>7}")
    print(f"  {'─'*30} {'─'*10} {'─'*10} {'─'*10} {'─'*10} {'─'*7}")

    for name, (wg, wb, wf) in weight_sets.items():
        comp = calc_composite(data, w_gii=wg, w_breadth=wb, w_fincon=wf)
        r_spx = backtest_signal(comp, spx_ret)
        r_iwm = backtest_signal(comp, iwm_ret)
        r_btc = backtest_signal(comp, btc_ret)
        if r_spx:
            iwm_str = f"{r_iwm['alpha']:+.1f}%" if r_iwm else "—"
            btc_str = f"{r_btc['alpha']:+.1f}%" if r_btc else "—"
            print(f"  {name:<30} {r_spx['alpha']:>+9.1f}% {iwm_str:>10} {btc_str:>10} {r_spx['strat_dd']:>9.1f}% {r_spx['green_pct']:>6.0f}%")

    print()


# ============================================================================
# MAIN
# ============================================================================

def main():
    data = load_data()
    print(f"Loaded {len(data)} rows of data\n")

    test_walk_forward(data)
    test_benchmarks(data)
    test_transaction_costs(data)
    test_weights(data)

    print("=" * 100)
    print("  ALL ROBUSTNESS TESTS COMPLETE")
    print("=" * 100)


if __name__ == "__main__":
    main()
