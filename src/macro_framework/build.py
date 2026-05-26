#!/usr/bin/env python3
"""
build.py — Generate the macro dashboard.

Layout (from "How to Use It" slide):
  1. Banner — RISK-ON/OFF + macro-season badge
  2. MRMI history chart — see how the signal has evolved
  3. MRMI Drivers — collapsed by default, eye icon for indicator descriptions
  4. Macro Seasons — 4 season pills + intensity bars (no quadrant scatter)
  5. Reference Library — supplementary indicators (some pending data)

Reads:
  Upstream Yahoo/FRED data via macro_pipeline.py
  snapshots/<latest>.json (current values)

Writes:
  outputs/dashboard.html
"""

import glob
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

# Re-export the shared indicator pipeline so existing research/analysis scripts
# that import from `build` continue to work after the v2 dashboard became the
# default build entry point.
from macro_framework.macro_pipeline import *

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_PKL = CACHE_DIR / "raw_data.pkl"
OUTPUT = REPO_ROOT / "outputs" / "dashboard.html"
BRIEFS_DIR = REPO_ROOT / "briefs"


def _md_to_html(text: str) -> str:
    """Minimal markdown: links, **bold**, *italic*, paragraphs."""
    out = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                 r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*])\*([^*\n]+)\*(?![*])", r"<em>\1</em>", out)
    paragraphs = [p.strip() for p in out.split("\n\n") if p.strip()]
    return "".join(f"<p>{p}</p>" for p in paragraphs)


def _refresh_all_briefs():
    """Lazy-regenerate (pillar briefs first, then top) on weekly Tuesday cadence."""
    try:
        from macro_framework.weekly_briefs import generate_all_briefs
        generate_all_briefs()
    except Exception as e:
        print(f"  Warning: brief refresh failed: {e}")


def _latest_brief_dir():
    if not BRIEFS_DIR.exists():
        return None, None
    dated = []
    for p in BRIEFS_DIR.iterdir():
        if not p.is_dir():
            continue
        try:
            from datetime import datetime as _dt
            _dt.strptime(p.name, "%Y-%m-%d")
        except ValueError:
            continue
        dated.append(p)
    if not dated:
        return None, None
    dated.sort(key=lambda p: p.name)
    return dated[-1], dated[-1].name


def _load_brief_html(filename, snap_date):
    """Returns (html, date_str, is_stale). html='' if missing.
    Reads from the most-recent dated folder under briefs/."""
    latest_dir, latest_date = _latest_brief_dir()
    if not latest_dir:
        return "", None, False
    path = latest_dir / filename
    if not path.exists():
        return "", None, False
    body = path.read_text().strip()
    if not body:
        return "", None, False
    is_stale = bool(latest_date and snap_date and latest_date < snap_date)
    return _md_to_html(body), latest_date, is_stale


def latest_snapshot():
    files = sorted(glob.glob(str(SNAPSHOT_DIR / "*.json")))
    if not files:
        raise SystemExit("No snapshot found. Run python -m macro_framework.build first.")
    return json.load(open(files[-1]))



def load_raw_data():
    if not RAW_DATA_PKL.exists():
        return None
    return pd.read_pickle(RAW_DATA_PKL)


def to_list_safe(s):
    """Convert pandas Series to JSON-safe list (NaN -> None, rounded)."""
    return [round(float(v), 4) if pd.notna(v) else None for v in s]


def build_library_indicators(data, dates_index):
    """
    Compute per-indicator series + display values for the Reference Library.
    Each entry has the latest value formatted for display + a time series for charting.
    """
    YEAR = 365
    out = {}

    def add(key, label, category, raw_series, *,
            transform="raw", unit="", ref_line=None, ref_label="", desc="", notes=""):
        if raw_series is None:
            out[key] = {
                "label": label, "category": category,
                "values": None, "display": "—",
                "unit": unit, "ref_line": ref_line, "ref_label": ref_label,
                "desc": desc, "notes": notes, "available": False,
            }
            return

        s = raw_series.reindex(dates_index)
        if transform == "yoy_pct":
            display_series = s.pct_change(YEAR) * 100
            unit_str = "%"
            fmt = lambda v: f"{'+' if v >= 0 else ''}{v:.1f}%"
        elif transform == "thousands":
            display_series = s / 1000.0
            unit_str = "K"
            fmt = lambda v: f"{v:,.0f}K"
        else:  # raw
            display_series = s
            unit_str = unit
            fmt = lambda v: f"{'+' if v >= 0 and key not in {'cfnai'} else ''}{v:.2f}{unit_str}" if unit_str else f"{v:.2f}"

        latest = display_series.dropna()
        latest_v = float(latest.iloc[-1]) if len(latest) else None
        display = fmt(latest_v) if latest_v is not None else "—"

        out[key] = {
            "label": label, "category": category,
            "values": to_list_safe(display_series),
            "display": display, "unit": unit_str,
            "ref_line": ref_line, "ref_label": ref_label,
            "desc": desc, "notes": notes, "available": True,
        }

    # Liquidity
    add("m2_us", "US M2 Money Supply", "Liquidity",
        data["M2SL"] if "M2SL" in data else None,
        transform="yoy_pct", ref_line=0, ref_label="no growth",
        desc="US M2 Money Supply (FRED M2SL), shown as YoY % growth. Cross-currency global M2 would also include ECB / BOJ / PBOC — US M2 is the dominant component.",
        notes="Monetary fuel for risk assets · expanding = tailwind")

    # Activity
    add("ism_mfg", "ISM Manufacturing PMI", "Activity",
        None,  # not on FRED
        desc="ISM Manufacturing PMI is no longer redistributed via FRED (ISM licensing). Could substitute Empire State or Philly Fed manufacturing surveys as proxies.",
        notes="Data pending — ISM doesn't redistribute via FRED")

    add("gdpnow", "Atlanta Fed GDPNow", "Activity",
        data["GDPNOW"] if "GDPNOW" in data else None,
        transform="raw", unit="%", ref_line=2.0, ref_label="trend ~2%",
        desc="Atlanta Fed GDPNow — real-time nowcast of current-quarter Real GDP growth (annualized %). Updates several times per quarter as new data prints.",
        notes="Closes the publication-lag gap on official GDP")

    add("cfnai", "CFNAI", "Activity",
        data["CFNAI"] if "CFNAI" in data else None,
        transform="raw", ref_line=0, ref_label="trend",
        desc="Chicago Fed National Activity Index — composite of 85 monthly US activity indicators, normalized to mean 0. Above 0 = above-trend growth, below 0 = below-trend.",
        notes="Comprehensive cross-sector US activity composite")

    add("indpro", "Industrial Production", "Activity",
        data["INDPRO"] if "INDPRO" in data else None,
        transform="yoy_pct", ref_line=0, ref_label="no growth",
        desc="Industrial Production index (manufacturing + mining + utilities), shown as YoY % change. Long historical series, biased toward goods-producing sectors.",
        notes="Goods-side activity · partial overlap with copper")

    add("housing_starts", "Housing Starts", "Activity",
        data["HOUST"] if "HOUST" in data else None,
        transform="thousands", ref_line=None,
        desc="Housing Starts (thousands of units, SAAR). Rate-sensitive — tends to lead the cycle when the Fed pivots.",
        notes="Rate-sensitive · leads the cycle on Fed pivots")

    add("permits", "Building Permits", "Activity",
        data["PERMIT"] if "PERMIT" in data else None,
        transform="thousands", ref_line=None,
        desc="Building Permits (thousands of units, SAAR). Leads housing starts by 1–2 months — even more forward-looking on construction activity.",
        notes="Permits lead starts by 1–2 months")

    # Labor
    add("initial_claims", "Initial Jobless Claims", "Labor",
        data["ICSA"] if "ICSA" in data else None,
        transform="thousands", ref_line=None,
        desc="Initial unemployment insurance claims (weekly, thousands). Highest-frequency real-economy signal in the framework — recession indicator when the 4-week moving average rises sharply.",
        notes="Weekly · most reliable recession indicator")

    add("continuing_claims", "Continuing Jobless Claims", "Labor",
        data["CCSA"] if "CCSA" in data else None,
        transform="thousands", ref_line=None,
        desc="Continuing unemployment insurance claims (weekly, thousands). Tracks how long workers stay unemployed — rising trend can signal labor-market deterioration even when initial claims are low.",
        notes="Companion to initial claims · tracks duration of unemployment")

    return out



def macro_backdrop(re_score, inf_dir):
    """
    Map the (Real Economy Score, Inflation Direction) pair to a qualitative
    backdrop label + empirical conditioning advice for green MRMI flips.
    Bucket boundaries match the backtest analysis (sign of each axis).
    """
    if re_score is None or inf_dir is None:
        return None
    if re_score >= 0 and inf_dir < 0:
        return {
            "label": "Tailwind",
            "tag": "Reflation-like", "color": "#4CAF50",
            "summary": "Real economy expanding, inflation cooling. Historically the strongest setup for green MRMI flips (+6.0% SPX 90d, 98% hit).",
        }
    if re_score >= 0 and inf_dir >= 0:
        return {
            "label": "Mixed",
            "tag": "Expansion-like", "color": "#FF8C00",
            "summary": "Economy expanding but inflation rising. Mixed setup for green flips (+2.0% SPX 90d, 68% hit) — late-cycle dynamics.",
        }
    if re_score < 0 and inf_dir < 0:
        return {
            "label": "Setup-Building",
            "tag": "Disinflation-like", "color": "#4DA8DA",
            "summary": "Economy weakening but inflation falling — Fed pivot setup. Green flips here historically perform well (+5.4% SPX 90d, 80% hit).",
        }
    return {
        "label": "Headwind",
        "tag": "Stagflation-like", "color": "#E84B5A",
        "summary": "Economy weakening AND inflation rising. Worst setup for green flips: −5.1% SPX 90d, only 27% hit historically. Fade green signals here.",
    }



def driver_label(value):
    if value > 0.75:  return ("Strong", "#4CAF50")
    if value > 0:     return ("Positive", "#8BC34A")
    if value > -0.75: return ("Soft", "#FF9800")
    return ("Weak", "#E84B5A")


def fmt_signed(v, decimals=2):
    if v is None: return "—"
    return f"{'+' if v >= 0 else ''}{v:.{decimals}f}"


def strip_html(s):
    return re.sub(r'<[^>]+>', '', s) if s else ""


def _escape(s):
    return html.escape(str(s), quote=True)


def _fmt_growth_current(row):
    v = row.get("current")
    if v is None:
        return "—"
    unit = row.get("unit")
    if unit == "%":
        return f"{v:+.2f}%"
    if unit == "pct":
        return f"{v * 100:+.1f}%"
    if unit == "pp":
        return f"{v:+.2f}pp"
    if unit == "index":
        return f"{v:+.2f}"
    return f"{v:.2f}"


def _fmt_growth_trend(row, key):
    v = row.get(key)
    if v is None:
        return "—"
    if row.get("trend_type") == "roc":
        return f"{v:+.1f}%"
    if row.get("unit") == "pct":
        return f"{v * 100:+.1f}pp"
    if row.get("unit") in {"%", "pp"}:
        return f"{v:+.2f}pp"
    return f"{v:+.2f}"


def _fmt_growth_z(v):
    if v is None:
        return "—"
    return f"{v:+.2f}"


def _growth_z_class(v):
    if v is None:
        return "neutral"
    return "pos" if v > 0 else "neg" if v < 0 else "neutral"


def _growth_impulse_drilldown_html(payload):
    rows = payload.get("rows") or []
    if not rows:
        return ""
    brief = payload.get("brief") or []
    brief_html = "".join(f"<p>{_escape(sentence)}</p>" for sentence in brief)
    options_html = "".join(
        f'<option value="{_escape(row.get("key", ""))}">{_escape(row.get("label", ""))}</option>'
        for row in rows
    )
    row_html = []
    for row in rows:
        z_now = row.get("z_21d")
        z7 = row.get("z_change_7d")
        z30 = row.get("z_change_30d")
        label = _escape(row.get("label", ""))
        explanation = _escape(row.get("explanation", ""))
        row_html.append(f'''
          <tr class="growth-input-row" data-growth-key="{_escape(row.get("key", ""))}">
            <td>
              <div class="growth-input-name">
                <span class="sc-label">{label}</span>
                <span class="growth-info-icon" tabindex="0" role="img" aria-label="{label}: {explanation}" data-tooltip="{explanation}">i</span>
              </div>
              <div class="muted small">{_escape(row.get("source", ""))}</div>
            </td>
            <td><span class="muted small">{_escape(row.get("group", ""))}</span></td>
            <td><span class="val {_growth_z_class(z7)}">{_fmt_growth_z(z7)}</span></td>
            <td><span class="val {_growth_z_class(z30)}">{_fmt_growth_z(z30)}</span></td>
            <td><span class="val {_growth_z_class(z_now)}">{_fmt_growth_z(z_now)}</span></td>
          </tr>''')
    return f'''
      <details class="growth-drilldown">
        <summary>View Growth Impulses inputs <span class="muted small">· sorted by 7-day contribution</span></summary>
        <div class="growth-drilldown-body">
          <p class="drivers-desc">{_escape(payload.get("intro", ""))}<br><span class="muted small">{_escape(payload.get("sort_note", ""))}</span></p>
          <div class="growth-mini-brief">
            <div class="pillar-brief-eyebrow">Growth Impulses mini-brief</div>
            {brief_html}
          </div>
          <table class="growth-inputs-table">
            <thead><tr>
              <th>Input</th><th>Group</th>
              <th title="Fast z-score change over the latest 7 trading days — main sort key">7d zΔ</th>
              <th title="Fast z-score change over the latest 30 trading days — durability check">30d zΔ</th>
              <th title="Current clipped z-score of the fast ROC leg">Current z</th>
            </tr></thead>
            <tbody>{''.join(row_html)}</tbody>
          </table>
          <div class="growth-input-chart-panel">
            <div class="growth-input-chart-header">
              <span class="growth-input-chart-title">Raw input history</span>
              <select id="growth-input-select" aria-label="Growth Impulses input chart">{options_html}</select>
            </div>
            <div class="chart-wrap growth-input-chart-wrap"><canvas id="chart-growth-input"></canvas></div>
            <div id="growth-input-chart-desc" class="chart-desc"></div>
          </div>
        </div>
      </details>'''

def _driver_drilldown_html(payload, *, dom_key, summary_label, brief_label, chart_label):
    rows = payload.get("rows") or []
    if not rows:
        return ""
    brief = payload.get("brief") or []
    brief_html = "".join(f"<p>{_escape(sentence)}</p>" for sentence in brief)
    options_html = "".join(
        f'<option value="{_escape(row.get("key", ""))}">{_escape(row.get("label", ""))}</option>'
        for row in rows
    )
    row_html = []
    for row in rows:
        z_now = row.get("z_21d")
        z7 = row.get("z_change_7d")
        z30 = row.get("z_change_30d")
        label = _escape(row.get("label", ""))
        explanation = _escape(row.get("explanation", ""))
        row_html.append(f"""
          <tr class="driver-input-row" data-driver-drilldown="{_escape(dom_key)}" data-input-key="{_escape(row.get("key", ""))}">
            <td>
              <div class="growth-input-name">
                <span class="sc-label">{label}</span>
                <span class="growth-info-icon" tabindex="0" role="img" aria-label="{label}: {explanation}" data-tooltip="{explanation}">i</span>
              </div>
              <div class="muted small">{_escape(row.get("source", ""))}</div>
            </td>
            <td><span class="muted small">{_escape(row.get("group", ""))}</span></td>
            <td><span class="val {_growth_z_class(z7)}">{_fmt_growth_z(z7)}</span></td>
            <td><span class="val {_growth_z_class(z30)}">{_fmt_growth_z(z30)}</span></td>
            <td><span class="val {_growth_z_class(z_now)}">{_fmt_growth_z(z_now)}</span></td>
          </tr>""")
    return f"""
      <details class="growth-drilldown driver-drilldown" data-driver-drilldown="{_escape(dom_key)}">
        <summary>View {summary_label} inputs <span class="muted small">· sorted by 7-day contribution</span></summary>
        <div class="growth-drilldown-body">
          <p class="drivers-desc">{_escape(payload.get("intro", ""))}<br><span class="muted small">{_escape(payload.get("sort_note", ""))}</span></p>
          <div class="growth-mini-brief">
            <div class="pillar-brief-eyebrow">{brief_label} mini-brief</div>
            {brief_html}
          </div>
          <table class="growth-inputs-table">
            <thead><tr>
              <th>Input</th><th>Group</th>
              <th title="Input z-score change over the latest 7 trading days — main sort key">7d zΔ</th>
              <th title="Input z-score change over the latest 30 trading days — durability check">30d zΔ</th>
              <th title="Current z-score used in the driver composite">Current z</th>
            </tr></thead>
            <tbody>{''.join(row_html)}</tbody>
          </table>
          <div class="growth-input-chart-panel">
            <div class="growth-input-chart-header">
              <span class="growth-input-chart-title">Raw input history</span>
              <select id="{_escape(dom_key)}-input-select" aria-label="{_escape(chart_label)} input chart">{options_html}</select>
            </div>
            <div class="chart-wrap growth-input-chart-wrap"><canvas id="chart-{_escape(dom_key)}-input"></canvas></div>
            <div id="{_escape(dom_key)}-input-chart-desc" class="chart-desc"></div>
          </div>
        </div>
      </details>"""


def _make_scale_bar(mrmi_value, state_color):
    """Horizontal bar showing MRMI's cash / caution / long posture zones."""
    if mrmi_value is None:
        return ""
    SCALE_MIN, SCALE_MAX = -3.0, 5.0
    clamped = max(SCALE_MIN, min(SCALE_MAX, mrmi_value))
    pct = (clamped - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100
    cash_pct = (MRMI_CASH_THRESHOLD - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100
    long_pct = (MRMI_LONG_THRESHOLD - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100
    caution_width = long_pct - cash_pct
    return f"""
  <div class="scale-bar">
    <div class="scale-track">
      <div class="scale-zone-cash" style="width: {cash_pct}%;"></div>
      <div class="scale-zone-caution" style="width: {caution_width}%;"></div>
      <div class="scale-zone-long" style="width: {100 - long_pct}%;"></div>
      <div class="scale-threshold" style="left: {cash_pct}%;"></div>
      <div class="scale-threshold" style="left: {long_pct}%;"></div>
      <div class="scale-marker" style="left: {pct}%; background: {state_color}; box-shadow: 0 0 0 4px {state_color}33;"></div>
    </div>
    <div class="scale-axis">
      <span style="left: 0%;">−3</span>
      <span style="left: {cash_pct}%; color: #888;">−0.50 · cash</span>
      <span style="left: {long_pct}%; color: #888;">+0.25 · long</span>
      <span style="left: 100%;">+5</span>
    </div>
    <div class="scale-legend">
      <span class="scale-cash-label">CASH · 0%</span>
      <span class="scale-caution-label">CAUTION · 75%</span>
      <span class="scale-long-label">LONG · 100%</span>
    </div>
  </div>"""


def render(snap, chart, raw_data=None):
    # === NEW unified Milk Road Macro Index (MRMI) ===
    mrmi_combined = snap.get("mrmi_combined") or {}
    mrmi_value = mrmi_combined.get("value")
    mrmi_state = mrmi_combined.get("state")  # "LONG", "CAUTION", or "CASH"
    mmi_value = mrmi_combined.get("momentum")
    macro_buffer = mrmi_combined.get("macro_buffer")
    stress_intensity = mrmi_combined.get("stress_intensity") or 0.0
    stress_score = mrmi_combined.get("stress_score")
    stress_score_label = (mrmi_combined.get("stress_score_bucket") or "watch").upper()
    preview_meta = snap.get("preview") or {}

    # Legacy MMI (formerly called MRMI in old code) — now the underlying momentum signal
    mmi = snap["mrmi"]
    state = mmi["state"]  # green/red of the momentum signal
    components = snap["components"]
    gii, breadth, fincon = components["gii_fast"], components["breadth"], components["fincon"]

    # Macro context — Real Economy Composite + Inflation Direction
    macro = snap.get("macro") or {}
    re_score = macro.get("real_economy_score")
    inf_dir = macro.get("inflation_dir_pp")
    core_cpi_yoy_pct = macro.get("core_cpi_yoy_pct")
    re_components = macro.get("real_economy_components") or {}
    re_raw = macro.get("raw") or {}
    backdrop = macro_backdrop(re_score, inf_dir) or {
        "label": "—", "tag": "—", "color": "#666",
        "summary": "Macro context data not yet available.",
    }
    underliers = snap.get("underliers", {})

    # Chart data — embed time series as JSON for Chart.js to consume
    sc = chart["scorecard"]
    drivers_meta = {
        key: {
            "label": sc[key]["label"],
            "values": sc[key]["values"],
            "green_above": sc[key].get("green_above", True),
            "desc": sc[key].get("desc", ""),
        }
        for key in ("gii_fast", "breadth", "fincon")
    }
    # Macro context series for Real Economy + Inflation Direction
    macro_chart = chart.get("macro_ctx") or {}
    re_score_series   = macro_chart.get("real_economy_score", [])
    inf_dir_series    = macro_chart.get("inflation_dir_pp", [])
    core_cpi_series   = macro_chart.get("core_cpi_yoy_pct", [])
    re_components_series = macro_chart.get("components", {})
    re_raw_series     = macro_chart.get("raw", {})

    # Real Economy components — used for the Macro Drivers scorecard
    macro_drivers_meta = {
        "pce": {
            "label": "Real PCE YoY",
            "values": re_raw_series.get("pce_yoy", []),
            "type": "pct_signed", "target": 0.0,
            "above_label": "expanding", "below_label": "contracting",
            "above_color": "#4CAF50", "below_color": "#E84B5A",
            "desc": "Real Personal Consumption Expenditures YoY % change (FRED PCEC96). Consumer spending is ~70% of US GDP. Monthly cadence — much more responsive than quarterly GDP.",
        },
        "sahm": {
            "label": "Sahm Rule",
            "values": re_raw_series.get("sahm_rule", []),
            "type": "pct_signed", "target": 0.5,
            "above_label": "above recession threshold", "below_label": "below recession threshold",
            "above_color": "#E84B5A", "below_color": "#4CAF50",
            "desc": "Sahm Rule = (3-month MA of unemployment rate) − (12-month low). Has crossed +0.5pp at the start of every US recession since 1970. Forward-looking labor stress signal.",
        },
        "income": {
            "label": "Real Personal Income YoY",
            "values": re_raw_series.get("income_yoy", []),
            "type": "pct_signed", "target": 0.0,
            "above_label": "rising", "below_label": "falling",
            "above_color": "#4CAF50", "below_color": "#E84B5A",
            "desc": "Real Personal Income YoY % change (FRED RPI). Tracks household income trajectory in inflation-adjusted terms — monthly cadence.",
        },
        "gdpnow": {
            "label": "Atlanta Fed GDPNow",
            "values": re_raw_series.get("gdpnow", []),
            "type": "pct", "target": 2.0,
            "above_label": "above trend ~2%", "below_label": "below trend ~2%",
            "above_color": "#4CAF50", "below_color": "#E84B5A",
            "desc": "Atlanta Fed GDPNow — real-time nowcast of current-quarter Real GDP growth (annualized %). Updates several times per quarter as new data prints.",
        },
    }

    # Per-driver descriptions (plain text for tooltips)
    sc = chart["scorecard"]
    gii_desc = strip_html(sc["gii_fast"]["desc"])
    breadth_desc = strip_html(sc["breadth"]["desc"])
    fincon_desc = strip_html(sc["fincon"]["desc"])

    # === Headline action driven by NEW MRMI ===
    is_long = mrmi_state == "LONG"
    is_caution = mrmi_state == "CAUTION"
    state_color = "#4CAF50" if is_long else "#cdaa6a" if is_caution else "#E84B5A"
    state_label = "LONG" if is_long else "CAUTION" if is_caution else "CASH"
    state_subtitle = "100% exposure" if is_long else "75% exposure" if is_caution else "0% exposure"
    mrmi_value_str = f"{'+' if (mrmi_value or 0) >= 0 else ''}{mrmi_value:.2f}" if mrmi_value is not None else "—"

    # State-aware story for the banner — translates the numbers into plain English
    mmi_state_word = "healthy" if state == "green" else "weak"
    if (stress_score or 0) >= BUCKET_CUTOFF_BUILDING_ELEV:
        macro_state_word = "elevated stress"
    elif (stress_score or 0) >= BUCKET_CUTOFF_CALM_WATCH:
        macro_state_word = "stress building"
    else:
        macro_state_word = "calm stress"

    if is_long and (stress_score or 0) < BUCKET_CUTOFF_CALM_WATCH and state == "green":
        banner_story = "Market signals are healthy and macro stress is calm. Framework supports full risk exposure."
    elif is_long:
        banner_story = f"Market signals are healthy enough for full exposure. Macro shows {macro_state_word}, but not enough to cut risk."
    elif is_caution:
        banner_story = "MRMI is in the investor caution zone. Stay invested, but reduce aggressiveness to 75% exposure and pay attention."
    else:  # CASH
        banner_story = "Market signals and macro conditions are hostile enough to prioritize capital preservation at 0% exposure."

    # AI-generated briefs: pillar briefs first, then top brief that consumes them.
    # Lazy weekly cadence (regenerates if latest archive folder is older than most recent Tuesday).
    # Briefs persist forever in briefs/YYYY-MM-DD/ — past weeks are preserved for review.
    _refresh_all_briefs()
    commentary_html, commentary_date, commentary_stale = _load_brief_html("top.md", snap.get("date"))
    market_brief_html, market_brief_date, market_brief_stale = _load_brief_html("market.md", snap.get("date"))
    economy_brief_html, economy_brief_date, economy_brief_stale = _load_brief_html("economy.md", snap.get("date"))

    # MMI (momentum) sub-signal coloring
    mmi_color = "#4CAF50" if state == "green" else "#E84B5A"
    mmi_label = "GREEN" if state == "green" else "RED"
    mmi_value_str = f"{'+' if (mmi_value or 0) >= 0 else ''}{mmi_value:.2f}" if mmi_value is not None else "—"

    # Macro Stress sub-signal coloring
    stress_score_color = {
        "CALM": "#4CAF50",
        "WATCH": "#cdaa6a",
        "BUILDING": "#FF8C00",
        "ELEVATED": "#E84B5A",
    }.get(stress_score_label, "#cdaa6a")
    stress_color = stress_score_color
    stress_value_str = f"{float(stress_score):.1f}" if stress_score is not None else "—"
    stress_momentum_label = preview_meta.get("stress_momentum_label")
    stress_momentum_color = preview_meta.get("stress_momentum_color", "#888")
    stress_momentum_chip = (
        f'\n      <span class="macro-stress-momentum-chip" style="color:{stress_momentum_color}; '
        f'border-color:{stress_momentum_color}55;">{stress_momentum_label}</span>'
        if stress_momentum_label else ""
    )
    stress_panel_tip = preview_meta.get("stress_panel_tip") or (
        "<p><strong>What you're seeing:</strong> Martin's unified macro-stress score on a 0–10 scale. It is calm by default, rises when growth weakens or inflation accelerates, and builds fastest when both hit together.</p><p><strong>MRMI buffer:</strong> this same stress score now erodes the macro buffer used in the production MRMI strategy.</p><p><strong>Inputs below:</strong> the stress-inputs panel shows the raw axes: Real Economy Score and Inflation Direction Δ6m.</p>"
    )
    stress_panel_subtitle = preview_meta.get("stress_panel_subtitle") or (
        "Stagflation pressure — growth weakness × inflation rising. Calm by default, builds when both factors hit."
    )
    stress_reading_label = preview_meta.get("stress_reading_label") or "0–10 score"
    stress_inputs_title = preview_meta.get("stress_inputs_title") or "Real Economy Score · Inflation Direction Δ6m"
    stress_growth_label = preview_meta.get("stress_growth_label") or "Real Economy Score"
    stress_inflation_label = preview_meta.get("stress_inflation_label") or "Inflation Direction Δ6m"
    stress_cutoff_calm_watch = preview_meta.get("stress_cutoff_calm_watch", BUCKET_CUTOFF_CALM_WATCH)
    stress_cutoff_watch_building = preview_meta.get("stress_cutoff_watch_building", BUCKET_CUTOFF_WATCH_BUILDING)
    stress_cutoff_building_elev = preview_meta.get("stress_cutoff_building_elev", BUCKET_CUTOFF_BUILDING_ELEV)
    preview_banner = ""
    if preview_meta:
        preview_banner = (
            '<div class="preview-banner">PREVIEW BUILD · '
            f'{preview_meta.get("label", "new strategy formula")} · output only, production dashboard unchanged</div>'
        )
    backtest_card_html = preview_meta.get("backtest_card_html") or '''
    <!-- Backtest figures source: reports/task-35-investor-grade-thresholds.md recommendation -->
    <details class="backtest-toggle">
      <summary>How well does this work historically? <span class="muted small">(click)</span></summary>
      <div class="backtest-toggle-body">
        <p class="muted small" style="margin-bottom: 8px;">Full-sample investor-grade posture backtest (2017–2026), no leverage:</p>
        <ul class="backtest-list">
          <li><span class="bt-asset-inline">SPX</span> +20.9% annual return · max drawdown −7.3% · Calmar 2.88</li>
          <li><span class="bt-asset-inline">Russell 2000</span> +25.6% annual return · max drawdown −10.0% · Calmar 2.57</li>
          <li><span class="bt-asset-inline">Bitcoin</span> +39.3% annual return · max drawdown −58.6% · Calmar 0.67</li>
        </ul>
        <p class="muted small" style="margin-top: 8px;">Average exposure 62.9% of the time (cash 27.9%, caution 36.6%).</p>
      </div>
    </details>'''

    g_label, g_color = driver_label(gii)
    b_label, b_color = driver_label(breadth)
    f_label, f_color = driver_label(fincon)

    # Reference Library — wire from raw data where available
    library = build_library_indicators(raw_data, pd.DatetimeIndex(chart["dates"])) if raw_data is not None else {}

    library_rows_html_parts = []
    for key, meta in library.items():
        avail = meta.get("available")
        row_class = "lib-row" if avail else "lib-row unavailable"
        click = f"toggleLib('{key}')" if avail else ""
        info_html = (
            f'<span class="info-icon"><svg width="13" height="13" viewBox="0 0 14 14" fill="none">'
            f'<circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/>'
            f'<circle cx="7" cy="4" r="0.9" fill="currentColor"/>'
            f'<line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>'
            f'</svg><span class="tip-pop">{meta["desc"]}</span></span>'
        ) if meta.get("desc") else ""
        library_rows_html_parts.append(f'''<tr class="{row_class}" {f'onclick="{click}"' if click else ''}>
            <td><span class="ind-name">{meta["label"]}</span>{info_html}</td>
            <td class="muted small">{meta["category"]}</td>
            <td class="value mono">{meta["display"]}</td>
            <td class="muted small">{meta["notes"]}</td>
        </tr>''')
        if avail:
            library_rows_html_parts.append(
                f'<tr class="expanded-row" id="exp-lib-{key}"><td colspan="4">'
                f'<div class="chart-wrap"><canvas id="canvas-lib-{key}"></canvas></div>'
                f'<div class="chart-desc">{meta["desc"]}</div>'
                f'</td></tr>'
            )
    library_rows_html = "\n".join(library_rows_html_parts)

    library_payload = {
        key: {
            "label": m["label"],
            "values": m["values"],
            "unit": m["unit"],
            "ref_line": m["ref_line"],
            "ref_label": m["ref_label"],
        }
        for key, m in library.items() if m.get("values")
    }

    mrmi_combined_chart = chart.get("mrmi_combined") or {}
    chart_payload = json.dumps({
        "dates": chart["dates"],
        "composite": chart["composite"]["value"],  # MMI (the underlying momentum)
        "mrmi_combined": {
            "value":                     mrmi_combined_chart.get("value", []),
            "momentum":                  mrmi_combined_chart.get("momentum", []),
            "stress_intensity":          mrmi_combined_chart.get("stress_intensity", []),
            "stress_score":              mrmi_combined_chart.get("stress_score", []),
            "growth_weakness":           mrmi_combined_chart.get("growth_weakness", []),
            "inflation_pressure_raw":    mrmi_combined_chart.get("inflation_pressure_raw", []),
            "stress_score_bucket":       mrmi_combined_chart.get("stress_score_bucket", []),
            "macro_buffer":              mrmi_combined_chart.get("macro_buffer", []),
        },
        "spx": chart.get("spx", []),
        "iwm": chart.get("iwm", []),
        "btc": chart.get("btc", []),
        "drivers": drivers_meta,
        "growth_impulse": chart.get("growth_impulse") or {},
        "sector_breadth": chart.get("sector_breadth") or {},
        "financial_conditions": chart.get("financial_conditions") or {},
        "macro": {
            "real_economy_score": re_score_series,
            "inflation_dir_pp":   inf_dir_series,
            "core_cpi_yoy_pct":   core_cpi_series,
            "components":         re_components_series,
        },
        "macro_drivers": macro_drivers_meta,
        "library": library_payload,
        "preview": preview_meta.get("chart") or {},
    }, separators=(",", ":"))

    growth_drilldown_html = _growth_impulse_drilldown_html(
        chart.get("growth_impulse") or snap.get("growth_impulse_drilldown") or {}
    )
    breadth_drilldown_html = _driver_drilldown_html(
        chart.get("sector_breadth") or snap.get("sector_breadth_drilldown") or {},
        dom_key="breadth",
        summary_label="Sector Breadth",
        brief_label="Sector Breadth",
        chart_label="Sector Breadth",
    )
    fincon_drilldown_html = _driver_drilldown_html(
        chart.get("financial_conditions") or snap.get("financial_conditions_drilldown") or {},
        dom_key="fincon",
        summary_label="Financial Conditions",
        brief_label="Financial Conditions",
        chart_label="Financial Conditions",
    )
    info_svg = '<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="4" r="0.9" fill="currentColor"/><line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Macro Dashboard v2 · {snap["date"]}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', system-ui, sans-serif;
    background: #0a0a0a; color: #ccc;
    padding: 24px 32px 48px; max-width: 1280px; margin: 0 auto;
  }}
  .mono {{ font-family: 'SF Mono', Menlo, monospace; }}
  .muted {{ color: #666; }}
  .small {{ font-size: 13px; }}

  .meta-bar {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 18px; font-size: 13px; color: #555;
  }}
  .meta-bar .brand {{ color: #888; font-weight: 600; letter-spacing: 0.5px; }}

  /* SECTION TITLE */
  .section-title {{
    font-size: 19px; letter-spacing: -0.3px;
    color: #e0e0e0; margin: 56px 0 14px; font-weight: 600;
    display: flex; align-items: center; gap: 14px;
    text-transform: none;
  }}
  .step-num {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 30px; height: 30px; flex: 0 0 30px;
    background: #1a1a1a; border: 1px solid #2a2a2a;
    color: #888; font-size: 13px; font-weight: 600;
    border-radius: 50%; letter-spacing: 0;
    font-family: 'SF Mono', Menlo, monospace;
  }}
  .pillar-chip {{
    display: inline-block; padding: 2px 9px; border-radius: 4px;
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px;
    font-weight: 600; margin-left: auto;
  }}
  .pillar-chip.market  {{ background: rgba(255,255,255,0.06); color: #ccc; border: 1px solid #2a2a2a; }}
  .pillar-chip.economy {{ background: rgba(205,170,106,0.10); color: #cdaa6a; border: 1px solid rgba(205,170,106,0.25); }}
  .lookback-tabs {{
    display: inline-flex; align-items: center; gap: 4px;
    text-transform: none; letter-spacing: normal;
  }}
  .lookback-tabs .lookback-label {{ color: #555; font-size: 10px; margin-right: 6px; font-weight: 500; }}
  .lookback-tabs button {{
    background: #161616; border: 1px solid #222; color: #777;
    font-size: 10px; padding: 3px 9px; border-radius: 4px;
    cursor: pointer; font-family: inherit; font-weight: 600;
    letter-spacing: 0.5px;
  }}
  .lookback-tabs button:hover {{ color: #ccc; border-color: #333; }}
  .lookback-tabs button.active {{ color: #fff; background: #1f1f1f; border-color: #444; }}

  /* 1 — BANNER */
  .banner {{
    display: grid; grid-template-columns: 2fr 1fr; gap: 16px;
    background: #111; border: 1px solid #222; border-radius: 12px;
    padding: 24px 32px; margin-bottom: 24px;
    border-left: 6px solid {state_color};
  }}
  .banner-state {{
    font-size: 52px; font-weight: 700; color: {state_color}; line-height: 1;
    letter-spacing: -1.5px;
  }}
  .banner-mrmi {{ font-size: 15px; color: #888; margin-top: 12px; }}
  .banner-mrmi .val {{ color: #fff; font-weight: 600; }}
  .banner-quadrant {{
    background: #181818; border-radius: 8px; padding: 16px 20px;
    border-left: 4px solid {backdrop['color']};
    display: flex; flex-direction: column; justify-content: center;
  }}
  .banner-quadrant .label {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px;
    color: #666; margin-bottom: 4px;
  }}
  .banner-quadrant .name {{ font-size: 26px; font-weight: 700; color: {backdrop['color']}; }}
  .banner-quadrant .axes {{ font-size: 13px; color: #888; margin-top: 4px; }}

  /* Hero (the headline area) */
  .hero {{
    margin-bottom: 36px; padding: 8px 4px 0;
  }}
  .hero-eyebrow {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px;
    color: #555; font-weight: 500; margin-bottom: 18px;
  }}
  .hero-grid {{
    display: grid; grid-template-columns: minmax(0, 1fr) auto;
    gap: 48px; align-items: start;
  }}
  .hero-main {{ min-width: 0; }}
  .hero-row {{
    display: flex; align-items: baseline; gap: 28px;
    margin-bottom: 24px;
  }}
  .hero-value {{
    font-size: 80px; font-weight: 600; line-height: 1;
    letter-spacing: -3px;
  }}
  .hero-action-label {{
    font-size: 22px; font-weight: 600; letter-spacing: -0.4px;
    line-height: 1.1;
  }}
  .hero-action-sub {{
    font-size: 13px; color: #777; margin-top: 4px;
  }}
  .hero-story {{
    margin: 22px 0 0; color: #999;
    font-size: 14px; line-height: 1.55;
  }}
  .hero-story-ai {{
    margin: 24px 0 0; color: #c8c8c8;
    font-size: 14px; line-height: 1.6;
  }}
  .hero-story-ai p {{ margin: 0 0 10px; }}
  .hero-story-ai p:last-child {{ margin-bottom: 0; }}
  .hero-story-ai a {{ color: #cdaa6a; text-decoration: none; border-bottom: 1px dotted #6c5a36; }}
  .hero-story-ai a:hover {{ color: #e6c98a; border-bottom-color: #cdaa6a; }}
  .hero-story-eyebrow {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.8px;
    color: #555; font-weight: 500; margin-bottom: 10px;
  }}
  /* Right-column pillars panel — preview of the two signals behind MRMI */
  .hero-pillars {{
    border-left: 1px solid #1f1f1f;
    padding: 4px 0 4px 32px;
    min-width: 240px;
  }}
  .hero-pillars-title {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.8px;
    color: #555; font-weight: 500; margin-bottom: 14px;
  }}
  .hero-pillar {{
    display: flex; align-items: baseline; justify-content: space-between;
    gap: 16px; padding: 10px 0;
  }}
  .hero-pillar + .hero-pillar {{ border-top: 1px solid #161616; }}
  .hero-pillar-name {{ font-size: 13px; color: #aaa; }}
  .hero-pillar-right {{ display: flex; align-items: baseline; gap: 10px; }}
  .hero-pillar-state {{
    font-size: 13px; font-weight: 600; letter-spacing: 0.4px;
  }}
  .hero-pillar-value {{
    font-size: 13px; color: #777;
  }}
  .hero-pillar-note {{
    margin-top: 14px; font-size: 11px; color: #555; line-height: 1.5;
  }}
  @media (max-width: 880px) {{
    .hero-grid {{ grid-template-columns: 1fr; gap: 28px; }}
    .hero-pillars {{ border-left: none; border-top: 1px solid #1f1f1f; padding: 20px 0 0; }}
  }}

  /* Scale bar — visual showing where MRMI sits on its scale */
  .scale-bar {{
    max-width: 720px; margin-top: 4px;
  }}
  .scale-track {{
    position: relative; height: 8px; border-radius: 4px;
    background: #1a1a1a; display: flex; overflow: hidden;
  }}
  .scale-zone-cash {{
    background: linear-gradient(to right, #E84B5A22, #E84B5A11);
    height: 100%;
  }}
  .scale-zone-caution {{
    background: linear-gradient(to right, #cdaa6a22, #cdaa6a18);
    height: 100%;
  }}
  .scale-zone-long {{
    background: linear-gradient(to right, #4CAF5011, #4CAF5022);
    height: 100%;
  }}
  .scale-threshold {{
    position: absolute; top: -3px; bottom: -3px;
    width: 1px; background: #444;
  }}
  .scale-marker {{
    position: absolute; top: -4px; width: 16px; height: 16px;
    border-radius: 50%; transform: translateX(-50%);
    transition: left 0.3s;
  }}
  .scale-axis {{
    position: relative; height: 14px; margin-top: 8px;
    font-size: 10px; color: #555;
    font-family: 'SF Mono', Menlo, monospace;
  }}
  .scale-axis span {{ position: absolute; transform: translateX(-50%); }}
  .scale-axis span:first-child {{ transform: translateX(0); }}
  .scale-axis span:last-child {{ transform: translateX(-100%); }}
  .scale-legend {{
    display: flex; justify-content: space-between;
    margin-top: 4px; font-size: 10px; letter-spacing: 1.5px;
    text-transform: uppercase; font-weight: 600;
  }}
  .scale-cash-label {{ color: #E84B5A88; }}
  .scale-caution-label {{ color: #cdaa6a99; }}
  .scale-long-label {{ color: #4CAF5088; }}

  /* Composition (just two pillars, no MRMI repeat) */
  .comp {{
    margin-bottom: 36px;
    padding-top: 26px; border-top: 1px solid #1a1a1a;
  }}
  .comp-header {{
    display: flex; justify-content: space-between; align-items: baseline;
    margin-bottom: 22px;
  }}
  .comp-eyebrow {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px;
    color: #555; font-weight: 500;
  }}
  .comp-formula {{
    font-size: 11px; color: #444;
    font-family: 'SF Mono', Menlo, monospace; letter-spacing: 0.5px;
  }}
  .comp-rows {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 36px;
  }}
  .comp-row {{
    display: grid;
    grid-template-columns: auto auto 1fr;
    gap: 18px; align-items: baseline;
  }}
  .comp-row-label {{
    grid-column: 1 / -1;
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px;
    color: #888; font-weight: 500; margin-bottom: 6px;
  }}
  .comp-row-value {{
    font-size: 36px; font-weight: 600; line-height: 1;
    letter-spacing: -1px;
  }}
  .comp-row-state {{
    font-size: 11px; font-weight: 500;
    text-transform: uppercase; letter-spacing: 1.2px;
    align-self: center;
  }}
  .comp-row-meta {{
    grid-column: 1 / -1;
    font-size: 12px; color: #666;
    line-height: 1.5; margin-top: 10px;
  }}
  .comp-rule {{
    margin: 26px 0 0; padding-top: 18px;
    border-top: 1px dashed #1f1f1f;
    font-size: 12px; color: #666; line-height: 1.5;
  }}
  .section-intro {{
    color: #aaa; font-size: 13px; line-height: 1.55;
    margin: 0 0 16px 0;
  }}
  .section-intro strong {{ color: #ddd; }}

  /* 2 — MRMI CHART */
  .mrmi-chart {{
    background: #111; border: 1px solid #222; border-radius: 10px;
    padding: 18px 24px 18px; margin-bottom: 24px;
  }}
  .mrmi-chart-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 6px;
  }}
  .mrmi-chart-header h3 {{
    color: #ddd; font-size: 16px; font-weight: 600;
    display: inline-flex; align-items: center; gap: 8px;
  }}
  .mrmi-chart-header h3 .info-icon {{ color: #555; }}
  .mrmi-chart .legend {{ font-size: 12px; color: #888; margin-bottom: 10px; }}
  .mrmi-chart .legend-item {{
    margin-right: 14px; display: inline-flex; align-items: center;
    cursor: pointer; user-select: none;
    transition: opacity 0.15s, color 0.15s;
  }}
  .mrmi-chart .legend-item:hover {{ color: #fff; }}
  .mrmi-chart .legend-item.inactive {{ opacity: 0.4; color: #555; }}
  .mrmi-chart .legend-item.inactive .legend-dot {{ opacity: 0.5; }}
  .mrmi-chart .legend-dot {{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    margin-right: 6px;
  }}
  .range-tabs {{ display: inline-flex; gap: 2px; }}
  .range-tabs button {{
    background: #161616; border: 1px solid #222; color: #777;
    font-size: 11px; padding: 4px 10px; border-radius: 4px;
    cursor: pointer; font-family: inherit; font-weight: 500;
    letter-spacing: 0.5px;
  }}
  .range-tabs button:hover {{ color: #ccc; border-color: #333; }}
  .range-tabs button.active {{ color: #fff; background: #1f1f1f; border-color: #333; }}
  .chart-container {{ position: relative; height: 280px; width: 100%; }}
  .chart-description {{
    margin-top: 18px; padding-top: 16px;
    border-top: 1px solid #1f1f1f;
  }}
  .chart-description p {{ font-size: 13px; color: #aaa; line-height: 1.6; margin: 0 0 10px 0; }}
  .chart-description p.muted {{ font-size: 12px; color: #666; }}
  .chart-description strong {{ color: #ddd; }}
  .chart-description em {{ color: #ccc; font-style: normal; font-weight: 600; }}
  .backtest-toggle {{
    margin-top: 8px; background: #0e0e0e;
    border: 1px solid #1f1f1f; border-radius: 6px;
    padding: 10px 16px;
  }}
  .backtest-toggle > summary {{
    list-style: none; cursor: pointer; font-size: 12px;
    color: #999; font-weight: 500;
  }}
  .backtest-toggle > summary::-webkit-details-marker {{ display: none; }}
  .backtest-toggle > summary::after {{
    content: " ▾"; color: #555; font-size: 10px; transition: transform 0.15s;
    display: inline-block;
  }}
  .backtest-toggle[open] > summary::after {{ transform: rotate(180deg); }}
  .backtest-toggle-body {{ margin-top: 10px; padding-top: 10px; border-top: 1px solid #1c1c1c; }}
  .backtest-list {{ list-style: none; padding: 0; margin: 0; }}
  .backtest-list li {{
    font-size: 12px; color: #aaa; padding: 4px 0; line-height: 1.5;
  }}
  .bt-asset-inline {{
    display: inline-block; min-width: 100px; color: #888;
    font-weight: 600; text-transform: uppercase; font-size: 10px; letter-spacing: 1px;
  }}
  .preview-banner {{
    margin: 0 0 16px; padding: 10px 14px; border: 1px solid #3a2b10;
    background: #130f07; color: #d8b764; border-radius: 8px;
    font-size: 11px; letter-spacing: 1.2px; text-transform: uppercase;
    font-weight: 700;
  }}
  .macro-stress-momentum-chip {{
    display: inline-flex; align-items: center; height: 24px; padding: 0 8px;
    border: 1px solid; border-radius: 999px; font-size: 11px; font-weight: 700;
    letter-spacing: 0.4px; white-space: nowrap;
  }}

  /* 3 — DRIVERS (toggle + scorecard table) */
  details.drivers {{
    background: #111; border: 1px solid #222; border-radius: 10px;
    padding: 0; margin-bottom: 24px;
  }}
  details.drivers > summary {{
    list-style: none; padding: 14px 24px; cursor: pointer;
    display: flex; justify-content: space-between; align-items: center;
    color: #aaa; font-size: 12px; text-transform: uppercase; letter-spacing: 1.5px;
    font-weight: 600;
  }}
  details.drivers > summary::-webkit-details-marker {{ display: none; }}
  details.drivers > summary::after {{
    content: "▾"; color: #555; font-size: 12px;
    transition: transform 0.15s;
  }}
  details.drivers[open] > summary::after {{ transform: rotate(180deg); }}
  details.drivers > summary:hover {{ color: #fff; }}
  details.drivers .state-dot {{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
    margin-right: 8px; vertical-align: middle;
  }}

  .drivers-body {{ padding: 0 24px 18px; }}
  .drivers-desc {{
    font-size: 12px; color: #666; line-height: 1.55;
    padding-bottom: 12px; border-bottom: 1px solid #1a1a1a;
    margin-bottom: 4px;
  }}
  .drivers-desc strong {{ color: #999; }}
  .growth-drilldown {{
    margin-top: 14px; border-top: 1px solid #1a1a1a; padding-top: 10px;
  }}
  .growth-drilldown > summary {{
    list-style: none; cursor: pointer; color: #aaa; font-size: 12px;
    text-transform: uppercase; letter-spacing: 1.2px; font-weight: 600;
    padding: 4px 0 8px;
  }}
  .growth-drilldown > summary::-webkit-details-marker {{ display: none; }}
  .growth-drilldown > summary::after {{ content: "▾"; color: #555; margin-left: 8px; }}
  .growth-drilldown[open] > summary::after {{ content: "▴"; }}
  .growth-drilldown-body {{ padding-top: 4px; }}
  .growth-mini-brief {{
    margin: 10px 0 12px; padding: 12px 14px;
    background: #0d0d0d; border: 1px solid #1c1c1c; border-left: 2px solid #4CAF50;
    border-radius: 6px; color: #bdbdbd; font-size: 13px; line-height: 1.55;
  }}
  .growth-mini-brief p {{ margin: 0 0 8px; }}
  .growth-mini-brief p:last-child {{ margin-bottom: 0; }}
  .growth-inputs-table {{ width: 100%; border-collapse: collapse; }}
  .growth-inputs-table th {{
    text-align: left; padding: 8px 6px; border-bottom: 1px solid #222;
    color: #555; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    font-weight: 600;
  }}
  .growth-inputs-table td {{
    padding: 9px 6px; border-bottom: 1px solid #1a1a1a;
    font-size: 12px; vertical-align: top;
  }}
  .growth-inputs-table th:first-child, .growth-inputs-table td:first-child {{ padding-left: 0; }}
  .growth-inputs-table th[title] {{ cursor: help; border-bottom-style: dashed; }}
  .growth-input-name {{ display: inline-flex; align-items: center; gap: 6px; position: relative; }}
  .growth-info-icon {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 14px; height: 14px; border: 1px solid #333; border-radius: 50%;
    color: #8a8a8a; font-size: 9px; font-weight: 800; line-height: 1; cursor: help;
    text-transform: lowercase; vertical-align: 1px; position: relative; flex: 0 0 auto;
  }}
  .growth-info-icon::after {{
    content: attr(data-tooltip); position: absolute; left: 50%; bottom: calc(100% + 8px);
    transform: translateX(-50%); width: max-content; max-width: min(280px, 70vw);
    padding: 8px 10px; background: #111; color: #ddd; border: 1px solid #333;
    border-radius: 6px; box-shadow: 0 8px 24px rgba(0,0,0,.42); font-size: 11px;
    font-weight: 500; line-height: 1.45; text-transform: none; white-space: normal;
    opacity: 0; visibility: hidden; pointer-events: none; z-index: 30;
  }}
  .growth-info-icon::before {{
    content: ""; position: absolute; left: 50%; bottom: calc(100% + 3px);
    transform: translateX(-50%) rotate(45deg); width: 8px; height: 8px;
    background: #111; border-right: 1px solid #333; border-bottom: 1px solid #333;
    opacity: 0; visibility: hidden; pointer-events: none; z-index: 31;
  }}
  .growth-info-icon:hover, .growth-info-icon:focus {{
    color: #f1f1f1; border-color: #777; background: #1a1a1a; outline: none;
  }}
  .growth-info-icon:hover::after, .growth-info-icon:focus::after,
  .growth-info-icon:hover::before, .growth-info-icon:focus::before {{ opacity: 1; visibility: visible; }}
  .growth-info-icon:focus-visible {{ box-shadow: 0 0 0 2px #4CAF5055; }}
  .growth-input-row, .driver-input-row {{ cursor: pointer; transition: background 0.1s; }}
  .growth-input-row:hover, .driver-input-row:hover {{ background: #161616; }}
  .growth-input-row.is-selected, .driver-input-row.is-selected {{ background: #14171a; }}
  .growth-input-chart-panel {{
    margin-top: 18px; padding: 12px 14px; background: #0d0d0d;
    border: 1px solid #1c1c1c; border-radius: 6px;
  }}
  .growth-input-chart-header {{
    display: flex; align-items: center; justify-content: space-between;
    gap: 12px; margin-bottom: 10px;
  }}
  .growth-input-chart-title {{
    color: #aaa; font-size: 11px; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 600;
  }}
  .growth-input-chart-header select {{
    background: #1a1a1a; color: #ccc; border: 1px solid #2a2a2a; border-radius: 4px;
    font-size: 12px; padding: 4px 8px; font-family: inherit; cursor: pointer;
    max-width: 60%;
  }}
  .growth-input-chart-header select:hover {{ border-color: #3a3a3a; }}
  .growth-input-chart-wrap {{ height: 180px; padding: 0; }}

  /* scorecard table */
  #scorecard-mrmi table {{ width: 100%; border-collapse: collapse; }}
  #scorecard-mrmi th {{
    text-align: left; padding: 10px 8px; border-bottom: 1px solid #222;
    color: #555; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    font-weight: 600;
  }}
  #scorecard-mrmi th:first-child {{ padding-left: 0; }}
  #scorecard-mrmi td {{
    padding: 12px 8px; border-bottom: 1px solid #1a1a1a;
    font-size: 13px; vertical-align: top;
  }}
  #scorecard-mrmi td:first-child {{ padding-left: 0; }}
  .sc-row {{ cursor: pointer; transition: background 0.1s; }}
  .sc-row:hover {{ background: #161616; }}
  .sc-label {{ color: #ccc; font-weight: 500; font-size: 14px; }}
  .info-icon {{
    color: #555; cursor: help; display: inline-flex; vertical-align: middle;
    margin-left: 6px; transition: color 0.15s; position: relative;
  }}
  .info-icon:hover {{ color: #ccc; }}
  .val {{ font-family: 'SF Mono', Menlo, monospace; font-size: 14px; font-weight: 600; }}
  .val.pos {{ color: #4CAF50; }}
  .val.neg {{ color: #E84B5A; }}
  .val.neutral {{ color: #888; }}
  .dir {{ font-family: 'SF Mono', Menlo, monospace; font-size: 12px; }}
  .dir.up {{ color: #4CAF50; }}
  .dir.down {{ color: #E84B5A; }}
  .dir.flat {{ color: #555; }}
  .dot {{
    display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  }}
  .dot.green {{ background: #4CAF50; }}
  .dot.red {{ background: #E84B5A; }}

  /* proximity bar under indicator name */
  .proximity-wrap {{ margin-top: 6px; }}
  .proximity-track {{
    height: 2px; background: #1a1a1a; border-radius: 1px;
    overflow: hidden; max-width: 220px;
  }}
  .proximity-fill {{ height: 100%; transition: width 0.2s; }}
  .proximity-label {{
    font-size: 10px; margin-top: 3px; font-family: 'SF Mono', Menlo, monospace;
    color: #555; letter-spacing: 0.3px;
  }}
  .proximity-label.near {{ color: #f59e0b; }}
  .proximity-label.mid {{ color: #888; }}
  .proximity-label.far {{ color: #555; }}

  /* expanded chart row */
  .expanded-row {{ display: none; }}
  .expanded-row.active {{ display: table-row; }}
  .expanded-row td {{ padding: 8px 0 16px; background: #0d0d0d; border-bottom: 1px solid #222; }}
  .chart-wrap {{ position: relative; height: 200px; width: 100%; padding: 0 8px; }}
  .chart-desc {{
    font-size: 12px; color: #666; line-height: 1.55;
    padding: 10px 12px 0;
  }}
  .chart-desc strong {{ color: #999; }}

  /* tooltip popover for info icons */
  .info-icon .tip-pop {{
    position: absolute; left: 100%; top: 50%; transform: translateY(-50%);
    margin-left: 8px; z-index: 50; width: 320px;
    background: #1c1c1c; color: #ddd; font-size: 12px;
    padding: 10px 14px; border: 1px solid #333; border-radius: 6px;
    line-height: 1.5; opacity: 0; pointer-events: none;
    transition: opacity 0.15s; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
    font-weight: 400; text-transform: none; letter-spacing: normal;
  }}
  .info-icon:hover .tip-pop {{ opacity: 1; }}
  .info-icon .tip-pop.tip-pop-wide {{ width: 420px; }}
  .info-icon .tip-pop p {{ margin: 0 0 8px; }}
  .info-icon .tip-pop p:last-child {{ margin-bottom: 0; }}
  .info-icon .tip-pop strong {{ color: #fff; }}
  .info-icon .tip-pop em {{ color: #cdaa6a; font-style: normal; }}

  /* one-line subtitle under chart titles */
  .mrmi-chart-subtitle {{
    font-size: 13px; color: #888; margin: -4px 0 14px;
    line-height: 1.5;
  }}


  /* Macro-stress pillar: match the market pillar card + drivers structure */
  .macro-stress-snapshot {{ margin-bottom: 24px; }}
  .macro-stress-reading {{
    display: inline-flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
    justify-content: flex-end;
  }}
  .macro-stress-reading-value {{
    font-size: 28px; font-weight: 600; line-height: 1;
    letter-spacing: -0.5px; color: #e0e0e0;
  }}
  .macro-stress-reading-chip {{
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 44px; padding: 4px 10px; border-radius: 999px;
    background: #181818; border: 1px solid;
    font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
    text-transform: uppercase; line-height: 1;
  }}
  .macro-stress-reading-label {{
    font-size: 11px; color: #666; font-weight: 600;
    letter-spacing: 1.2px; text-transform: uppercase;
  }}
  .macro-stress-inputs-panel .drivers-body {{ padding-top: 2px; }}
  .macro-stress-mini-legend {{ font-size: 12px; color: #888; margin: 0 0 10px; }}
  .macro-stress-mini-legend span {{ display: inline-flex; align-items: center; margin-right: 14px; }}
  .macro-stress-mini-legend i {{ width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; display: inline-block; }}
  .macro-stress-inputs-wrap {{ height: 190px; padding: 0 8px; }}
  @media (max-width: 720px) {{
    .macro-stress-reading {{ justify-content: flex-start; }}
    .macro-stress-reading-value {{ font-size: 24px; }}
  }}

  /* Pillar weekly brief (sits between chart and drivers) */
  .pillar-brief {{
    margin: 20px 0 24px;
    padding: 16px 18px;
    background: #0d0d0d; border: 1px solid #1c1c1c; border-radius: 6px;
    border-left: 2px solid #333;
    color: #c8c8c8; font-size: 13.5px; line-height: 1.6;
  }}
  .pillar-brief-eyebrow {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.8px;
    color: #666; font-weight: 500; margin-bottom: 10px;
  }}
  .pillar-brief p {{ margin: 0 0 10px; }}
  .pillar-brief p:last-child {{ margin-bottom: 0; }}
  .pillar-brief a {{ color: #cdaa6a; text-decoration: none; border-bottom: 1px dotted #6c5a36; }}
  .pillar-brief a:hover {{ color: #e6c98a; border-bottom-color: #cdaa6a; }}
  /* Headline (top) brief: slightly more prominent than the pillar briefs */
  .pillar-brief.pillar-brief-headline {{
    color: #d4d4d4; font-size: 14px; line-height: 1.65;
    border-left-color: #cdaa6a; padding: 18px 20px;
  }}
  /* 4 — MACRO BACKDROP */
  .seasons {{
    background: #111; border: 1px solid #222; border-radius: 10px;
    padding: 22px 26px 22px; margin-bottom: 14px;
  }}
  .backdrop-grid {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 14px;
    margin-bottom: 16px;
  }}
  .backdrop-cell {{
    background: #181818; border-radius: 8px; padding: 18px 22px;
    border-left: 4px solid;
  }}
  .backdrop-eyebrow {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.8px;
    color: #666; margin-bottom: 8px; font-weight: 600;
  }}
  .backdrop-value {{
    font-size: 38px; font-weight: 800; letter-spacing: -0.5px;
    color: #fff; line-height: 1; margin-bottom: 6px;
  }}
  .backdrop-meta {{
    font-size: 13px; color: #888;
  }}
  .backdrop-summary {{
    background: #161616; border-radius: 8px; padding: 16px 22px;
    border-left: 3px solid;
    margin-bottom: 14px;
  }}
  .backdrop-summary-tag {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px;
    font-weight: 700; margin-bottom: 6px;
  }}
  .backdrop-summary p {{
    color: #bbb; font-size: 14px; line-height: 1.55; margin: 0;
  }}
  .season-now {{
    background: #181818; border-radius: 8px; padding: 22px 26px;
    border-left: 4px solid;
    margin-bottom: 22px;
  }}
  .season-now-eyebrow {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.8px;
    color: #666; margin-bottom: 6px; font-weight: 600;
  }}
  .season-now-name {{
    font-size: 38px; font-weight: 800; letter-spacing: -0.5px;
    margin-bottom: 10px; line-height: 1;
  }}
  .season-now-desc {{
    color: #bbb; font-size: 14px; line-height: 1.55;
    margin-bottom: 14px; max-width: 720px;
  }}
  .season-now-axes {{
    display: flex; gap: 36px; flex-wrap: wrap;
    font-size: 13px; color: #888;
  }}
  .season-now-axes .axis-pair {{ display: inline-flex; gap: 6px; align-items: baseline; }}
  .season-now-axes .axis-pair .mono {{ font-weight: 700; font-size: 14px; }}

  /* season history strip */
  .season-history {{ margin-top: 4px; }}
  .history-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 8px;
  }}
  .history-label {{
    font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px;
    color: #555; font-weight: 600;
  }}
  .history-legend {{ font-size: 11px; color: #777; }}
  .history-legend .hkey {{ margin-left: 14px; display: inline-flex; align-items: center; }}
  .history-legend .hdot {{
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    margin-right: 5px;
  }}
  .history-strip {{
    display: grid; grid-template-columns: repeat(60, 1fr); gap: 1px;
    margin-bottom: 6px;
  }}
  .hcell {{
    height: 26px; border-radius: 2px; border: 1px solid;
    cursor: default;
  }}
  .hcell.empty {{ background: #161616; border-color: #222; }}
  .history-axis {{
    position: relative; height: 14px; font-size: 10px; color: #555;
    font-family: 'SF Mono', Menlo, monospace;
  }}
  .history-axis span {{ position: absolute; transform: translateX(-50%); }}
  .history-axis span:first-child {{ transform: translateX(0); }}
  .history-axis span:last-child {{ transform: translateX(-100%); }}

  .seasons-axis-spec {{
    border-top: 1px solid #1f1f1f;
    margin-top: 18px; padding-top: 14px;
    font-size: 12px; color: #666; line-height: 1.6;
  }}
  .seasons-axis-spec strong {{ color: #888; }}
  .pending-tag {{
    display: inline-block; background: #1a1100; color: #f59e0b;
    font-size: 11px; padding: 2px 8px; border-radius: 4px;
    margin-left: 4px; font-weight: 500;
  }}

  /* macro seasons drivers — reuse drivers-body styles */
  .seasons-drivers {{ margin-top: 0; }}
  #scorecard-seasons table {{ width: 100%; border-collapse: collapse; }}
  #scorecard-seasons th {{
    text-align: left; padding: 10px 8px; border-bottom: 1px solid #222;
    color: #555; font-size: 10px; text-transform: uppercase; letter-spacing: 1px;
    font-weight: 600;
  }}
  #scorecard-seasons th:first-child {{ padding-left: 0; }}
  #scorecard-seasons td {{
    padding: 12px 8px; border-bottom: 1px solid #1a1a1a;
    font-size: 13px; vertical-align: top;
  }}
  #scorecard-seasons td:first-child {{ padding-left: 0; }}

  /* 5 — LIBRARY */
  .library {{
    background: #111; border: 1px solid #222; border-radius: 10px;
    padding: 22px 26px;
  }}
  .library table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  .library th {{
    text-align: left; padding: 10px 14px; border-bottom: 2px solid #222;
    color: #666; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
    font-weight: 600;
  }}
  .library td {{
    padding: 10px 14px; border-bottom: 1px solid #1a1a1a;
    font-size: 14px; vertical-align: middle;
  }}
  .library tr:last-child td {{ border-bottom: none; }}
  .library .ind-name {{ color: #ddd; font-weight: 500; }}
  .library .value {{ color: #fff; font-weight: 600; }}
  .library-footer {{ margin-top: 14px; font-size: 12px; color: #666; }}
  .lib-row {{ cursor: pointer; transition: background 0.1s; }}
  .lib-row:hover {{ background: #161616; }}
  .lib-row.unavailable {{ cursor: default; opacity: 0.55; }}
  .lib-row.unavailable:hover {{ background: transparent; }}
</style>
</head>
<body>

<div class="meta-bar">
  <span class="brand">MILK ROAD · MACRO DASHBOARD v2</span>
  <span>{snap["date"]} · built {snap.get("build_time_utc", "")}</span>
</div>
{preview_banner}

<!-- 1 · HERO (single source of truth for the headline value) -->
<header class="hero">
  <div class="hero-eyebrow">Milk Road Macro Index · {snap["date"]}</div>
  <div class="hero-grid">
    <div class="hero-main">
      <div class="hero-row">
        <div class="hero-value mono" style="color:{state_color};">{mrmi_value_str}</div>
        <div class="hero-action">
          <div class="hero-action-label" style="color:{state_color};">{state_label}</div>
          <div class="hero-action-sub">{state_subtitle}</div>
        </div>
      </div>

      <!-- Visual scale bar -->
      {_make_scale_bar(mrmi_value, state_color)}
    </div>

    <aside class="hero-pillars">
      <div class="hero-pillars-title">What's behind it</div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">Market signal (MMI)</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{mmi_color};">{mmi_label}</span>
          <span class="hero-pillar-value mono">{mmi_value_str}</span>
        </span>
      </div>
      <div class="hero-pillar">
        <span class="hero-pillar-name">Macro stress</span>
        <span class="hero-pillar-right">
          <span class="hero-pillar-state" style="color:{stress_color};">{stress_score_label}</span>
          <span class="hero-pillar-value mono">{stress_value_str}</span>
        </span>
      </div>
      <div class="hero-pillar-note">MRMI = MMI + macro buffer. Posture is LONG above +0.25, CAUTION from −0.50 to +0.25, CASH below −0.50.</div>
    </aside>
  </div>

  {(f'<div class="hero-story hero-story-ai">'
    f'<div class="hero-story-eyebrow">This week’s read{(" · " + commentary_date + " (cached)") if commentary_stale else ""}</div>'
    f'{commentary_html}'
    f'</div>') if commentary_html else f'<p class="hero-story">{banner_story}</p>'}
</header>

<!-- 2 · MRMI HISTORY CHART (right after hero — context for the headline number) -->
<div class="section-title"><span class="step-num">1</span>How the index has evolved</div>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Milk Road Macro Index (MRMI)
      <span class="info-icon">{info_svg}<span class="tip-pop tip-pop-wide"><p><strong>How it's built:</strong> MRMI combines MMI (market momentum from credit, breadth and volatility) with a macro buffer that erodes when growth and inflation both deteriorate. The formula is unchanged; the production posture layer maps MRMI to LONG, CAUTION, or CASH.</p><p><strong>Reading the chart:</strong> white line is the MRMI value over time. Green zone = LONG above +0.25, amber = CAUTION from −0.50 to +0.25, red = CASH below −0.50. Toggle assets in the legend to overlay SPX / Russell / BTC.</p><p><strong>Next:</strong> open <em>MMI Drivers</em> below to see what's behind the market signal, then <em>Macro Backdrop</em> for the economy signal.</p></span></span>
    </h3>
    <div class="range-tabs">
      <button data-range="1y" class="active">1Y</button>
      <button data-range="2y">2Y</button>
      <button data-range="5y">5Y</button>
      <button data-range="all">ALL</button>
    </div>
  </div>
  <p class="mrmi-chart-subtitle">An allocation posture index: LONG above +0.25, CAUTION (75% exposure) from −0.50 to +0.25, CASH below −0.50.</p>
  <div class="legend">
    <span class="legend-item" data-series="mrmi"><span class="legend-dot" style="background:#fff"></span>MRMI (headline)</span>
    <span class="legend-item inactive" data-series="mmi"><span class="legend-dot" style="background:#888"></span>MMI (momentum only)</span>
    <span class="legend-item" data-series="spx"><span class="legend-dot" style="background:#f5c842"></span>S&amp;P 500</span>
    <span class="legend-item inactive" data-series="iwm"><span class="legend-dot" style="background:#E84B9A"></span>Russell</span>
    <span class="legend-item inactive" data-series="btc"><span class="legend-dot" style="background:#A78BFA"></span>Bitcoin</span>
  </div>
  <div class="chart-container"><canvas id="chart-mrmi"></canvas></div>

  <div class="chart-description">
    {backtest_card_html.strip()}
  </div>
</div>

<!-- 3 · MMI (market pillar): chart over time + drivers below -->
<div class="section-title"><span class="step-num">2</span>What the markets are signaling<span class="pillar-chip market">Market pillar</span></div>
<p class="section-intro"><strong>MMI — Market Momentum Index.</strong> The fast, <em>market-derived</em> half of MRMI: built entirely from price and volatility data — credit spreads, cyclical sector breadth, and financial-conditions volatility — equally weighted. Markets react quickly, so MMI catches turning points early; the trade-off is they can also flash false alarms, which is why MMI alone never triggers a CASH call. It only acts in concert with the slower economy pillar below.</p>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Market Momentum Index (MMI)
      <span class="info-icon">{info_svg}<span class="tip-pop tip-pop-wide"><p><strong>What you're seeing:</strong> the MMI score over time, equally-weighted from GII (global growth momentum), Breadth (cyclical participation) and FinCon (financial conditions). Above zero = healthy momentum. Below zero = momentum is rolling over.</p><p><strong>Drivers below:</strong> click any row to expand the underlying series. The MMI score is just the average of the three.</p></span></span>
    </h3>
  </div>
  <p class="mrmi-chart-subtitle">Market momentum on its own, averaged from credit spreads, sector breadth and financial-conditions volatility.</p>
  <div class="chart-container" style="height: 220px;"><canvas id="chart-mmi"></canvas></div>
</div>
{(f'<div class="pillar-brief"><div class="pillar-brief-eyebrow">This week’s read · market pillar{(" · " + market_brief_date + " (cached)") if market_brief_stale else ""}</div>{market_brief_html}</div>') if market_brief_html else ''}
<details class="drivers" open>
  <summary>
    <span><span class="state-dot" style="background:{mmi_color}"></span>MMI DRIVERS <span class="muted small">· GII · Breadth · FinCon — click any row to expand</span></span>
  </summary>
  <div class="drivers-body">
    <div id="scorecard-mrmi"></div>
    <template id="drilldown-template-gii_fast">{growth_drilldown_html}</template>
    <template id="drilldown-template-breadth">{breadth_drilldown_html}</template>
    <template id="drilldown-template-fincon">{fincon_drilldown_html}</template>
  </div>
</details>

<!-- 5 · MACRO BACKDROP — chart over time + drivers, parallel to MMI -->
<div class="section-title"><span class="step-num">3</span>What the economy is signaling<span class="pillar-chip economy">Economy pillar</span></div>
<p class="section-intro"><strong>Macro Stress.</strong> The slow, <em>economy-derived</em> half of MRMI: built from real-economy data — consumer spending, jobs, income, GDP nowcast — and inflation trajectory. The unified 0–10 score is calm by default, rises when either growth weakens or inflation accelerates, and builds fastest when both factors hit together.</p>
<div class="mrmi-chart macro-stress-snapshot">
  <div class="mrmi-chart-header">
    <h3>Macro Stress
      <span class="info-icon">{info_svg}<span class="tip-pop tip-pop-wide">{stress_panel_tip}</span></span>
    </h3>
    <div class="macro-stress-reading">
      <span class="macro-stress-reading-value mono">{stress_value_str}</span>{stress_momentum_chip}
      <span class="macro-stress-reading-chip" style="color:{stress_color}; border-color:{stress_color}55; box-shadow: 0 0 0 3px {stress_color}12;">{stress_score_label}</span>
      <span class="macro-stress-reading-label">{stress_reading_label}</span>
    </div>
  </div>
  <p class="mrmi-chart-subtitle">{stress_panel_subtitle}</p>
  <div class="chart-container" style="height: 220px;"><canvas id="chart-stress-history"></canvas></div>
</div>
<details class="drivers macro-stress-inputs-panel" open>
  <summary>
    <span><span class="state-dot" style="background:{stress_color}"></span>STRESS INPUTS <span class="muted small">· {stress_inputs_title}</span></span>
  </summary>
  <div class="drivers-body">
    <div class="macro-stress-mini-legend">
      <span><i style="background:#4CAF50"></i>{stress_growth_label}</span>
      <span><i style="background:#cdaa6a"></i>{stress_inflation_label}</span>
    </div>
    <div class="chart-wrap macro-stress-inputs-wrap"><canvas id="chart-stress-inputs"></canvas></div>
  </div>
</details>
{(f'<div class="pillar-brief"><div class="pillar-brief-eyebrow">This week’s read · economy pillar{(" · " + economy_brief_date + " (cached)") if economy_brief_stale else ""}</div>{economy_brief_html}</div>') if economy_brief_html else ''}
<details class="drivers seasons-drivers">
  <summary>
    <span><span class="state-dot" style="background:{backdrop['color']}"></span>REAL ECONOMY DRIVERS <span class="muted small">· PCE · Sahm · Real Income · GDPNow — click any row to expand</span></span>
  </summary>
  <div class="drivers-body">
    <div id="scorecard-seasons"></div>
  </div>
</details>

<!-- 6 · LIBRARY -->
<div class="section-title"><span class="step-num">4</span>Reference Library</div>
<div class="library">
  <table>
    <thead>
      <tr><th>Indicator</th><th>Category</th><th>Latest</th><th>Notes</th></tr>
    </thead>
    <tbody>
      {library_rows_html}
    </tbody>
  </table>
  <div class="library-footer">
    Library entries don't drive the headline posture — they're context that explains narrative shifts. Most need data wiring before they can populate.
  </div>
</div>

<script>
const CHART_DATA = {chart_payload};
const RANGE_BARS = {{ '1y': 252, '2y': 504, '5y': 1260, 'all': 0 }};
let mrmiChart = null;

function sliceRecent(arr, n) {{
  if (!arr || !arr.length) return [];
  return n > 0 ? arr.slice(-n) : arr.slice();
}}

function normalizePrices(arr) {{
  let first = null;
  for (const v of arr) {{ if (v !== null) {{ first = v; break; }} }}
  if (!first) return arr;
  return arr.map(v => v !== null ? (v / first) * 100 : null);
}}

const visibleSeries = {{ mrmi: true, mmi: false, spx: true, iwm: false, btc: false }};

function buildMrmiChart(rangeKey) {{
  const n = RANGE_BARS[rangeKey] ?? 252;
  const dates = sliceRecent(CHART_DATA.dates, n);
  const mrmi_series = sliceRecent((CHART_DATA.mrmi_combined || {{}}).value || [], n);
  const mmi_series = sliceRecent(CHART_DATA.composite, n);
  const spx = normalizePrices(sliceRecent(CHART_DATA.spx, n));
  const iwm = normalizePrices(sliceRecent(CHART_DATA.iwm, n));
  const btc = normalizePrices(sliceRecent(CHART_DATA.btc, n));

  const datasets = [];
  if (visibleSeries.spx) datasets.push({{ label: 'S&P 500', data: spx, borderColor: '#f5c842', borderWidth: 2,
       pointRadius: 0, tension: 0.1, spanGaps: true, yAxisID: 'yPrice', order: 2 }});
  if (visibleSeries.iwm) datasets.push({{ label: 'Russell', data: iwm, borderColor: '#E84B9A', borderWidth: 2,
       pointRadius: 0, tension: 0.1, spanGaps: true, yAxisID: 'yPrice', order: 2 }});
  if (visibleSeries.btc) datasets.push({{ label: 'Bitcoin', data: btc, borderColor: '#A78BFA', borderWidth: 2,
       pointRadius: 0, tension: 0.1, spanGaps: true, yAxisID: 'yPrice', order: 2 }});
  if (visibleSeries.mmi) datasets.push({{
      label: 'MMI (momentum only)', data: mmi_series,
      borderColor: '#888888', borderWidth: 1.4,
      borderDash: [4, 3],
      pointRadius: 0, tension: 0.1, spanGaps: true,
      order: 1,
  }});
  if (visibleSeries.mrmi) datasets.push({{
      label: 'MRMI', data: mrmi_series,
      borderColor: '#ffffff', borderWidth: 2.0,
      pointRadius: 0, tension: 0.1, spanGaps: true,
      order: 0,
  }});

  const showPriceAxis = visibleSeries.spx || visibleSeries.iwm || visibleSeries.btc;

  if (mrmiChart) mrmiChart.destroy();
  mrmiChart = new Chart(document.getElementById('chart-mrmi'), {{
    type: 'line',
    data: {{ labels: dates, datasets }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }},
          bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{
            label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '—'),
          }},
        }},
        annotation: {{
          annotations: {{
            cashBand: {{ type: 'box', yMin: -10, yMax: {MRMI_CASH_THRESHOLD:.2f}, backgroundColor: 'rgba(232,75,90,0.10)', borderWidth: 0, scaleID: 'y' }},
            cautionBand: {{ type: 'box', yMin: {MRMI_CASH_THRESHOLD:.2f}, yMax: {MRMI_LONG_THRESHOLD:.2f}, backgroundColor: 'rgba(205,170,106,0.10)', borderWidth: 0, scaleID: 'y' }},
            longBand: {{ type: 'box', yMin: {MRMI_LONG_THRESHOLD:.2f}, yMax: 10, backgroundColor: 'rgba(76,175,80,0.10)', borderWidth: 0, scaleID: 'y' }},
            cashLine: {{ type: 'line', yMin: {MRMI_CASH_THRESHOLD:.2f}, yMax: {MRMI_CASH_THRESHOLD:.2f}, borderColor: 'rgba(232,75,90,0.65)', borderWidth: 1, borderDash: [4, 4], scaleID: 'y', label: {{ display: true, content: 'CASH −0.50', position: 'start', backgroundColor: 'transparent', color: '#9a3d47', font: {{ size: 9 }} }} }},
            longLine: {{ type: 'line', yMin: {MRMI_LONG_THRESHOLD:.2f}, yMax: {MRMI_LONG_THRESHOLD:.2f}, borderColor: 'rgba(76,175,80,0.65)', borderWidth: 1, borderDash: [4, 4], scaleID: 'y', label: {{ display: true, content: 'LONG +0.25', position: 'start', backgroundColor: 'transparent', color: '#4CAF50', font: {{ size: 9 }} }} }},
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 12, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ position: 'left', ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 7 }}, grid: {{ color: '#1a1a1a' }} }},
        yPrice: {{ display: showPriceAxis, position: 'right', ticks: {{ color: '#444', font: {{ size: 9, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ display: false }} }},
      }},
    }},
  }});
}}

let currentRange = '1y';
let driverCharts = {{}};
let mmiChart = null;

function buildMmiChart(rangeKey) {{
  const n = RANGE_BARS[rangeKey] ?? 252;
  const dates = sliceRecent(CHART_DATA.dates, n);
  const mmi = sliceRecent(CHART_DATA.composite, n);
  if (mmiChart) mmiChart.destroy();
  const canvas = document.getElementById('chart-mmi');
  if (!canvas) return;
  mmiChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: 'MMI', data: mmi,
        borderColor: '#ffffff', borderWidth: 1.8,
        pointRadius: 0, tension: 0.1, spanGaps: true,
        fill: {{ target: 'origin', above: 'rgba(76,175,80,0.18)', below: 'rgba(232,75,90,0.18)' }},
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }},
          bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{
            label: ctx => 'MMI: ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '—'),
          }},
        }},
        annotation: {{
          annotations: {{
            zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }},
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ position: 'left', ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 6 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

function lastValid(arr) {{
  for (let i = arr.length - 1; i >= 0; i--) {{
    if (arr[i] !== null && arr[i] !== undefined) return arr[i];
  }}
  return null;
}}

function fmtChg(curr, prev) {{
  if (curr === null || prev === null) return '<span class="dir flat">—</span>';
  const diff = curr - prev;
  const pct = (diff * 100).toFixed(0);
  const sign = diff > 0 ? '+' : '';
  if (Math.abs(diff) < 0.03) return `<span class="dir flat">${{sign}}${{pct}}%</span>`;
  if (diff > 0) return `<span class="dir up">▲ ${{sign}}${{pct}}%</span>`;
  return `<span class="dir down">▼ ${{sign}}${{pct}}%</span>`;
}}

function buildScorecard() {{
  const container = document.getElementById('scorecard-mrmi');
  if (!container) return;
  const drivers = CHART_DATA.drivers;
  const keys = ['gii_fast', 'breadth', 'fincon'];

  let html = '<table><thead><tr>';
  html += '<th>Indicator</th><th>Value</th><th>7d</th><th>30d</th><th>Signal</th>';
  html += '</tr></thead><tbody>';

  keys.forEach(key => {{
    const entry = drivers[key];
    if (!entry) return;
    const sliced = sliceRecent(entry.values, RANGE_BARS[currentRange]);
    const current = lastValid(sliced);
    const prev7 = sliced.length > 5 ? lastValid(sliced.slice(0, sliced.length - 5)) : null;
    const prev30 = sliced.length > 21 ? lastValid(sliced.slice(0, sliced.length - 21)) : null;

    let valCls = 'neutral';
    if (current !== null) valCls = (current > 0) === entry.green_above ? 'pos' : 'neg';
    const valStr = current !== null ? current.toFixed(2) : '—';

    let signalHtml = '<span style="font-size:10px;color:#444;">—</span>';
    if (current !== null) {{
      const isGreen = (current > 0) === entry.green_above;
      signalHtml = `<span class="dot ${{isGreen ? 'green' : 'red'}}"></span>`;
    }}

    let proximityHtml = '';
    if (current !== null) {{
      const dist = Math.abs(current);
      const pct = Math.min(100, (dist / 3) * 100).toFixed(1);
      const fillColor = (current > 0) === entry.green_above ? '#4CAF50' : '#E84B5A';
      const urgency = dist < 0.3 ? 'near' : dist < 0.75 ? 'mid' : 'far';
      const flipDir = (current > 0) === entry.green_above ? '↓ to red' : '↑ to green';
      proximityHtml = `
        <div class="proximity-wrap">
          <div class="proximity-track"><div class="proximity-fill" style="width:${{pct}}%;background:${{fillColor}}"></div></div>
          <div class="proximity-label ${{urgency}}">${{dist.toFixed(2)}} ${{flipDir}}</div>
        </div>`;
    }}

    const infoIcon = entry.desc
      ? `<span class="info-icon" title=""><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="4" r="0.9" fill="currentColor"/><line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg><span class="tip-pop">${{entry.desc}}</span></span>`
      : '';

    html += `<tr class="sc-row" onclick="toggleDriver('${{key}}')">`;
    html += `<td><span class="sc-label">${{entry.label}}</span>${{infoIcon}}${{proximityHtml}}</td>`;
    html += `<td><span class="val ${{valCls}}">${{valStr}}</span></td>`;
    html += `<td>${{fmtChg(current, prev7)}}</td>`;
    html += `<td>${{fmtChg(current, prev30)}}</td>`;
    html += `<td>${{signalHtml}}</td>`;
    html += `</tr>`;
    html += `<tr class="expanded-row" id="exp-${{key}}"><td colspan="5"><div class="chart-wrap"><canvas id="canvas-${{key}}"></canvas></div><div class="chart-desc">${{entry.desc || ''}}</div><div class="indicator-drilldown-slot" data-driver-key="${{key}}"></div></td></tr>`;
  }});

  html += '</tbody></table>';
  container.innerHTML = html;
  attachDriverDrilldowns();
}}

function attachDriverDrilldowns() {{
  document.querySelectorAll('.indicator-drilldown-slot').forEach(slot => {{
    const driverKey = slot.dataset.driverKey;
    const template = document.getElementById('drilldown-template-' + driverKey);
    if (!template) return;
    slot.replaceChildren(template.content.cloneNode(true));
  }});
}}

function toggleDriver(key, forceOpen) {{
  const row = document.getElementById('exp-' + key);
  if (!row) return;
  const isOpen = row.classList.contains('active');
  if (isOpen && !forceOpen) {{
    row.classList.remove('active');
    if (driverCharts[key]) {{ driverCharts[key].destroy(); delete driverCharts[key]; }}
  }} else if (!isOpen) {{
    row.classList.add('active');
    createDriverChart(key);
  }}
}}

function expandAllDrivers() {{
  ['gii_fast', 'breadth', 'fincon'].forEach(k => toggleDriver(k, true));
}}

function createDriverChart(key) {{
  const entry = CHART_DATA.drivers[key];
  if (!entry) return;
  const dates = sliceRecent(CHART_DATA.dates, RANGE_BARS[currentRange]);
  const values = sliceRecent(entry.values, RANGE_BARS[currentRange]);
  const invert = entry.green_above === false;
  const greenColor = invert ? 'rgba(232,75,90,0.20)' : 'rgba(76,175,80,0.20)';
  const redColor = invert ? 'rgba(76,175,80,0.20)' : 'rgba(232,75,90,0.20)';

  if (driverCharts[key]) driverCharts[key].destroy();
  driverCharts[key] = new Chart(document.getElementById('canvas-' + key), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: entry.label, data: values,
        borderColor: '#ffffff', borderWidth: 1.6,
        pointRadius: 0, tension: 0.1, spanGaps: true,
        fill: {{ target: 'origin', above: greenColor, below: redColor }},
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '—') }},
        }},
        annotation: {{ annotations: {{ zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }} }} }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

document.querySelectorAll('.range-tabs button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.range-tabs button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentRange = btn.dataset.range;
    buildMrmiChart(currentRange);
    buildMmiChart(currentRange);
    buildScorecard();
    buildMacroDriversScorecard();
    buildMacroChart();
    buildStressHistoryChart();
    buildStressInputsChart();
        Object.keys(driverCharts).forEach(k => createDriverChart(k));
    Object.keys(macroDriverCharts).forEach(k => createMacroDriverChart(k));
    Object.keys(libCharts).forEach(k => createLibChart(k));
    if (growthInputBuilt && growthInputCurrentKey) buildGrowthInputChart(growthInputCurrentKey);
    rebuildDriverInputCharts();
  }});
}});

document.querySelectorAll('.legend-item').forEach(item => {{
  item.addEventListener('click', () => {{
    const key = item.dataset.series;
    visibleSeries[key] = !visibleSeries[key];
    item.classList.toggle('inactive', !visibleSeries[key]);
    buildMrmiChart(currentRange);
  }});
}});

// ── Macro Backdrop: drivers scorecard ──────

function fmtSigned(v, dec) {{
  dec = dec ?? 2;
  if (v === null || v === undefined) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(dec);
}}

function buildMacroDriversScorecard() {{
  const container = document.getElementById('scorecard-seasons');
  if (!container) return;
  const keys = ['pce', 'sahm', 'income', 'gdpnow'];

  let html = '<table><thead><tr>';
  html += '<th>Indicator</th><th>Value</th><th>7d</th><th>30d</th><th>Signal</th>';
  html += '</tr></thead><tbody>';

  keys.forEach(key => {{
    const entry = CHART_DATA.macro_drivers[key];
    if (!entry || !entry.values || entry.values.length === 0) return;
    const sliced = sliceRecent(entry.values, RANGE_BARS[currentRange]);
    const current = lastValid(sliced);
    const prev30 = sliced.length > 21 ? lastValid(sliced.slice(0, sliced.length - 21)) : null;

    const isPctTarget = entry.type === 'pct';
    const isPctSigned = entry.type === 'pct_signed';
    const isPct = isPctTarget || isPctSigned;
    const ref = entry.target ?? 0;
    const isAbove = current !== null && current > ref;
    const sigColor = isAbove ? entry.above_color : entry.below_color;
    const sigLabel = isAbove ? entry.above_label : entry.below_label;

    let valStr = '—';
    let valCls = 'neutral';
    if (current !== null) {{
      if (isPctSigned) valStr = (current >= 0 ? '+' : '') + current.toFixed(2) + (key === 'sahm' ? 'pp' : '%');
      else if (isPctTarget) valStr = current.toFixed(2) + '%';
      else valStr = (current >= 0 ? '+' : '') + current.toFixed(2);
      valCls = (key === 'sahm' ? !isAbove : isAbove) ? 'pos' : 'neg';  // sahm: lower = better
    }}

    function fmtDelta(curr, prev) {{
      if (curr === null || prev === null) return '<span class="dir flat">—</span>';
      const diff = curr - prev;
      if (Math.abs(diff) < 0.02) return `<span class="dir flat">${{diff >= 0 ? '+' : ''}}${{diff.toFixed(2)}}pp</span>`;
      const cls = diff > 0 ? 'up' : 'down';
      const sign = diff > 0 ? '▲ +' : '▼ ';
      return `<span class="dir ${{cls}}">${{sign}}${{diff.toFixed(2)}}pp</span>`;
    }}

    const cell30 = fmtDelta(current, prev30);

    const signalHtml = current !== null
      ? `<span style="display:inline-flex;align-items:center;gap:6px;font-size:11px;color:${{sigColor}}"><span class="dot" style="background:${{sigColor}}"></span>${{sigLabel}}</span>`
      : '<span style="font-size:10px;color:#444;">—</span>';

    const infoIcon = entry.desc
      ? `<span class="info-icon"><svg width="13" height="13" viewBox="0 0 14 14" fill="none"><circle cx="7" cy="7" r="6" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="4" r="0.9" fill="currentColor"/><line x1="7" y1="6.5" x2="7" y2="10.5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg><span class="tip-pop">${{entry.desc}}</span></span>`
      : '';

    html += `<tr class="sc-row" onclick="toggleMacroDriver('${{key}}')">`;
    html += `<td><span class="sc-label">${{entry.label}}</span>${{infoIcon}}</td>`;
    html += `<td><span class="val ${{valCls}}">${{valStr}}</span></td>`;
    html += `<td><span class="dir flat" title="monthly data">—</span></td>`;
    html += `<td>${{cell30}}</td>`;
    html += `<td>${{signalHtml}}</td>`;
    html += `</tr>`;
    html += `<tr class="expanded-row" id="exp-md-${{key}}"><td colspan="5"><div class="chart-wrap"><canvas id="canvas-md-${{key}}"></canvas></div><div class="chart-desc">${{entry.desc || ''}}</div></td></tr>`;
  }});

  html += '</tbody></table>';
  container.innerHTML = html;
}}

let macroDriverCharts = {{}};

function toggleMacroDriver(key, forceOpen) {{
  const row = document.getElementById('exp-md-' + key);
  if (!row) return;
  const isOpen = row.classList.contains('active');
  if (isOpen && !forceOpen) {{
    row.classList.remove('active');
    if (macroDriverCharts[key]) {{ macroDriverCharts[key].destroy(); delete macroDriverCharts[key]; }}
  }} else if (!isOpen) {{
    row.classList.add('active');
    createMacroDriverChart(key);
  }}
}}

function expandAllMacroDrivers() {{
  ['pce', 'sahm', 'income', 'gdpnow'].forEach(k => toggleMacroDriver(k, true));
}}

function createMacroDriverChart(key) {{
  const entry = CHART_DATA.macro_drivers[key];
  if (!entry) return;
  const dates = sliceRecent(CHART_DATA.dates, RANGE_BARS[currentRange]);
  const values = sliceRecent(entry.values, RANGE_BARS[currentRange]);
  const ref = entry.target ?? 0;
  const isPctTarget = entry.type === 'pct';

  if (macroDriverCharts[key]) macroDriverCharts[key].destroy();
  macroDriverCharts[key] = new Chart(document.getElementById('canvas-md-' + key), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: entry.label, data: values,
        borderColor: '#ffffff', borderWidth: 1.6,
        pointRadius: 0, tension: 0.1, spanGaps: true,
        fill: isPctTarget ? false : {{ target: 'origin', above: 'rgba(76,175,80,0.20)', below: 'rgba(232,75,90,0.20)' }},
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '—') }},
        }},
        annotation: {{
          annotations: {{
            ref: {{ type: 'line', yMin: ref, yMax: ref, borderColor: ref === 0 ? '#333' : '#FF8C0080', borderWidth: 1, borderDash: ref === 0 ? [] : [4, 4], scaleID: 'y' }},
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

// ── Reference Library: click to expand chart per indicator ────────

let libCharts = {{}};

function toggleLib(key) {{
  const row = document.getElementById('exp-lib-' + key);
  if (!row) return;
  if (row.classList.contains('active')) {{
    row.classList.remove('active');
    if (libCharts[key]) {{ libCharts[key].destroy(); delete libCharts[key]; }}
  }} else {{
    row.classList.add('active');
    createLibChart(key);
  }}
}}

function createLibChart(key) {{
  const entry = (CHART_DATA.library || {{}})[key];
  if (!entry) return;
  const dates = sliceRecent(CHART_DATA.dates, RANGE_BARS[currentRange]);
  const values = sliceRecent(entry.values, RANGE_BARS[currentRange]);
  const unit = entry.unit || '';
  const refLine = entry.ref_line;

  const annotations = {{}};
  if (refLine !== null && refLine !== undefined) {{
    annotations.ref = {{
      type: 'line', yMin: refLine, yMax: refLine,
      borderColor: refLine === 0 ? '#333' : '#FF8C0080',
      borderWidth: 1, borderDash: refLine === 0 ? [] : [4, 4], scaleID: 'y',
    }};
  }}

  if (libCharts[key]) libCharts[key].destroy();
  libCharts[key] = new Chart(document.getElementById('canvas-lib-' + key), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: entry.label, data: values,
        borderColor: '#ffffff', borderWidth: 1.6,
        pointRadius: 0, tension: 0.1, spanGaps: true,
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) + unit : '—') }},
        }},
        annotation: {{ annotations: annotations }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

// Compute stress windows: contiguous index ranges where stress > 0 (light) or > 0.5 (strong).
// Returns array of {{xMin, xMax, level}} where level is 'low' or 'high'.
function computeStressWindows(stressArr) {{
  const windows = [];
  let inLow = false, inHigh = false, lowStart = -1, highStart = -1;
  for (let i = 0; i < stressArr.length; i++) {{
    const v = stressArr[i] ?? 0;
    const isHigh = v > 0.5;
    const isLow  = v > 0 && !isHigh;
    if (isHigh && !inHigh) {{ highStart = i; inHigh = true; }}
    if (!isHigh && inHigh) {{ windows.push({{xMin: highStart, xMax: i - 1, level: 'high'}}); inHigh = false; }}
    if (isLow && !inLow) {{ lowStart = i; inLow = true; }}
    if (!isLow && inLow) {{ windows.push({{xMin: lowStart, xMax: i - 1, level: 'low'}}); inLow = false; }}
  }}
  if (inHigh) windows.push({{xMin: highStart, xMax: stressArr.length - 1, level: 'high'}});
  if (inLow)  windows.push({{xMin: lowStart,  xMax: stressArr.length - 1, level: 'low'}});
  return windows;
}}

function buildMacroChart() {{
  const canvas = document.getElementById('chart-macro');
  if (!canvas) return;
  const dates = sliceRecent(CHART_DATA.dates, RANGE_BARS[currentRange]);
  const re_series = sliceRecent((CHART_DATA.macro || {{}}).real_economy_score || [], RANGE_BARS[currentRange]);
  const inf_series = sliceRecent((CHART_DATA.macro || {{}}).inflation_dir_pp || [], RANGE_BARS[currentRange]);
  const stress_series = sliceRecent((CHART_DATA.mrmi_combined || {{}}).stress_intensity || [], RANGE_BARS[currentRange]);

  // Background tint for stress episodes — faint red where stress > 0, stronger > 0.5.
  const stressWindows = computeStressWindows(stress_series);
  const stressAnnotations = {{}};
  stressWindows.forEach((w, i) => {{
    stressAnnotations['stress' + i] = {{
      type: 'box',
      xMin: w.xMin, xMax: w.xMax,
      backgroundColor: w.level === 'high' ? 'rgba(232,75,90,0.14)' : 'rgba(232,75,90,0.06)',
      borderWidth: 0,
      drawTime: 'beforeDatasetsDraw',
    }};
  }});

  if (window.macroChart) window.macroChart.destroy();
  window.macroChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label: 'Real Economy Score', data: re_series,
           borderColor: '#ffffff', borderWidth: 1.8,
           pointRadius: 0, tension: 0.1, spanGaps: true,
           yAxisID: 'y' }},
        {{ label: 'Inflation Direction Δ6m', data: inf_series,
           borderColor: '#cdaa6a', borderWidth: 1.4, borderDash: [4, 3],
           pointRadius: 0, tension: 0.1, spanGaps: true,
           yAxisID: 'yInf' }},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{ label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(2) : '—') }},
        }},
        annotation: {{
          annotations: Object.assign({{
            zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }},
          }}, stressAnnotations),
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y:    {{ position: 'left',  ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 6 }}, grid: {{ color: '#1a1a1a' }} }},
        yInf: {{ position: 'right', ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ display: false }} }},
      }},
    }},
  }});
}}

function buildStressHistoryChart() {{
  const canvas = document.getElementById('chart-stress-history');
  if (!canvas) return;
  const n = RANGE_BARS[currentRange] ?? 252;
  const dates = sliceRecent(CHART_DATA.dates, n);
  const stress = sliceRecent((CHART_DATA.mrmi_combined || {{}}).stress_score || [], n);

  if (window.stressHistoryChart) window.stressHistoryChart.destroy();
  window.stressHistoryChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: 'Stress score', data: stress,
        borderColor: '#ffffff', borderWidth: 1.8,
        pointRadius: 0, pointHoverRadius: 3, tension: 0.1, spanGaps: true,
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{
            label: ctx => {{
              const score = ctx.parsed.y !== null ? ctx.parsed.y.toFixed(1) : '—';
              return 'Stress score: ' + score;
            }},
          }},
        }},
        annotation: {{
          annotations: {{
            calmBand: {{ type: 'box', yMin: 0, yMax: {stress_cutoff_calm_watch:.2f}, backgroundColor: 'rgba(76,175,80,0.10)', borderWidth: 0, scaleID: 'y' }},
            watchBand: {{ type: 'box', yMin: {stress_cutoff_calm_watch:.2f}, yMax: {stress_cutoff_watch_building:.2f}, backgroundColor: 'rgba(205,170,106,0.10)', borderWidth: 0, scaleID: 'y' }},
            buildingBand: {{ type: 'box', yMin: {stress_cutoff_watch_building:.2f}, yMax: {stress_cutoff_building_elev:.2f}, backgroundColor: 'rgba(255,140,0,0.10)', borderWidth: 0, scaleID: 'y' }},
            elevatedBand: {{ type: 'box', yMin: {stress_cutoff_building_elev:.2f}, yMax: 10, backgroundColor: 'rgba(232,75,90,0.10)', borderWidth: 0, scaleID: 'y' }},
            watch: {{ type: 'line', yMin: {stress_cutoff_calm_watch:.2f}, yMax: {stress_cutoff_calm_watch:.2f}, borderColor: 'rgba(205,170,106,0.55)', borderWidth: 1, borderDash: [4, 4], scaleID: 'y',
              label: {{ display: true, content: 'WATCH {stress_cutoff_calm_watch:.1f}', position: 'start', backgroundColor: 'transparent', color: '#8f7644', font: {{ size: 9 }} }} }},
            building: {{ type: 'line', yMin: {stress_cutoff_watch_building:.2f}, yMax: {stress_cutoff_watch_building:.2f}, borderColor: 'rgba(255,140,0,0.55)', borderWidth: 1, borderDash: [4, 4], scaleID: 'y',
              label: {{ display: true, content: 'BUILDING {stress_cutoff_watch_building:.1f}', position: 'start', backgroundColor: 'transparent', color: '#9a6a28', font: {{ size: 9 }} }} }},
            elevated: {{ type: 'line', yMin: {stress_cutoff_building_elev:.2f}, yMax: {stress_cutoff_building_elev:.2f}, borderColor: 'rgba(232,75,90,0.55)', borderWidth: 1, borderDash: [4, 4], scaleID: 'y',
              label: {{ display: true, content: 'ELEVATED {stress_cutoff_building_elev:.1f}', position: 'start', backgroundColor: 'transparent', color: '#9a3d47', font: {{ size: 9 }} }} }},
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{
          min: 0, max: 10,
          afterBuildTicks: scale => {{ scale.ticks = [0, {stress_cutoff_calm_watch:.2f}, {stress_cutoff_watch_building:.2f}, {stress_cutoff_building_elev:.2f}, 10].map(value => ({{ value }})); }},
          ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, callback: value => Number(value).toFixed(value === 0 || value === 10 ? 0 : 1) }},
          grid: {{ color: '#1a1a1a' }},
        }},
      }},
    }},
  }});
}}

function buildStressInputsChart() {{
  const canvas = document.getElementById('chart-stress-inputs');
  if (!canvas) return;
  const n = RANGE_BARS[currentRange] ?? 252;
  const dates = sliceRecent(CHART_DATA.dates, n);
  const realEconomy = sliceRecent((CHART_DATA.macro || {{}}).real_economy_score || [], n);
  const inflationDir = sliceRecent((CHART_DATA.macro || {{}}).inflation_dir_pp || [], n);
  const growthLabel = 'Real Economy Score';
  const inflationLabel = 'Inflation Direction Δ6m';

  if (window.stressInputsChart) window.stressInputsChart.destroy();
  window.stressInputsChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label: growthLabel, data: realEconomy,
           borderColor: '#4CAF50', borderWidth: 1.6,
           pointRadius: 0, pointHoverRadius: 3, tension: 0.1, spanGaps: true }},
        {{ label: inflationLabel, data: inflationDir,
           borderColor: '#cdaa6a', borderWidth: 1.6, borderDash: [4, 3],
           pointRadius: 0, pointHoverRadius: 3, tension: 0.1, spanGaps: true }},
      ],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{
            label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? (ctx.parsed.y >= 0 ? '+' : '') + ctx.parsed.y.toFixed(2) : '—'),
          }},
        }},
        annotation: {{ annotations: {{ zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }} }} }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 6 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

buildMrmiChart('1y');
buildMmiChart('1y');
buildScorecard();
buildMacroDriversScorecard();
buildMacroChart();
buildStressHistoryChart();
buildStressInputsChart();

// Growth Impulses raw-input chart (built lazily on first <details> open).
let growthInputChart = null;
let growthInputBuilt = false;
let growthInputCurrentKey = null;
const GROWTH_ROWS_BY_KEY = (() => {{
  const map = {{}};
  const rows = ((CHART_DATA.growth_impulse || {{}}).rows) || [];
  rows.forEach(r => {{ if (r && r.key) map[r.key] = r; }});
  return map;
}})();

function buildGrowthInputChart(key) {{
  const canvas = document.getElementById('chart-growth-input');
  if (!canvas) return;
  const row = GROWTH_ROWS_BY_KEY[key];
  if (!row) return;
  growthInputCurrentKey = key;
  const n = RANGE_BARS[currentRange] ?? 252;
  const dates = sliceRecent(CHART_DATA.dates, n);
  const values = sliceRecent(row.values || [], n);
  const desc = document.getElementById('growth-input-chart-desc');
  if (desc) {{
    const unit = row.unit ? ' (' + row.unit + ')' : '';
    const z = row.z_21d != null ? ((row.z_21d >= 0 ? '+' : '') + row.z_21d.toFixed(2)) : '—';
    const z7 = row.z_change_7d != null ? ((row.z_change_7d >= 0 ? '+' : '') + row.z_change_7d.toFixed(2)) : '—';
    desc.textContent = row.source + ' · current z ' + z + ' · 7d zΔ ' + z7 + unit;
  }}
  document.querySelectorAll('.growth-input-row').forEach(tr => {{
    tr.classList.toggle('is-selected', tr.dataset.growthKey === key);
  }});

  if (growthInputChart) growthInputChart.destroy();
  growthInputChart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: row.label,
        data: values,
        borderColor: '#4CAF50', borderWidth: 1.6,
        pointRadius: 0, pointHoverRadius: 3, tension: 0.1, spanGaps: true,
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{
            label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(4) : '—'),
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 6 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

function ensureGrowthInputChart() {{
  if (growthInputBuilt) return;
  const select = document.getElementById('growth-input-select');
  if (!select) return;
  const firstKey = select.value || (select.options[0] && select.options[0].value);
  if (!firstKey) return;
  growthInputBuilt = true;
  buildGrowthInputChart(firstKey);
}}

document.addEventListener('toggle', e => {{
  const details = e.target.closest && e.target.closest('details.growth-drilldown:not(.driver-drilldown)');
  if (details && details.open) ensureGrowthInputChart();
}}, true);

if (document.querySelector('details.growth-drilldown:not(.driver-drilldown)[open]')) ensureGrowthInputChart();

document.addEventListener('change', e => {{
  if (e.target && e.target.id === 'growth-input-select') buildGrowthInputChart(e.target.value);
}});

document.addEventListener('click', e => {{
  const tr = e.target.closest && e.target.closest('.growth-input-row');
  if (!tr || e.target.closest('.growth-info-icon')) return;
  const key = tr.dataset.growthKey;
  if (!key) return;
  const growthSelect = document.getElementById('growth-input-select');
  const growthDetails = document.querySelector('details.growth-drilldown:not(.driver-drilldown)');
  if (growthSelect) growthSelect.value = key;
  if (growthDetails && !growthDetails.open) growthDetails.open = true;
  growthInputBuilt = true;
  buildGrowthInputChart(key);
}});

// Sector Breadth / Financial Conditions raw-input charts (same UX as Growth Impulses).
const DRIVER_DRILLDOWN_CONFIG = {{
  breadth: {{ payloadKey: 'sector_breadth', color: '#9AD0F5' }},
  fincon: {{ payloadKey: 'financial_conditions', color: '#cdaa6a' }},
}};
const driverInputState = {{}};

function driverRowsByKey(payloadKey) {{
  const map = {{}};
  const rows = ((CHART_DATA[payloadKey] || {{}}).rows) || [];
  rows.forEach(r => {{ if (r && r.key) map[r.key] = r; }});
  return map;
}}

function buildDriverInputChart(driverKey, inputKey) {{
  const cfg = DRIVER_DRILLDOWN_CONFIG[driverKey];
  if (!cfg) return;
  const rows = driverRowsByKey(cfg.payloadKey);
  const row = rows[inputKey];
  const canvas = document.getElementById('chart-' + driverKey + '-input');
  if (!row || !canvas) return;
  const state = driverInputState[driverKey] || (driverInputState[driverKey] = {{}});
  state.currentKey = inputKey;
  state.built = true;

  const n = RANGE_BARS[currentRange] ?? 252;
  const dates = sliceRecent(CHART_DATA.dates, n);
  const values = sliceRecent(row.values || [], n);
  const desc = document.getElementById(driverKey + '-input-chart-desc');
  if (desc) {{
    const unit = row.unit ? ' (' + row.unit + ')' : '';
    const z = row.z_21d != null ? ((row.z_21d >= 0 ? '+' : '') + row.z_21d.toFixed(2)) : '—';
    const z7 = row.z_change_7d != null ? ((row.z_change_7d >= 0 ? '+' : '') + row.z_change_7d.toFixed(2)) : '—';
    desc.textContent = row.source + ' · current z ' + z + ' · 7d zΔ ' + z7 + unit;
  }}
  document.querySelectorAll('.driver-input-row[data-driver-drilldown="' + driverKey + '"]').forEach(tr => {{
    tr.classList.toggle('is-selected', tr.dataset.inputKey === inputKey);
  }});

  if (state.chart) state.chart.destroy();
  state.chart = new Chart(canvas, {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [{{
        label: row.label,
        data: values,
        borderColor: cfg.color, borderWidth: 1.6,
        pointRadius: 0, pointHoverRadius: 3, tension: 0.1, spanGaps: true,
      }}],
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: {{ mode: 'index', intersect: false }},
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1a1a1a', borderColor: '#333', borderWidth: 1,
          titleColor: '#999', bodyColor: '#e0e0e0',
          titleFont: {{ size: 11 }}, bodyFont: {{ size: 11, family: "'SF Mono', Menlo, monospace" }},
          padding: 8,
          callbacks: {{
            label: ctx => ctx.dataset.label + ': ' + (ctx.parsed.y !== null ? ctx.parsed.y.toFixed(4) : '—'),
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ ticks: {{ color: '#555', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 6 }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }},
  }});
}}

function ensureDriverInputChart(driverKey) {{
  const state = driverInputState[driverKey] || (driverInputState[driverKey] = {{}});
  if (state.built) return;
  const select = document.getElementById(driverKey + '-input-select');
  if (!select) return;
  const firstKey = select.value || (select.options[0] && select.options[0].value);
  if (firstKey) buildDriverInputChart(driverKey, firstKey);
}}

function rebuildDriverInputCharts() {{
  Object.keys(driverInputState).forEach(driverKey => {{
    const state = driverInputState[driverKey];
    if (state && state.built && state.currentKey) buildDriverInputChart(driverKey, state.currentKey);
  }});
}}

document.addEventListener('toggle', e => {{
  const details = e.target.closest && e.target.closest('details.driver-drilldown[data-driver-drilldown]');
  if (details && details.open) ensureDriverInputChart(details.dataset.driverDrilldown);
}}, true);

Object.keys(DRIVER_DRILLDOWN_CONFIG).forEach(driverKey => {{
  const details = document.querySelector('details.driver-drilldown[data-driver-drilldown="' + driverKey + '"]');
  if (details && details.open) ensureDriverInputChart(driverKey);
}});

document.addEventListener('change', e => {{
  const select = e.target && e.target.closest && e.target.closest('select[id$="-input-select"]');
  if (!select || select.id === 'growth-input-select') return;
  const driverKey = select.id.replace(/-input-select$/, '');
  if (DRIVER_DRILLDOWN_CONFIG[driverKey]) buildDriverInputChart(driverKey, select.value);
}});

document.addEventListener('click', e => {{
  const tr = e.target.closest && e.target.closest('.driver-input-row');
  if (!tr || e.target.closest('.growth-info-icon')) return;
  const driverKey = tr.dataset.driverDrilldown;
  const inputKey = tr.dataset.inputKey;
  if (!driverKey || !inputKey) return;
  const details = document.querySelector('details.driver-drilldown[data-driver-drilldown="' + driverKey + '"]');
  const select = document.getElementById(driverKey + '-input-select');
  if (select) select.value = inputKey;
  if (details && !details.open) details.open = true;
  buildDriverInputChart(driverKey, inputKey);
}});

// Driver charts stay collapsed by default — click an individual row to expand it.
</script>

</body>
</html>
"""


def build_dashboard(use_cache: bool = True) -> Path:
    """Fetch data, compute indicators, save snapshot, and render the dashboard."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    data = fetch_all_data(use_cache=use_cache)

    print("Calculating indicators...")
    gii = calc_growth_impulse(data)
    fincon = calc_financial_conditions(data)
    breadth = calc_sector_breadth(data)
    composite = calc_composite(gii, fincon, breadth)
    biz_cycle = calc_business_cycle(data)
    infl_ctx = calc_inflation_context(data)
    macro_ctx = calc_macro_context(data, lookback_years=3)
    mrmi_combined = calc_milk_road_macro_index(composite, macro_ctx)

    print(f"  Composite:  {composite.dropna().shape[0]} valid rows, latest={composite.dropna().iloc[-1]:.2f}")
    print(f"  GII:        {gii.dropna().shape[0]} valid rows, latest fast={gii['fast'].dropna().iloc[-1]:.2f}")
    print(f"  FinCon:     {fincon['composite'].dropna().shape[0] if 'composite' in fincon else 0} valid rows")
    print(f"  Breadth:    {breadth['composite'].dropna().shape[0] if 'composite' in breadth else 0} valid rows")
    print(f"  Biz Cycle:  {biz_cycle['composite'].dropna().shape[0] if 'composite' in biz_cycle else 0} valid rows")
    print(f"  Inflation:  {infl_ctx['composite'].dropna().shape[0] if 'composite' in infl_ctx else 0} valid rows")
    mrmi_series = mrmi_combined['mrmi'].dropna()
    if len(mrmi_series):
        latest = mrmi_series.iloc[-1]
        state = mrmi_posture(latest)
        exposure = mrmi_exposure(latest)
        stress_score_now = mrmi_combined['stress_score'].dropna().iloc[-1] if len(mrmi_combined['stress_score'].dropna()) else 0
        print(f"  ▶ MRMI:     {latest:+.2f} → {state} ({exposure:.0%} exposure)  (Momentum {composite.dropna().iloc[-1]:+.2f}  Buffer {mrmi_combined['macro_buffer'].dropna().iloc[-1]:+.2f}  Stress score {stress_score_now:.1f})")
    re_score = macro_ctx['real_economy_score'].dropna()
    inf_dir = macro_ctx['inflation_dir_pp'].dropna()
    if len(re_score):
        print(f"  Macro:      Real Economy Score {re_score.iloc[-1]:+.2f} (z, 3y lookback)")
        comps = macro_ctx['real_economy_components']
        if not comps.empty:
            latest = comps.dropna().iloc[-1] if len(comps.dropna()) else None
            if latest is not None:
                comp_str = "  ".join(f"{k}={v:+.2f}" for k, v in latest.items())
                print(f"              components: {comp_str}")
        if len(inf_dir):
            cpi_y = macro_ctx['core_cpi_yoy_pct'].dropna()
            print(f"              Inflation Dir Δ6m {inf_dir.iloc[-1]:+.2f}pp  (Core CPI YoY {cpi_y.iloc[-1]:.2f}%)")

    save_snapshot(data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, mrmi_combined)
    chart_json, _seasons_current = prepare_chart_data(
        data, composite, gii, fincon, breadth, biz_cycle, infl_ctx, macro_ctx, mrmi_combined
    )
    snap = latest_snapshot()
    chart = json.loads(chart_json)
    OUTPUT.write_text(render(snap, chart, data))
    return OUTPUT


def main() -> None:
    use_cache = "--no-cache" not in sys.argv
    open_browser = "--open" in sys.argv
    out = build_dashboard(use_cache=use_cache)
    print(f"Dashboard written to {out}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"file://{out.resolve()}")


if __name__ == "__main__":
    main()
