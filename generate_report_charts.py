#!/usr/bin/env python3
"""
Generate all charts for the monthly macro update report.
Saves PNG files to .cache/charts/ for embedding in the HTML report.
"""

from pathlib import Path
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np

from build import (
    calc_growth_impulse, calc_financial_conditions, calc_sector_breadth,
    calc_composite, calc_business_cycle, calc_inflation_context
)

CACHE_DIR = Path(__file__).parent / ".cache"
CHARTS_DIR = CACHE_DIR / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

# Dark theme matching the dashboard
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
PINK = "#E84B9A"
PURPLE = "#A78BFA"
ORANGE = "#FF8C00"

# Season colors
SPRING = "#A8D86E"   # fresh green
SUMMER = "#FF8C00"   # warm orange
FALL = "#E84B5A"     # red leaves
WINTER = "#4DA8DA"   # cool blue


def load_indicators():
    data = pd.read_pickle(CACHE_DIR / "raw_data.pkl")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    pulse = calc_composite(gii, fincon, breadth)
    climate = calc_business_cycle(data)
    infl = calc_inflation_context(data)
    return data, gii, fincon, breadth, pulse, climate, infl


def shade_regimes(ax, signal, dates, alpha=0.18):
    """Shade background green when signal > 0, red when < 0."""
    sig_array = signal.values
    in_green = False
    start_idx = None
    for i, val in enumerate(sig_array):
        is_green = pd.notna(val) and val > 0
        if is_green and not in_green:
            start_idx = i
            in_green = True
        elif not is_green and in_green:
            ax.axvspan(dates[start_idx], dates[i], color=GREEN, alpha=alpha, lw=0)
            in_green = False
    if in_green and start_idx is not None:
        ax.axvspan(dates[start_idx], dates[-1], color=GREEN, alpha=alpha, lw=0)

    in_red = False
    start_idx = None
    for i, val in enumerate(sig_array):
        is_red = pd.notna(val) and val < 0
        if is_red and not in_red:
            start_idx = i
            in_red = True
        elif not is_red and in_red:
            ax.axvspan(dates[start_idx], dates[i], color=RED, alpha=alpha, lw=0)
            in_red = False
    if in_red and start_idx is not None:
        ax.axvspan(dates[start_idx], dates[-1], color=RED, alpha=alpha, lw=0)


def style_axis(ax, year_locator=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#333")
    ax.spines["bottom"].set_color("#333")
    ax.grid(True, alpha=0.3)
    if year_locator:
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


def slice_recent(series, days=504):
    end = series.dropna().index[-1]
    start = end - pd.Timedelta(days=int(days * 1.5))
    return series.loc[start:end].dropna()


# ─── 1. MRMI chart ────────────────────────────────────
def chart_pulse_with_spx(data, pulse):
    """MRMI signal with green/red regimes and SPX overlay."""
    mrmi = slice_recent(pulse, 504)
    spx = data["^GSPC"].loc[mrmi.index].dropna()

    fig, ax1 = plt.subplots(figsize=(10, 4.5))

    shade_regimes(ax1, mrmi, mrmi.index, alpha=0.18)

    ax1.plot(mrmi.index, mrmi.values, color=WHITE, linewidth=1.8,
             linestyle="--", label="MRMI")
    ax1.axhline(0, color="#444", linewidth=0.8, linestyle="-")
    ax1.set_ylabel("MRMI Z-Score", color=WHITE)
    ax1.set_ylim(-2.5, 2.5)
    ax1.tick_params(axis="y", labelcolor=WHITE)

    ax2 = ax1.twinx()
    spx_normalized = (spx / spx.iloc[0]) * 100
    ax2.plot(spx_normalized.index, spx_normalized.values, color=ACCENT,
             linewidth=2.0, label="S&P 500 (normalized)")
    ax2.set_ylabel("S&P 500 (start = 100)", color=ACCENT)
    ax2.tick_params(axis="y", labelcolor=ACCENT)
    ax2.spines["top"].set_visible(False)
    ax2.spines["left"].set_visible(False)
    ax2.spines["right"].set_color("#333")

    style_axis(ax1)
    ax1.set_xlim(mrmi.index[0], mrmi.index[-1])
    ax1.set_title("MRMI — Milk Road Momentum Index vs S&P 500 (Past 2 Years)",
                  fontsize=12, pad=12, loc="left")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
               framealpha=0.0, labelcolor="#bbb", fontsize=9)

    plt.savefig(CHARTS_DIR / "01_pulse.png")
    plt.close()
    print("  Saved: 01_pulse.png")


# ─── 2. MRMI components — the actual three indicators ───────────────
def chart_pulse_components_real(data, gii, fincon, breadth):
    """MRMI components — show all three actual indicators (GII, FinCon, Breadth)."""
    end = gii.index[-1]
    start = end - pd.Timedelta(days=504 * 1.5)

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True)

    # GII (z-score)
    g = gii["fast"].loc[start:end].dropna()
    axes[0].plot(g.index, g.values, color=WHITE, linewidth=1.5)
    axes[0].fill_between(g.index, 0, g.values, where=g.values > 0, color=GREEN, alpha=0.2)
    axes[0].fill_between(g.index, 0, g.values, where=g.values < 0, color=RED, alpha=0.2)
    axes[0].axhline(0, color="#444", linewidth=0.8)
    axes[0].set_title("GII — Growth Impulses (z-score, > 0 = momentum accelerating)",
                      loc="left", fontsize=11)
    axes[0].set_ylabel("Z-Score")

    # Financial Conditions composite (z-score, higher = looser = good)
    f = fincon["composite"].loc[start:end].dropna()
    axes[1].plot(f.index, f.values, color=WHITE, linewidth=1.5)
    axes[1].fill_between(f.index, 0, f.values, where=f.values > 0, color=GREEN, alpha=0.2)
    axes[1].fill_between(f.index, 0, f.values, where=f.values < 0, color=RED, alpha=0.2)
    axes[1].axhline(0, color="#444", linewidth=0.8)
    axes[1].set_title("Financial Conditions — VIX + MOVE + HY spread, inverted (z-score, > 0 = loose/good)",
                      loc="left", fontsize=11)
    axes[1].set_ylabel("Z-Score")

    # Sector Breadth (z-score)
    b = breadth["composite"].loc[start:end].dropna()
    axes[2].plot(b.index, b.values, color=WHITE, linewidth=1.5)
    axes[2].fill_between(b.index, 0, b.values, where=b.values > 0, color=GREEN, alpha=0.2)
    axes[2].fill_between(b.index, 0, b.values, where=b.values < 0, color=RED, alpha=0.2)
    axes[2].axhline(0, color="#444", linewidth=0.8)
    axes[2].set_title("Sector Breadth — 7 cyclical sectors (z-score, > 0 = broad rally)",
                      loc="left", fontsize=11)
    axes[2].set_ylabel("Z-Score")

    for ax in axes:
        style_axis(ax)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "02_pulse_components.png")
    plt.close()
    print("  Saved: 02_pulse_components.png")


# ─── 3. MRCI chart ──────────────────────────────────────────────────
def chart_climate(climate):
    """MRCI composite chart."""
    bc = slice_recent(climate["composite"], 504)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(bc.index, bc.values, color=BLUE, linewidth=2.0)
    ax.fill_between(bc.index, 0, bc.values, where=bc.values > 0, color=BLUE, alpha=0.15)
    ax.fill_between(bc.index, 0, bc.values, where=bc.values < 0, color="#888", alpha=0.10)
    ax.axhline(0, color="#444", linewidth=0.8)
    ax.axhline(1, color="#222", linewidth=0.6, linestyle=":")
    ax.axhline(-1, color="#222", linewidth=0.6, linestyle=":")
    ax.set_title("MRCI — Milk Road Cycle Index (z-score, > 0 = expanding)",
                 loc="left", fontsize=12, pad=12)
    ax.set_ylabel("Z-Score")
    style_axis(ax)
    ax.set_xlim(bc.index[0], bc.index[-1])
    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "03_climate.png")
    plt.close()
    print("  Saved: 03_climate.png")


# ─── 4. MRCI pillars (real values) ──────────────────────────────────
def chart_climate_pillars_real(data, climate):
    """Four cycle pillars — mix of real values and z-scores."""
    end = climate.index[-1]
    start = end - pd.Timedelta(days=504 * 1.5)

    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=True)

    # Real Economy — show CFNAI (real value)
    if "CFNAI" in data.columns:
        s = data["CFNAI"].loc[start:end].dropna()
        ax = axes[0, 0]
        ax.plot(s.index, s.values, color=BLUE, linewidth=1.5)
        ax.fill_between(s.index, 0, s.values, where=s.values > 0, color=GREEN, alpha=0.15)
        ax.fill_between(s.index, 0, s.values, where=s.values < 0, color=RED, alpha=0.15)
        ax.axhline(0, color="#444", linewidth=0.6)
        ax.axhline(-0.7, color=RED, linewidth=0.6, linestyle=":", label="Recession threshold")
        ax.set_title("Real Economy — CFNAI (real value, > 0 = above trend)",
                     loc="left", fontsize=11)
        ax.set_ylabel("CFNAI")
        ax.legend(loc="lower left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    # Credit & Money — show 3M-10Y curve in %
    if "DGS10" in data.columns and "DGS3MO" in data.columns:
        curve = (data["DGS10"] - data["DGS3MO"]).loc[start:end].dropna()
        ax = axes[0, 1]
        ax.plot(curve.index, curve.values, color=BLUE, linewidth=1.5)
        ax.fill_between(curve.index, 0, curve.values, where=curve.values > 0,
                        color=GREEN, alpha=0.15)
        ax.fill_between(curve.index, 0, curve.values, where=curve.values < 0,
                        color=RED, alpha=0.15)
        ax.axhline(0, color=RED, linewidth=0.8, linestyle="--", label="Inversion line")
        ax.set_title("Credit & Money — 10Y-3M Yield Curve (%, < 0 = recession risk)",
                     loc="left", fontsize=11)
        ax.set_ylabel("Spread (%)")
        ax.legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    # Markets — z-score (already a ratio, z-score is fine)
    if "markets" in climate.columns:
        s = climate["markets"].loc[start:end].dropna()
        ax = axes[1, 0]
        ax.plot(s.index, s.values, color=BLUE, linewidth=1.5)
        ax.fill_between(s.index, 0, s.values, where=s.values > 0, color=GREEN, alpha=0.15)
        ax.fill_between(s.index, 0, s.values, where=s.values < 0, color=RED, alpha=0.15)
        ax.axhline(0, color="#444", linewidth=0.6)
        ax.set_title("Markets — Cyclicals vs SPX (z-score, > 0 = cyclicals leading)",
                     loc="left", fontsize=11)
        ax.set_ylabel("Z-Score")
        style_axis(ax)

    # Labor — show actual jobless claims (in thousands)
    if "ICSA" in data.columns:
        claims = (data["ICSA"] / 1000).loc[start:end].dropna()
        ax = axes[1, 1]
        ax.plot(claims.index, claims.values, color=BLUE, linewidth=1.5)
        ax.axhline(250, color=RED, linewidth=0.6, linestyle=":", label="250K warning level")
        ax.fill_between(claims.index, 250, claims.values, where=claims.values > 250,
                        color=RED, alpha=0.15)
        ax.fill_between(claims.index, 250, claims.values, where=claims.values < 250,
                        color=GREEN, alpha=0.15)
        ax.set_title("Labor — Initial Jobless Claims (thousands, < 250K = healthy)",
                     loc="left", fontsize=11)
        ax.set_ylabel("Claims (000s)")
        ax.legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "04_climate_pillars.png")
    plt.close()
    print("  Saved: 04_climate_pillars.png")


# ─── 5. Inflation: realized CPI + breakeven expectations ───────────────
def chart_inflation_yields(data):
    """Realized CPI vs forward expectations, plus yield curve."""
    end = data.index[-1]
    start = end - pd.Timedelta(days=504 * 1.5)

    fig, axes = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True)

    # Top: Realized inflation (CPI YoY)
    cpi_yoy = None
    core_yoy = None
    if "CPIAUCSL" in data.columns:
        cpi = data["CPIAUCSL"]
        cpi_yoy = (cpi.pct_change(252) * 100).loc[start:end].dropna()
    if "CPILFESL" in data.columns:
        core = data["CPILFESL"]
        core_yoy = (core.pct_change(252) * 100).loc[start:end].dropna()

    if cpi_yoy is not None:
        axes[0].plot(cpi_yoy.index, cpi_yoy.values, color=RED, linewidth=1.8, label="Headline CPI YoY")
    if core_yoy is not None:
        axes[0].plot(core_yoy.index, core_yoy.values, color=ORANGE, linewidth=1.5, label="Core CPI YoY", alpha=0.8)
    axes[0].axhline(2.0, color="#666", linewidth=0.6, linestyle=":", label="Fed Target (2%)")
    axes[0].axhline(3.0, color="#444", linewidth=0.6, linestyle=":", label="3% line")
    axes[0].set_title("Realized Inflation — CPI Year-over-Year (%)",
                      loc="left", fontsize=11)
    axes[0].set_ylabel("%")
    axes[0].legend(loc="upper right", framealpha=0.0, labelcolor="#bbb", fontsize=9)
    style_axis(axes[0])

    # Middle: Forward expectations (breakevens)
    if "T5YIE" in data.columns and "T10YIE" in data.columns:
        t5 = data["T5YIE"].loc[start:end].dropna()
        t10 = data["T10YIE"].loc[start:end].dropna()
        axes[1].plot(t5.index, t5.values, color=ORANGE, linewidth=1.5, label="5Y Breakeven")
        axes[1].plot(t10.index, t10.values, color=ACCENT, linewidth=1.5, label="10Y Breakeven")
        axes[1].axhline(2.0, color="#666", linewidth=0.6, linestyle=":", label="Fed Target (2%)")
        axes[1].set_title("Forward Inflation Expectations — Breakeven Rates (%)",
                          loc="left", fontsize=11)
        axes[1].set_ylabel("%")
        axes[1].legend(loc="upper right", framealpha=0.0, labelcolor="#bbb", fontsize=9)
        style_axis(axes[1])

    # Bottom: Yield curve
    if all(c in data.columns for c in ["DGS10", "DGS3MO", "DGS2"]):
        c310 = (data["DGS10"] - data["DGS3MO"]).loc[start:end].dropna()
        c210 = (data["DGS10"] - data["DGS2"]).loc[start:end].dropna()
        axes[2].plot(c310.index, c310.values, color=BLUE, linewidth=1.5,
                     label="10Y - 3M (Fed preferred)")
        axes[2].plot(c210.index, c210.values, color=PURPLE, linewidth=1.2,
                     label="10Y - 2Y", alpha=0.8)
        axes[2].axhline(0, color=RED, linewidth=0.8, linestyle="--", label="Inversion line")
        axes[2].fill_between(c310.index, 0, c310.values, where=c310.values < 0,
                             color=RED, alpha=0.15)
        axes[2].set_title("Yield Curve Spreads (%, negative = inverted)",
                          loc="left", fontsize=11)
        axes[2].set_ylabel("Spread (%)")
        axes[2].legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=9)
        style_axis(axes[2])

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "05_inflation_yields.png")
    plt.close()
    print("  Saved: 05_inflation_yields.png")


# ─── 6. Seasons quadrant — 3 points only ───────────────────────────────
def chart_seasons_quadrant(climate, infl):
    """Macro seasons quadrant with Now, 30d ago, 180d ago."""
    bc = climate["composite"].dropna()
    inf = infl["composite"].dropna()
    common = bc.index.intersection(inf.index)
    bc = bc.loc[common]
    inf = inf.loc[common]

    inf_change = inf - inf.shift(21)
    inf_dir = inf_change.dropna()
    bc = bc.loc[inf_dir.index]

    # Get 3 points
    now_idx = -1
    d30_idx = -22 if len(bc) > 22 else -1
    d180_idx = -127 if len(bc) > 127 else 0

    points = [
        ("Now", bc.iloc[now_idx], inf_dir.iloc[now_idx], ACCENT, 250),
        ("30 days ago", bc.iloc[d30_idx], inf_dir.iloc[d30_idx], "#bbb", 130),
        ("180 days ago", bc.iloc[d180_idx], inf_dir.iloc[d180_idx], "#666", 100),
    ]

    fig, ax = plt.subplots(figsize=(9, 7.5))

    # Quadrant backgrounds (with seasons)
    # x = cycle direction (right = expanding, left = contracting)
    # y = inflation direction (up = rising, down = falling)
    # Spring: cycle ↑, inflation ↓ (bottom right) — SPRING
    # Summer: cycle ↑, inflation ↑ (top right) — SUMMER
    # Fall: cycle ↓, inflation ↑ (top left) — FALL
    # Winter: cycle ↓, inflation ↓ (bottom left) — WINTER

    ax.axhspan(-1, 0, xmin=0.5, xmax=1.0, facecolor=SPRING, alpha=0.10)
    ax.axhspan(0, 1, xmin=0.5, xmax=1.0, facecolor=SUMMER, alpha=0.10)
    ax.axhspan(0, 1, xmin=0.0, xmax=0.5, facecolor=FALL, alpha=0.10)
    ax.axhspan(-1, 0, xmin=0.0, xmax=0.5, facecolor=WINTER, alpha=0.10)

    # Connect points with lines (chronological)
    xs = [p[1] for p in reversed(points)]
    ys = [p[2] for p in reversed(points)]
    ax.plot(xs, ys, color="#444", linewidth=1, linestyle="--", alpha=0.6, zorder=2)

    # Plot each point with annotation
    for label, x, y, color, size in points:
        ax.scatter(x, y, s=size, color=color, zorder=5,
                   edgecolors=WHITE, linewidth=2)
        # Annotation offset
        offset_y = 0.08 if y < 0.3 else -0.08
        ax.annotate(label, (x, y), xytext=(x + 0.1, y + offset_y),
                    fontsize=10, color=color, fontweight="bold")

    # Quadrant labels (corners)
    ax.text(2.3, -0.7, "SPRING", fontsize=14, color=SPRING, fontweight="bold",
            ha="center", alpha=0.9)
    ax.text(2.3, -0.82, "Cycle ↑ + Inflation ↓\n(Equities)", fontsize=8,
            color=SPRING, ha="center", alpha=0.7)

    ax.text(2.3, 0.85, "SUMMER", fontsize=14, color=SUMMER, fontweight="bold",
            ha="center", alpha=0.9)
    ax.text(2.3, 0.73, "Cycle ↑ + Inflation ↑\n(Cyclicals, commodities)", fontsize=8,
            color=SUMMER, ha="center", alpha=0.7)

    ax.text(-2.3, 0.85, "FALL", fontsize=14, color=FALL, fontweight="bold",
            ha="center", alpha=0.9)
    ax.text(-2.3, 0.73, "Cycle ↓ + Inflation ↑\n(Cash, gold, TIPS)", fontsize=8,
            color=FALL, ha="center", alpha=0.7)

    ax.text(-2.3, -0.7, "WINTER", fontsize=14, color=WINTER, fontweight="bold",
            ha="center", alpha=0.9)
    ax.text(-2.3, -0.82, "Cycle ↓ + Inflation ↓\n(Bonds, defensives)", fontsize=8,
            color=WINTER, ha="center", alpha=0.7)

    ax.axhline(0, color="#666", linewidth=1)
    ax.axvline(0, color="#666", linewidth=1)

    ax.set_xlim(-3, 3)
    ax.set_ylim(-1.0, 1.0)
    ax.set_xlabel("MRCI — Business Cycle (← Contracting | Expanding →)", color="#999")
    ax.set_ylabel("Inflation 30d Change (← Falling | Rising →)", color="#999")
    ax.set_title("Macro Seasons — Where We Are Now",
                 loc="left", fontsize=12, pad=12)
    # Manually style without year_locator (this is a scatter, not time series)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#333")
    ax.spines["bottom"].set_color("#333")
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_locator(plt.MultipleLocator(1))
    ax.yaxis.set_major_locator(plt.MultipleLocator(0.5))

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "06_seasons.png")
    plt.close()
    print("  Saved: 06_seasons.png")


# ─── 7. What Changed — zoomed regime move (last 90 days) ───────────────
def chart_what_changed(data, pulse, fincon, gii, breadth):
    """Last 90 days zoomed in to show the regime flip."""
    end = pulse.dropna().index[-1]
    start = end - pd.Timedelta(days=90)

    p = pulse.loc[start:end].dropna()
    g = gii["fast"].loc[start:end].dropna()
    f = fincon["composite"].loc[start:end].dropna()
    b = breadth["composite"].loc[start:end].dropna()

    fig, ax = plt.subplots(figsize=(10, 4.5))
    shade_regimes(ax, p, p.index, alpha=0.15)

    ax.plot(p.index, p.values, color=WHITE, linewidth=2.2, label="MRMI", linestyle="--")
    ax.plot(g.index, g.values, color=GREEN, linewidth=1.2, label="GII", alpha=0.7)
    ax.plot(f.index, f.values, color=BLUE, linewidth=1.2, label="FinCon", alpha=0.7)
    ax.plot(b.index, b.values, color=ACCENT, linewidth=1.2, label="Sector Breadth", alpha=0.7)
    ax.axhline(0, color="#444", linewidth=0.8)

    ax.set_title("The Regime Flip — Last 90 Days (MRMI crossed back above zero)",
                 loc="left", fontsize=12, pad=12)
    ax.set_ylabel("Z-Score")
    ax.legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=9)
    style_axis(ax, year_locator=False)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "07_what_changed.png")
    plt.close()
    print("  Saved: 07_what_changed.png")


# ─── 8. Risk charts (4 small panels) ───────────────────────────────────
def chart_risks(data):
    """Four risk indicators in 2x2: CFNAI, SLOOS, 5Y BE, jobless claims."""
    end = data.index[-1]
    start = end - pd.Timedelta(days=504 * 1.5)

    fig, axes = plt.subplots(2, 2, figsize=(11, 6), sharex=True)

    # CFNAI
    if "CFNAI" in data.columns:
        s = data["CFNAI"].loc[start:end].dropna()
        ax = axes[0, 0]
        ax.plot(s.index, s.values, color=WHITE, linewidth=1.5)
        ax.axhline(0, color="#444", linewidth=0.6)
        ax.axhline(0.2, color=GREEN, linewidth=0.6, linestyle=":", label="Acceleration (>+0.20)")
        ax.axhline(-0.3, color=RED, linewidth=0.6, linestyle=":", label="Caution (<-0.30)")
        ax.fill_between(s.index, 0, s.values, where=s.values > 0, color=GREEN, alpha=0.15)
        ax.fill_between(s.index, 0, s.values, where=s.values < 0, color=RED, alpha=0.15)
        ax.set_title("CFNAI — Currently Slightly Below Trend", loc="left", fontsize=11)
        ax.set_ylabel("Index")
        ax.legend(loc="lower left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    # SLOOS
    if "DRTSCILM" in data.columns:
        s = data["DRTSCILM"].loc[start:end].dropna()
        ax = axes[0, 1]
        ax.plot(s.index, s.values, color=WHITE, linewidth=1.5)
        ax.axhline(0, color=GREEN, linewidth=0.6, linestyle=":", label="Easing")
        ax.fill_between(s.index, 0, s.values, where=s.values > 0, color=RED, alpha=0.15)
        ax.fill_between(s.index, 0, s.values, where=s.values < 0, color=GREEN, alpha=0.15)
        ax.set_title("SLOOS Lending Standards — Still Modestly Tightening (%)",
                     loc="left", fontsize=11)
        ax.set_ylabel("Net % Tightening")
        ax.legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    # 5Y Breakeven
    if "T5YIE" in data.columns:
        s = data["T5YIE"].loc[start:end].dropna()
        ax = axes[1, 0]
        ax.plot(s.index, s.values, color=ORANGE, linewidth=1.5)
        ax.axhline(2.0, color="#666", linewidth=0.6, linestyle=":", label="Fed Target")
        ax.axhline(2.8, color=RED, linewidth=0.6, linestyle=":", label="Summer alert (>2.8%)")
        ax.fill_between(s.index, 2.0, s.values, where=s.values > 2.8,
                        color=RED, alpha=0.15)
        ax.set_title("5Y Breakeven Inflation — Falling but Still Elevated (%)",
                     loc="left", fontsize=11)
        ax.set_ylabel("%")
        ax.legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    # Jobless claims
    if "ICSA" in data.columns:
        claims = (data["ICSA"] / 1000).loc[start:end].dropna()
        ax = axes[1, 1]
        ax.plot(claims.index, claims.values, color=WHITE, linewidth=1.5)
        ax.axhline(250, color=RED, linewidth=0.6, linestyle=":", label="250K warning")
        ax.fill_between(claims.index, 250, claims.values, where=claims.values > 250,
                        color=RED, alpha=0.15)
        ax.set_title("Initial Jobless Claims — Currently Healthy at 219K",
                     loc="left", fontsize=11)
        ax.set_ylabel("Claims (000s)")
        ax.legend(loc="upper left", framealpha=0.0, labelcolor="#bbb", fontsize=8)
        style_axis(ax)

    plt.tight_layout()
    plt.savefig(CHARTS_DIR / "08_risks.png")
    plt.close()
    print("  Saved: 08_risks.png")


def main():
    print("Generating report charts...")
    data, gii, fincon, breadth, pulse, climate, infl = load_indicators()

    chart_pulse_with_spx(data, pulse)
    chart_pulse_components_real(data, gii, fincon, breadth)
    chart_climate(climate)
    chart_climate_pillars_real(data, climate)
    chart_inflation_yields(data)
    chart_seasons_quadrant(climate, infl)
    chart_what_changed(data, pulse, fincon, gii, breadth)
    chart_risks(data)

    print(f"\nAll charts saved to {CHARTS_DIR}")


if __name__ == "__main__":
    main()
