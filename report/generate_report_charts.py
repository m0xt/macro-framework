#!/usr/bin/env python3
"""
Generate charts for the monthly Macro Update report.

Each chart is produced as a standalone PNG in `.cache/charts/`, embedded into
the report HTML by build_report.py via base64.

Current charts (keyed to the v2 dashboard's structure):
  01_mrmi.png         — MRMI history with LONG/CASH regime shading + SPX overlay
  02_mmi_drivers.png  — Three stacked panels: GII / Breadth / FinCon
  03_macro_stress.png — Real Economy Score + Inflation Direction + Stress Intensity
  04_real_economy_components.png — Four inputs to Real Economy Score
  05_decomposition.png — Today's MRMI value decomposed: MMI + Buffer − Threshold
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from build import (
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_macro_context,
    calc_milk_road_macro_index,
    calc_sector_breadth,
)

CACHE_DIR = ROOT / ".cache"
CHARTS_DIR = CACHE_DIR / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# Dashboard-matched dark theme
plt.rcParams.update({
    "figure.facecolor": "#0a0a0a",
    "axes.facecolor": "#111",
    "axes.edgecolor": "#222",
    "axes.labelcolor": "#999",
    "axes.titlecolor": "#e0e0e0",
    "axes.titleweight": "bold",
    "xtick.color": "#666",
    "ytick.color": "#666",
    "grid.color": "#1a1a1a",
    "grid.linewidth": 0.5,
    "text.color": "#e0e0e0",
    "savefig.facecolor": "#0a0a0a",
    "savefig.edgecolor": "none",
    "savefig.dpi": 110,
    "savefig.bbox": "tight",
    "font.family": "sans-serif",
    "font.size": 10,
})

GREEN = "#4CAF50"
RED = "#E84B5A"
BLUE = "#4DA8DA"
ACCENT = "#f59e0b"
WHITE = "#e0e0e0"
AMBER = "#cdaa6a"


def _style(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#333")
    ax.spines["bottom"].set_color("#333")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def _shade_regimes(ax, signal, dates, alpha=0.15):
    """Green band when signal > 0, red band when < 0."""
    vals = signal.values
    for color, predicate in ((GREEN, lambda v: pd.notna(v) and v > 0),
                              (RED,   lambda v: pd.notna(v) and v < 0)):
        in_band = False
        start = None
        for i, v in enumerate(vals):
            hit = predicate(v)
            if hit and not in_band:
                in_band, start = True, i
            elif not hit and in_band:
                ax.axvspan(dates[start], dates[i], color=color, alpha=alpha, lw=0)
                in_band = False
        if in_band and start is not None:
            ax.axvspan(dates[start], dates[-1], color=color, alpha=alpha, lw=0)


def _slice_recent(series, days=504):
    """Last ~2 years of non-NaN observations."""
    end = series.dropna().index[-1]
    start = end - pd.Timedelta(days=int(days * 1.5))
    return series.loc[start:end]


# ─── data loading ──────────────────────────────────────────────────────────
def load_all():
    data = pd.read_pickle(CACHE_DIR / "raw_data.pkl")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    mmi = calc_composite(gii, fincon, breadth)
    macro_ctx = calc_macro_context(data, lookback_years=3, apply_release_lags=True)
    mrmi_dict = calc_milk_road_macro_index(mmi, macro_ctx, buffer_size=1.0, threshold=0.5)
    return data, gii, fincon, breadth, mmi, macro_ctx, mrmi_dict


# ─── 01: MRMI with SPX ─────────────────────────────────────────────────────
def chart_mrmi(data, mrmi_dict):
    mrmi = _slice_recent(mrmi_dict["mrmi"], 504).dropna()
    spx = data["^GSPC"].reindex(mrmi.index).dropna()

    fig, ax1 = plt.subplots(figsize=(10, 4.5))
    _shade_regimes(ax1, mrmi, mrmi.index)

    ax1.plot(mrmi.index, mrmi.values, color=WHITE, linewidth=1.8, label="MRMI")
    ax1.axhline(0, color="#666", linewidth=1.0, linestyle="--", label="LONG / CASH threshold")
    ax1.set_ylabel("MRMI", color=WHITE)
    ax1.set_ylim(-3, 5)
    ax1.tick_params(axis="y", labelcolor=WHITE)

    ax2 = ax1.twinx()
    spx_norm = (spx / spx.iloc[0]) * 100
    ax2.plot(spx_norm.index, spx_norm.values, color=ACCENT, linewidth=1.5, alpha=0.85,
             label="S&P 500 (rebased to 100)")
    ax2.set_ylabel("S&P 500 (start = 100)", color=ACCENT)
    ax2.tick_params(axis="y", labelcolor=ACCENT)
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color("#333")

    _style(ax1)
    ax1.set_xlim(mrmi.index[0], mrmi.index[-1])
    ax1.set_title("MRMI vs S&P 500 — past 2 years",
                  fontsize=12, pad=10, loc="left")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="lower right",
               framealpha=0.0, labelcolor="#bbb", fontsize=9)

    plt.savefig(CHARTS_DIR / "01_mrmi.png")
    plt.close()
    print("  Saved: 01_mrmi.png")


# ─── 02: MMI's three drivers ──────────────────────────────────────────────
def chart_mmi_drivers(gii, fincon, breadth):
    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)

    panels = [
        (axes[0], gii["fast"], "GII — Growth Impulses", "credit, sectors, copper, vol, curve"),
        (axes[1], breadth["composite"], "Sector Breadth", "7 cyclical ETFs · participation in the rally"),
        (axes[2], fincon["composite"], "Financial Conditions (FinCon)", "VIX + MOVE + HY spread, inverted"),
    ]

    for ax, series, title, subtitle in panels:
        s = _slice_recent(series, 504).dropna()
        ax.plot(s.index, s.values, color=WHITE, linewidth=1.4)
        ax.fill_between(s.index, 0, s.values, where=s.values > 0, color=GREEN, alpha=0.20, lw=0)
        ax.fill_between(s.index, 0, s.values, where=s.values < 0, color=RED, alpha=0.20, lw=0)
        ax.axhline(0, color="#666", linewidth=0.8, linestyle="--")
        ax.set_title(f"{title}  —  {subtitle}", loc="left", fontsize=11)
        ax.set_ylabel("z-score")
        _style(ax)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "02_mmi_drivers.png")
    plt.close()
    print("  Saved: 02_mmi_drivers.png")


# ─── 03: Macro Stress (RE + Inflation + intensity) ────────────────────────
def chart_macro_stress(macro_ctx, mrmi_dict):
    re_score = _slice_recent(macro_ctx["real_economy_score"], 504 * 2).dropna()
    inf_dir = _slice_recent(macro_ctx["inflation_dir_pp"], 504 * 2).dropna()
    stress = _slice_recent(mrmi_dict["stress_intensity"], 504 * 2).dropna()

    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

    # Real Economy Score
    ax = axes[0]
    ax.plot(re_score.index, re_score.values, color=WHITE, linewidth=1.5)
    ax.fill_between(re_score.index, 0, re_score.values,
                    where=re_score.values > 0, color=GREEN, alpha=0.20, lw=0)
    ax.fill_between(re_score.index, 0, re_score.values,
                    where=re_score.values < 0, color=RED, alpha=0.20, lw=0)
    ax.axhline(0, color="#666", linewidth=0.8, linestyle="--")
    ax.set_title("Real Economy Score  —  PCE / Sahm (inv) / Income / GDPNow, z-scored over 3y",
                 loc="left", fontsize=11)
    ax.set_ylabel("z-score")
    _style(ax)

    # Inflation Direction
    ax = axes[1]
    ax.plot(inf_dir.index, inf_dir.values, color=WHITE, linewidth=1.5)
    ax.fill_between(inf_dir.index, 0, inf_dir.values,
                    where=inf_dir.values > 0, color=RED, alpha=0.20, lw=0,
                    label="rising (adverse)")
    ax.fill_between(inf_dir.index, 0, inf_dir.values,
                    where=inf_dir.values < 0, color=GREEN, alpha=0.20, lw=0,
                    label="cooling (benign)")
    ax.axhline(0, color="#666", linewidth=0.8, linestyle="--")
    ax.set_title("Inflation Direction  —  Δ Core CPI YoY over the last 6 months",
                 loc="left", fontsize=11)
    ax.set_ylabel("pp (percentage points)")
    _style(ax)
    ax.legend(loc="lower left", framealpha=0.0, labelcolor="#bbb", fontsize=9)

    # Stress Intensity
    ax = axes[2]
    ax.fill_between(stress.index, 0, stress.values, color=AMBER, alpha=0.55, lw=0)
    ax.plot(stress.index, stress.values, color=AMBER, linewidth=1.5)
    ax.axhline(0.5, color="#888", linewidth=0.8, linestyle="--",
               label="Stress ON threshold (0.5)")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Stress Intensity  —  AND-gate output, fires when crossing 0.5",
                 loc="left", fontsize=11)
    ax.set_ylabel("[0, 1]")
    _style(ax)
    ax.legend(loc="upper right", framealpha=0.0, labelcolor="#bbb", fontsize=9)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "03_macro_stress.png")
    plt.close()
    print("  Saved: 03_macro_stress.png")


# ─── 04: Real Economy components ──────────────────────────────────────────
def chart_real_economy_components(macro_ctx):
    comps = macro_ctx["real_economy_components"]  # DataFrame: pce, labor_inv, income, gdpnow
    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=True)
    panels = [
        (axes[0, 0], "pce",       "Real PCE YoY — consumer spending growth"),
        (axes[0, 1], "labor_inv", "Sahm Rule (inverted) — labor market stress"),
        (axes[1, 0], "income",    "Real Personal Income YoY"),
        (axes[1, 1], "gdpnow",    "Atlanta Fed GDPNow nowcast"),
    ]
    for ax, col, title in panels:
        s = _slice_recent(comps[col], 504 * 2).dropna()
        if s.empty:
            continue
        ax.plot(s.index, s.values, color=WHITE, linewidth=1.3)
        ax.fill_between(s.index, 0, s.values, where=s.values > 0, color=GREEN, alpha=0.20, lw=0)
        ax.fill_between(s.index, 0, s.values, where=s.values < 0, color=RED, alpha=0.20, lw=0)
        ax.axhline(0, color="#666", linewidth=0.7, linestyle="--")
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_ylabel("z-score")
        _style(ax)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "04_real_economy_components.png")
    plt.close()
    print("  Saved: 04_real_economy_components.png")


# ─── 05: Today's MRMI decomposition (bar) ─────────────────────────────────
def chart_decomposition(mrmi_dict):
    latest_idx = mrmi_dict["mrmi"].dropna().index[-1]
    mmi = float(mrmi_dict["momentum"].loc[latest_idx])
    buffer = float(mrmi_dict["macro_buffer"].loc[latest_idx])
    threshold = float(mrmi_dict["threshold"])
    mrmi_val = float(mrmi_dict["mrmi"].loc[latest_idx])

    labels = ["MMI\n(market pillar)", "+ Buffer\n(1 − Stress)", "− Threshold", "= MRMI"]
    values = [mmi, buffer, -threshold, mrmi_val]
    colors = [GREEN if mmi >= 0 else RED, AMBER, "#888",
              GREEN if mrmi_val >= 0 else RED]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(labels, values, color=colors, edgecolor="#222", width=0.6)

    for bar, v in zip(bars, values):
        y = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2,
                y + (0.08 if y >= 0 else -0.18),
                f"{v:+.2f}", ha="center", color=WHITE, fontsize=12, weight="bold")

    ax.axhline(0, color="#666", linewidth=0.8)
    ax.set_ylim(-1.0, max(2.5, mrmi_val + 0.8))
    ax.set_title(
        f"Today's MRMI = {mmi:+.2f} + {buffer:+.2f} − {threshold:.2f} = {mrmi_val:+.2f}  "
        f"({'LONG' if mrmi_val > 0 else 'CASH'})",
        loc="left", fontsize=12, pad=10)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#333")
    ax.spines["bottom"].set_color("#333")
    ax.grid(True, axis="y", alpha=0.3)
    ax.tick_params(axis="x", labelcolor="#ccc", labelsize=10)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "05_decomposition.png")
    plt.close()
    print("  Saved: 05_decomposition.png")


def main():
    print("Loading data and computing indicators...")
    data, gii, fincon, breadth, _mmi, macro_ctx, mrmi_dict = load_all()

    print("Rendering charts...")
    chart_mrmi(data, mrmi_dict)
    chart_mmi_drivers(gii, fincon, breadth)
    chart_macro_stress(macro_ctx, mrmi_dict)
    chart_real_economy_components(macro_ctx)
    chart_decomposition(mrmi_dict)

    print(f"All charts saved to {CHARTS_DIR}")


if __name__ == "__main__":
    main()
