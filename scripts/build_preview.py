#!/usr/bin/env python3
"""Render a local preview dashboard for task-34 unified-stress MRMI."""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from macro_framework import build as dashboard_build
from macro_framework.macro_pipeline import (
    CACHE_DIR,
    calc_business_cycle,
    calc_composite,
    calc_financial_conditions,
    calc_growth_impulse,
    calc_inflation_context,
    calc_macro_context,
    calc_milk_road_macro_index_unified_stress,
    calc_sector_breadth,
    fetch_all_data,
    prepare_chart_data,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "outputs" / "dashboard-preview.html"

ALPHA = 0.75
BETA = 0.5
LAMBDA_WEIGHT = 10
BUFFER_SIZE = 0.5
THRESHOLD = 0.75

STRESS_CUTOFF_CALM_WATCH = 3.0
STRESS_CUTOFF_WATCH_BUILDING = 5.0
STRESS_CUTOFF_BUILDING_ELEV = 7.0


def _latest(series):
    s = series.dropna()
    if len(s) == 0:
        return None
    return round(float(s.iloc[-1]), 4)


def _latest_label(series):
    s = series.dropna()
    if len(s) == 0:
        return None
    v = s.iloc[-1]
    return str(v) if v is not None else None


def _to_list(series):
    return [round(float(v), 4) if pd.notna(v) else None for v in series]


def _stress_bucket(score):
    if pd.isna(score):
        return None
    if score < STRESS_CUTOFF_CALM_WATCH:
        return "calm"
    if score < STRESS_CUTOFF_WATCH_BUILDING:
        return "watch"
    if score < STRESS_CUTOFF_BUILDING_ELEV:
        return "building"
    return "elevated"


def _stress_momentum(stress_raw):
    s = stress_raw.dropna()
    if len(s) < 8:
        return None, "#888", None
    delta = float(s.iloc[-1] - s.iloc[-8])
    if delta > 0.25:
        return "↑ rising", "#E84B5A", delta
    if delta < -0.25:
        return "↓ cooling", "#4CAF50", delta
    return "→ steady", "#cdaa6a", delta


def _build_snapshot(data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, mrmi_combined, preview_meta):
    composite_v = _latest(composite)
    comps = macro_ctx.get("real_economy_components")
    comps_latest = {}
    if comps is not None and not comps.empty:
        for col in comps.columns:
            comps_latest[col] = _latest(comps[col])
    raw = macro_ctx.get("real_economy_raw") or {}

    mrmi_v = _latest(mrmi_combined["mrmi"])
    underlier_keys = [
        "^GSPC", "IWM", "BTC-USD", "^VIX", "^MOVE", "^TNX",
        "HYG", "HG=F", "GC=F", "DBC",
        "DGS10", "DGS2", "DGS3MO", "DFII10",
        "BAMLH0A0HYM2", "T5YIE", "T10YIE",
        "ICSA", "CCSA", "DTWEXBGS",
        "WALCL", "WTREGEN", "RRPONTSYD",
    ]

    return {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "build_time_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "mrmi": {
            "composite": composite_v,
            "state": "green" if composite_v is not None and composite_v > 0 else "red" if composite_v is not None else None,
        },
        "components": {
            "gii_fast": _latest(gii["fast"]) if "fast" in gii else None,
            "fincon": _latest(fincon["composite"]) if "composite" in fincon else None,
            "breadth": _latest(breadth["composite"]) if "composite" in breadth else None,
        },
        "mrci": {
            "composite": _latest(biz_cycle["composite"]) if "composite" in biz_cycle else None,
            "real_economy": _latest(biz_cycle["real_economy"]) if "real_economy" in biz_cycle else None,
            "credit_money": _latest(biz_cycle["credit_money"]) if "credit_money" in biz_cycle else None,
            "markets": _latest(biz_cycle["markets"]) if "markets" in biz_cycle else None,
            "labor": _latest(biz_cycle["labor"]) if "labor" in biz_cycle else None,
        },
        "inflation": _latest(infl_ctx["composite"]) if "composite" in infl_ctx else None,
        "mrmi_combined": {
            "value": mrmi_v,
            "state": "LONG" if mrmi_v is not None and mrmi_v > 0 else "CASH" if mrmi_v is not None else None,
            "momentum": _latest(mrmi_combined["momentum"]),
            "stress_intensity": _latest(mrmi_combined["stress_intensity"]),
            "stress_score": _latest(mrmi_combined["stress_score"]),
            "stress_growth_pressure": _latest(mrmi_combined["stress_growth_pressure"]),
            "stress_inflation_pressure": _latest(mrmi_combined["stress_inflation_pressure"]),
            "stress_score_bucket": _latest_label(mrmi_combined["stress_score_bucket"]),
            "macro_buffer": _latest(mrmi_combined["macro_buffer"]),
            "buffer_size": BUFFER_SIZE,
            "threshold": THRESHOLD,
            "alpha": ALPHA,
            "beta": BETA,
            "lambda_weight": LAMBDA_WEIGHT,
            "stress_p99": round(float(mrmi_combined["stress_p99"]), 6),
        },
        "macro": {
            "real_economy_score": _latest(macro_ctx["real_economy_score"]),
            "real_economy_components": comps_latest,
            "inflation_dir_pp": _latest(macro_ctx["inflation_dir_pp"]),
            "core_cpi_yoy_pct": _latest(macro_ctx["core_cpi_yoy_pct"]),
            "raw": {k: _latest(v) for k, v in raw.items()},
        },
        "underliers": {k: _latest(data[k]) for k in underlier_keys if k in data},
        "preview": preview_meta,
    }


def _preview_meta(mrmi_combined, gii):
    stress_p99 = float(mrmi_combined["stress_p99"])
    raw_now = _latest(mrmi_combined["stress_raw"])
    delta_label, delta_color, delta = _stress_momentum(mrmi_combined["stress_raw"])
    delta_text = f" · 7d raw Δ {delta:+.2f}" if delta is not None else ""
    return {
        "label": "Phase 1 best unified stress α=0.75 β=0.5 λ=10 buffer=0.5 threshold=0.75",
        "stress_momentum_label": delta_label,
        "stress_momentum_color": delta_color,
        "stress_panel_tip": (
            "<p><strong>Preview formula:</strong> Macro Stress is the task-34 OR+AND signal: "
            "α·growth_weakness + β·inflation_pressure + λ·growth_weakness·inflation_pressure. "
            "The MRMI preview uses α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75.</p>"
            f"<p><strong>Display scale:</strong> stress_raw is divided by the full-history p99 ({stress_p99:.2f}) and multiplied by 10, clipped to 0–10.</p>"
            "<p><strong>Buckets:</strong> round display boundaries: Calm 0–3, Watch 3–5, Building 5–7, Elevated 7–10.</p>"
        ),
        "stress_panel_subtitle": (
            f"Preview stress_raw normalized by full-history p99 {stress_p99:.2f} onto 0–10. "
            "Round display buckets: Calm 0–3, Watch 3–5, Building 5–7, Elevated 7–10. "
            f"Raw now {raw_now:.2f}{delta_text}."
        ),
        "stress_reading_label": f"0–10 preview score · raw {raw_now:.2f} · p99 {stress_p99:.2f}",
        "stress_inputs_title": "growth_weakness · inflation_pressure",
        "stress_growth_label": "growth_weakness",
        "stress_inflation_label": "inflation_pressure",
        "stress_cutoff_calm_watch": STRESS_CUTOFF_CALM_WATCH,
        "stress_cutoff_watch_building": STRESS_CUTOFF_WATCH_BUILDING,
        "stress_cutoff_building_elev": STRESS_CUTOFF_BUILDING_ELEV,
        "chart": {
            "stress_inputs": {
                "growth_label": "growth_weakness",
                "inflation_label": "inflation_pressure",
                "growth_weakness": _to_list(mrmi_combined["growth_weakness"].reindex(gii.index)),
                "inflation_pressure": _to_list(mrmi_combined["inflation_pressure"].reindex(gii.index)),
            },
        },
        "backtest_card_html": '''
    <!-- Preview backtest figures source: reports/task-34-stress-unification-backtest.md -->
    <details class="backtest-toggle" open>
      <summary>Preview — new strategy backtest <span class="muted small">(Phase 1 best)</span></summary>
      <div class="backtest-toggle-body">
        <p class="muted small" style="margin-bottom: 8px;">Unified-stress MRMI preview: α=0.75, β=0.5, λ=10, buffer=0.5, threshold=0.75.</p>
        <ul class="backtest-list">
          <li><span class="bt-asset-inline">Full sample</span> avg Calmar 2.551 · cash 48.43% · switches 210</li>
          <li><span class="bt-asset-inline">SPX OOS</span> +23.53% ann · −2.86% max DD · Calmar 8.22</li>
          <li><span class="bt-asset-inline">Russell OOS</span> +31.20% ann · −6.83% max DD · Calmar 4.57</li>
          <li><span class="bt-asset-inline">Bitcoin OOS</span> +50.17% ann · −24.67% max DD · Calmar 2.03</li>
        </ul>
        <p class="muted small" style="margin-top: 8px;">Production OOS Calmar comparison: SPX 5.38, Russell 3.76, BTC 0.73. This preview is more defensive: OOS cash time 40.75% and 69 switches.</p>
      </div>
    </details>''',
    }


def build_preview(use_cache=True):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    data = fetch_all_data(use_cache=use_cache)

    print("Calculating preview indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    composite = calc_composite(gii, fincon, breadth)
    biz_cycle = calc_business_cycle(data)
    infl_ctx = calc_inflation_context(data)
    macro_ctx = calc_macro_context(data, lookback_years=3)
    mrmi_base = calc_milk_road_macro_index_unified_stress(
        composite,
        macro_ctx,
        alpha=ALPHA,
        beta=BETA,
        lambda_weight=LAMBDA_WEIGHT,
        buffer_size=BUFFER_SIZE,
        threshold=THRESHOLD,
    )

    stress_score = (mrmi_base["stress_norm"] * 10.0).clip(lower=0.0, upper=10.0)
    preview_mrmi = dict(mrmi_base)
    preview_mrmi["stress_intensity"] = mrmi_base["stress_norm"]
    preview_mrmi["stress_score"] = stress_score
    preview_mrmi["stress_growth_pressure"] = mrmi_base["growth_weakness"]
    preview_mrmi["stress_inflation_pressure"] = mrmi_base["inflation_pressure"]
    preview_mrmi["stress_score_bucket"] = stress_score.map(_stress_bucket)

    preview_meta = _preview_meta(preview_mrmi, gii)
    snap = _build_snapshot(
        data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, preview_mrmi, preview_meta
    )
    chart_json, _seasons_current = prepare_chart_data(
        data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, preview_mrmi
    )
    chart = json.loads(chart_json)

    dashboard_build._refresh_all_briefs = lambda: None
    OUTPUT.write_text(dashboard_build.render(snap, chart, data))

    latest_mrmi = snap["mrmi_combined"]
    print(f"Preview dashboard written to {OUTPUT}")
    print(
        "  ▶ Preview MRMI: "
        f"{latest_mrmi['value']:+.2f} → {latest_mrmi['state']}  "
        f"Stress {latest_mrmi['stress_score']:.1f} ({latest_mrmi['stress_score_bucket']})  "
        f"p99 {latest_mrmi['stress_p99']:.2f}"
    )
    return OUTPUT, snap


def main():
    use_cache = "--no-cache" not in sys.argv
    build_preview(use_cache=use_cache)


if __name__ == "__main__":
    main()
