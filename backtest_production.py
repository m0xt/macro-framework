"""Comprehensive backtest of the production MRMI framework.

Produces every number used in docs/PRESENTATION.html so the slides can be updated
with accurate, current results. Uses the production-level signal:

    MMI    = equal-weighted (GII, Breadth, FinCon)
    Stress = min(1, max(0, -RE) × max(0, Inf_Dir))
    MRMI   = MMI + 1.0 × (1 - Stress) − 0.5

Strategy: invested when MRMI > 0, cash when MRMI < 0.

Reports:
  1. Headline backtest (IS / OOS, all 3 assets)
  2. Individual indicator standalone alpha (GII, Breadth, FinCon, MRMI)
  3. Walk-forward by calendar year
  4. Benchmark comparison (vs VIX-based, SMA, buy-and-hold)
  5. Transaction-cost & execution-delay sensitivity
  6. Weight-sensitivity (equal, alpha, GII-heavy, drop-one)

Run with:  .venv/bin/python backtest_production.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from build import (
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_macro_context,
    calc_sector_breadth,
    fetch_all_data,
)

# ── core backtest helpers ──────────────────────────────────────────────────

def backtest_signal(signal: pd.Series, ret: pd.Series,
                    delay: int = 0, cost_per_flip: float = 0.0) -> dict | None:
    """Backtest a binary signal (>0 = invested) on one asset's daily returns."""
    sig = signal.shift(delay) if delay > 0 else signal
    df = pd.DataFrame({"sig": sig, "ret": ret}).dropna()
    if len(df) < 100:
        return None

    invested = df["sig"] > 0
    n_years = len(df) / 252

    strat_ret = df["ret"].where(invested, 0.0)
    if cost_per_flip > 0:
        flips = invested.astype(int).diff().abs().fillna(0)
        strat_ret = strat_ret - flips * cost_per_flip

    bh_cum = (1 + df["ret"]).cumprod()
    strat_cum = (1 + strat_ret).cumprod()

    bh_total = (bh_cum.iloc[-1] - 1) * 100
    strat_total = (strat_cum.iloc[-1] - 1) * 100
    bh_ann = ((1 + bh_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0
    strat_ann = ((1 + strat_total / 100) ** (1 / n_years) - 1) * 100 if n_years > 0 else 0

    bh_dd = ((bh_cum / bh_cum.cummax()) - 1).min() * 100
    strat_dd = ((strat_cum / strat_cum.cummax()) - 1).min() * 100

    n_flips = invested.astype(int).diff().abs().sum()
    return {
        "bh_ann": float(bh_ann), "strat_ann": float(strat_ann),
        "alpha": float(strat_ann - bh_ann),
        "bh_dd": float(bh_dd), "strat_dd": float(strat_dd),
        "green_pct": float(invested.mean() * 100),
        "flips_yr": float(n_flips / n_years),
        "avg_dur": float(len(df) / max(n_flips, 1)) if n_flips else float(len(df)),
        "n_years": n_years,
    }


def production_mrmi(data: pd.DataFrame, w_gii=1.0, w_breadth=1.0, w_fincon=1.0,
                    buffer_size=1.0, threshold=0.5) -> tuple[pd.Series, pd.Series]:
    """Build production MRMI + the underlying MMI."""
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    macro_ctx = calc_macro_context(data)

    w_total = w_gii + w_breadth + w_fincon
    mmi = (gii["fast"] * w_gii + breadth["composite"] * w_breadth
           + fincon["composite"] * w_fincon) / w_total

    re = macro_ctx["real_economy_score"].reindex(mmi.index)
    inf = macro_ctx["inflation_dir_pp"].reindex(mmi.index)
    re_neg = (-re).clip(lower=0)
    inf_pos = inf.clip(lower=0)
    stress = (re_neg * inf_pos).clip(upper=1.0).fillna(0.0)
    macro_buffer = buffer_size * (1.0 - stress)
    mrmi = mmi + macro_buffer - threshold
    return mrmi, mmi


# ── reporters ──────────────────────────────────────────────────────────────

def fmt_pct(v: float, dec: int = 1) -> str:
    if v is None or np.isnan(v):
        return "—"
    return f"{v:+.{dec}f}%"


def print_headline(label: str, results: dict) -> None:
    print(f"\n  {label}")
    print(f"    {'asset':<8} {'B&H ann':>8} {'strat ann':>10} {'alpha':>8} {'B&H DD':>9} {'strat DD':>10} {'green%':>7}")
    print(f"    {'-'*8} {'-'*8} {'-'*10} {'-'*8} {'-'*9} {'-'*10} {'-'*7}")
    for asset in ("spx", "iwm", "btc"):
        r = results[asset]
        if r is None:
            continue
        print(f"    {asset.upper():<8} {fmt_pct(r['bh_ann']):>8} {fmt_pct(r['strat_ann']):>10} "
              f"{fmt_pct(r['alpha']):>8} {fmt_pct(r['bh_dd']):>9} {fmt_pct(r['strat_dd']):>10} "
              f"{r['green_pct']:>6.1f}%")
    if "spx" in results and results["spx"]:
        print(f"    flips/yr: {results['spx']['flips_yr']:.1f}   avg duration: {results['spx']['avg_dur']:.0f}d")


# ── tests ──────────────────────────────────────────────────────────────────

def test_headline(mrmi: pd.Series, asset_rets: dict, split_idx: int) -> dict:
    """Headline backtest: in-sample (first 70%) and out-of-sample (last 30%) numbers."""
    print("\n" + "=" * 90)
    print("TEST 1 · HEADLINE BACKTEST (production MRMI)")
    print("=" * 90)

    is_results = {a: backtest_signal(mrmi.iloc[:split_idx], r.iloc[:split_idx])
                  for a, r in asset_rets.items()}
    oos_results = {a: backtest_signal(mrmi.iloc[split_idx:], r.iloc[split_idx:])
                   for a, r in asset_rets.items()}
    full_results = {a: backtest_signal(mrmi, r) for a, r in asset_rets.items()}

    print_headline("In-sample (first 70%)", is_results)
    print_headline("Out-of-sample (last 30%)", oos_results)
    print_headline("Full sample", full_results)
    return {"is": is_results, "oos": oos_results, "full": full_results}


def test_individual_indicators(data: pd.DataFrame, asset_rets: dict, split_idx: int) -> dict:
    """Each indicator on its own (binary > 0), then MRMI for comparison."""
    print("\n" + "=" * 90)
    print("TEST 2 · INDIVIDUAL INDICATOR STANDALONE ALPHA (out-of-sample)")
    print("=" * 90)

    gii = calc_growth_impulse(data)["fast"]
    fincon_raw = calc_financial_conditions(data)["composite"]
    breadth = calc_sector_breadth(data)["composite"]
    mrmi, _ = production_mrmi(data)

    # FinCon is "loose = good" — but calc_composite uses it directly (positive = green).
    # Here we use the raw composite which has the same sign as in calc_composite (positive = good).
    indicators = {
        "GII":        gii,
        "Breadth":    breadth,
        "FinCon":     fincon_raw,
        "MMI (combo)": calc_composite(calc_growth_impulse(data),
                                       calc_financial_conditions(data),
                                       calc_sector_breadth(data)),
        "MRMI (prod)": mrmi,
    }

    print(f"\n    {'indicator':<14} {'SPX α':>8} {'IWM α':>8} {'BTC α':>8} {'green%':>8} {'flips/y':>8}")
    print(f"    {'-'*14} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
    out = {}
    for name, sig in indicators.items():
        oos_sig = sig.iloc[split_idx:]
        row = {}
        for asset in ("spx", "iwm", "btc"):
            r = backtest_signal(oos_sig, asset_rets[asset].iloc[split_idx:])
            row[asset] = r["alpha"] if r else None
        ref = backtest_signal(oos_sig, asset_rets["spx"].iloc[split_idx:])
        green = ref["green_pct"] if ref else None
        flips = ref["flips_yr"] if ref else None
        out[name] = {**row, "green_pct": green, "flips_yr": flips}
        print(f"    {name:<14} {fmt_pct(row['spx']):>8} {fmt_pct(row['iwm']):>8} "
              f"{fmt_pct(row['btc']):>8} {green:>7.1f}% {flips:>7.1f}")
    return out


def test_walk_forward(mrmi: pd.Series, asset_rets: dict) -> list:
    """Year-by-year alpha for production MRMI."""
    print("\n" + "=" * 90)
    print("TEST 3 · WALK-FORWARD (year-by-year, production MRMI)")
    print("=" * 90)
    print(f"\n    {'year':<6} {'SPX α':>8} {'IWM α':>8} {'BTC α':>8} {'SPX strat DD':>14} {'SPX B&H DD':>12}")
    print(f"    {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*14} {'-'*12}")

    rows = []
    years = sorted(set(mrmi.dropna().index.year))
    sums = {"spx": [], "iwm": [], "btc": [], "strat_dd": [], "bh_dd": []}
    for year in years:
        mask = mrmi.index.year == year
        if mask.sum() < 50:
            continue
        sig_y = mrmi[mask]
        rs = {a: backtest_signal(sig_y, asset_rets[a][mask]) for a in ("spx", "iwm", "btc")}
        if not all(rs.values()):
            continue
        rows.append({"year": year, **{f"{a}_alpha": rs[a]["alpha"] for a in ("spx", "iwm", "btc")},
                     "strat_dd": rs["spx"]["strat_dd"], "bh_dd": rs["spx"]["bh_dd"]})
        for a in ("spx", "iwm", "btc"):
            sums[a].append(rs[a]["alpha"])
        sums["strat_dd"].append(rs["spx"]["strat_dd"])
        sums["bh_dd"].append(rs["spx"]["bh_dd"])
        print(f"    {year:<6} {fmt_pct(rs['spx']['alpha']):>8} {fmt_pct(rs['iwm']['alpha']):>8} "
              f"{fmt_pct(rs['btc']['alpha']):>8} {fmt_pct(rs['spx']['strat_dd']):>13}  "
              f"{fmt_pct(rs['spx']['bh_dd']):>11}")
    if sums["spx"]:
        print(f"    {'avg':<6} {fmt_pct(np.mean(sums['spx'])):>8} {fmt_pct(np.mean(sums['iwm'])):>8} "
              f"{fmt_pct(np.mean(sums['btc'])):>8} {fmt_pct(np.mean(sums['strat_dd'])):>13}  "
              f"{fmt_pct(np.mean(sums['bh_dd'])):>11}")
    return rows


def test_benchmarks(data: pd.DataFrame, mrmi: pd.Series, asset_rets: dict) -> dict:
    """MRMI vs simple alternatives (full sample)."""
    print("\n" + "=" * 90)
    print("TEST 4 · BENCHMARK COMPARISON vs SIMPLE ALTERNATIVES (full sample)")
    print("=" * 90)

    spx = data["^GSPC"]
    vix = data["^VIX"]
    sma200 = spx.rolling(200).mean()

    benchmarks = {
        "MRMI (prod)":    mrmi,
        "VIX < 20":       (20 - vix),  # >0 when VIX<20
        "VIX < 25":       (25 - vix),
        "SPX > 200d SMA": (spx - sma200),  # >0 when above SMA
    }

    print(f"\n    {'strategy':<18} {'SPX ann':>9} {'SPX α':>8} {'SPX DD':>9} {'BTC α':>8} {'flips/y':>8} {'green%':>8}")
    print(f"    {'-'*18} {'-'*9} {'-'*8} {'-'*9} {'-'*8} {'-'*8} {'-'*8}")
    out = {}
    for name, sig in benchmarks.items():
        r_spx = backtest_signal(sig, asset_rets["spx"])
        r_btc = backtest_signal(sig, asset_rets["btc"])
        if r_spx:
            print(f"    {name:<18} {fmt_pct(r_spx['strat_ann']):>9} {fmt_pct(r_spx['alpha']):>8} "
                  f"{fmt_pct(r_spx['strat_dd']):>9} {fmt_pct(r_btc['alpha'] if r_btc else None):>8} "
                  f"{r_spx['flips_yr']:>7.1f} {r_spx['green_pct']:>7.1f}%")
            out[name] = {"spx_ann": r_spx["strat_ann"], "spx_alpha": r_spx["alpha"],
                          "spx_dd": r_spx["strat_dd"],
                          "btc_alpha": r_btc["alpha"] if r_btc else None,
                          "flips_yr": r_spx["flips_yr"], "green_pct": r_spx["green_pct"]}
    # Buy & hold reference
    bh_only = backtest_signal(pd.Series(1.0, index=mrmi.index), asset_rets["spx"])
    if bh_only:
        print(f"    {'Buy & Hold':<18} {fmt_pct(bh_only['strat_ann']):>9} {'0.0%':>8} "
              f"{fmt_pct(bh_only['strat_dd']):>9} {'—':>8} {0:>8} {'100.0%':>8}")
    return out


def test_transaction_costs(mrmi: pd.Series, spx_ret: pd.Series) -> dict:
    """Production MRMI alpha across delays and friction levels."""
    print("\n" + "=" * 90)
    print("TEST 5 · TRANSACTION COSTS & EXECUTION DELAY (SPX, full sample)")
    print("=" * 90)
    print(f"\n    {'delay':<8} {'cost/flip':>10} {'SPX α':>8}")
    print(f"    {'-'*8} {'-'*10} {'-'*8}")
    out = {}
    for delay in (0, 1, 5):
        for cost in (0.0, 0.0010, 0.0020, 0.0050):
            r = backtest_signal(mrmi, spx_ret, delay=delay, cost_per_flip=cost)
            if r:
                key = f"d{delay}_c{int(cost*10000)}bps"
                out[key] = r["alpha"]
                cost_label = f"{int(cost*10000)}bps" if cost else "0"
                print(f"    {delay:>3}d{'':<5} {cost_label:>10} {fmt_pct(r['alpha']):>8}")
    return out


def test_weights(data: pd.DataFrame, asset_rets: dict, split_idx: int) -> dict:
    """Weight-sensitivity grid (full sample)."""
    print("\n" + "=" * 90)
    print("TEST 6 · WEIGHT SENSITIVITY (full sample, production buffer/threshold)")
    print("=" * 90)

    schemes = [
        ("Equal weight (1/1/1)",     1.0, 1.0, 1.0),
        ("Alpha-weighted (37/35/28)", 0.37, 0.35, 0.28),
        ("GII-heavy (50/25/25)",     0.50, 0.25, 0.25),
        ("Breadth-heavy (25/50/25)", 0.25, 0.50, 0.25),
        ("FinCon-heavy (25/25/50)",  0.25, 0.25, 0.50),
        ("Drop GII",                 0.0, 1.0, 1.0),
        ("Drop Breadth",             1.0, 0.0, 1.0),
        ("Drop FinCon",              1.0, 1.0, 0.0),
    ]
    print(f"\n    {'scheme':<28} {'SPX α':>8} {'IWM α':>8} {'BTC α':>8} {'SPX DD':>9}")
    print(f"    {'-'*28} {'-'*8} {'-'*8} {'-'*8} {'-'*9}")
    out = {}
    for name, w_g, w_b, w_f in schemes:
        if w_g + w_b + w_f <= 0:
            continue
        try:
            mrmi, _ = production_mrmi(data, w_gii=w_g, w_breadth=w_b, w_fincon=w_f)
        except Exception:
            continue
        rs = {a: backtest_signal(mrmi, asset_rets[a]) for a in ("spx", "iwm", "btc")}
        if not all(rs.values()):
            continue
        out[name] = {a: rs[a]["alpha"] for a in ("spx", "iwm", "btc")}
        out[name]["spx_dd"] = rs["spx"]["strat_dd"]
        print(f"    {name:<28} {fmt_pct(rs['spx']['alpha']):>8} {fmt_pct(rs['iwm']['alpha']):>8} "
              f"{fmt_pct(rs['btc']['alpha']):>8} {fmt_pct(rs['spx']['strat_dd']):>9}")
    return out


# ── main ───────────────────────────────────────────────────────────────────

def main():
    print("=" * 90)
    print("Production Framework Backtest — Comprehensive")
    print("=" * 90)

    print("\n  Loading data...", flush=True)
    data = fetch_all_data(use_cache=True)
    print(f"  Loaded {len(data)} rows from {data.index[0].date()} to {data.index[-1].date()}")

    print("  Building production MRMI...", flush=True)
    mrmi, mmi = production_mrmi(data)

    asset_rets = {
        "spx": data["^GSPC"].pct_change().reindex(mrmi.index),
        "iwm": data["IWM"].pct_change().reindex(mrmi.index),
        "btc": data["BTC-USD"].pct_change().reindex(mrmi.index),
    }
    aligned = pd.DataFrame({"mrmi": mrmi, **asset_rets}).dropna()
    n = len(aligned)
    split_idx = int(n * 0.70)
    asset_rets_aligned = {k: aligned[k] for k in ("spx", "iwm", "btc")}
    print(f"  Aligned {n} rows. IS = {split_idx} bars (≈{split_idx/252:.1f} yr), "
          f"OOS = {n - split_idx} bars (≈{(n-split_idx)/252:.1f} yr).")

    test_headline(aligned["mrmi"], asset_rets_aligned, split_idx)
    test_individual_indicators(data, asset_rets_aligned, split_idx)
    test_walk_forward(aligned["mrmi"], asset_rets_aligned)
    test_benchmarks(data, aligned["mrmi"], asset_rets_aligned)
    test_transaction_costs(aligned["mrmi"], asset_rets_aligned["spx"])
    test_weights(data, asset_rets_aligned, split_idx)

    print("\n" + "=" * 90)
    print("DONE. Use these numbers to update docs/PRESENTATION.html.")
    print("=" * 90)


if __name__ == "__main__":
    main()
