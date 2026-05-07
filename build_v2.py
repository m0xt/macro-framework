#!/usr/bin/env python3
"""
build_v2.py — Generate dashboard v2 reflecting the redesigned framework.

Layout (from "How to Use It" slide):
  1. Banner — RISK-ON/OFF + macro-season badge
  2. MRMI history chart — see how the signal has evolved
  3. MRMI Drivers — collapsed by default, eye icon for indicator descriptions
  4. Macro Seasons — 4 season pills + intensity bars (no quadrant scatter)
  5. Reference Library — supplementary indicators (some pending data)

Reads:
  .cache/dashboard.html (extracts the embedded chart_data JSON for time series)
  .cache/snapshots/<latest>.json (current values)

Writes:
  .cache/dashboard_v2.html
"""

import json
import re
import glob
from pathlib import Path
import pandas as pd

CACHE_DIR = Path(__file__).parent / ".cache"
DASHBOARD_HTML = CACHE_DIR / "dashboard.html"
RAW_DATA_PKL = CACHE_DIR / "raw_data.pkl"
OUTPUT = CACHE_DIR / "dashboard_v2.html"


def latest_snapshot():
    files = sorted(glob.glob(str(CACHE_DIR / "snapshots" / "*.json")))
    if not files:
        raise SystemExit("No snapshot found. Run build.py first.")
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


def extract_chart_data():
    """Extract the embedded const DATA = {...}; from dashboard.html."""
    if not DASHBOARD_HTML.exists():
        raise SystemExit("dashboard.html not found. Run build.py first.")
    html = DASHBOARD_HTML.read_text()
    m = re.search(r'const DATA = (\{.*?\});', html, re.DOTALL)
    if not m:
        raise SystemExit("Could not find chart data in dashboard.html")
    return json.loads(m.group(1))


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


def _make_scale_bar(mrmi_value, state_color):
    """Horizontal bar showing where MRMI sits on a -3 to +5 scale, with threshold at 0."""
    if mrmi_value is None:
        return ""
    SCALE_MIN, SCALE_MAX = -3.0, 5.0
    clamped = max(SCALE_MIN, min(SCALE_MAX, mrmi_value))
    pct = (clamped - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100
    zero_pct = (0 - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 100
    return f"""
  <div class="scale-bar">
    <div class="scale-track">
      <div class="scale-zone-cash" style="width: {zero_pct}%;"></div>
      <div class="scale-zone-long" style="width: {100 - zero_pct}%;"></div>
      <div class="scale-zero" style="left: {zero_pct}%;"></div>
      <div class="scale-marker" style="left: {pct}%; background: {state_color}; box-shadow: 0 0 0 4px {state_color}33;"></div>
    </div>
    <div class="scale-axis">
      <span style="left: 0%;">−3</span>
      <span style="left: {zero_pct}%; color: #888;">0 · threshold</span>
      <span style="left: 100%;">+5</span>
    </div>
    <div class="scale-legend">
      <span class="scale-cash-label">CASH ↓</span>
      <span class="scale-long-label">↑ LONG</span>
    </div>
  </div>"""


def render(snap, chart, raw_data=None):
    # === NEW unified Milk Road Macro Index (MRMI) ===
    mrmi_combined = snap.get("mrmi_combined") or {}
    mrmi_value = mrmi_combined.get("value")
    mrmi_state = mrmi_combined.get("state")  # "LONG" or "CASH"
    mmi_value = mrmi_combined.get("momentum")
    macro_buffer = mrmi_combined.get("macro_buffer")
    stress_intensity = mrmi_combined.get("stress_intensity") or 0.0

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
    state_color = "#4CAF50" if is_long else "#E84B5A"
    state_label = "STAY LONG" if is_long else "CASH"
    state_subtitle = "100% position" if is_long else "0% position"
    mrmi_value_str = f"{'+' if (mrmi_value or 0) >= 0 else ''}{mrmi_value:.2f}" if mrmi_value is not None else "—"

    # State-aware story for the banner — translates the numbers into plain English
    mmi_state_word = "healthy" if state == "green" else "weak"
    if (stress_intensity or 0) >= 0.5:
        macro_state_word = "elevated stress"
    elif (stress_intensity or 0) > 0:
        macro_state_word = "mild stress building"
    else:
        macro_state_word = "no stress"

    if is_long and (stress_intensity or 0) == 0 and state == "green":
        banner_story = "Market signals are healthy and macro conditions show no stress. Framework recommends staying fully invested in risk assets."
    elif is_long and state == "green":
        banner_story = f"Market signals are healthy. Macro shows {macro_state_word} but doesn't override the buffer — stay invested."
    elif is_long and state != "green":
        banner_story = "Market signals are softening but macro stress is not confirming danger. The buffer keeps you long for now — watch for further deterioration."
    else:  # CASH
        banner_story = "Market signals AND macro conditions are both flashing danger. Framework recommends stepping aside until at least one signal recovers."

    # MMI (momentum) sub-signal coloring
    mmi_color = "#4CAF50" if state == "green" else "#E84B5A"
    mmi_label = "GREEN" if state == "green" else "RED"
    mmi_value_str = f"{'+' if (mmi_value or 0) >= 0 else ''}{mmi_value:.2f}" if mmi_value is not None else "—"

    # Macro Stress sub-signal coloring
    stress_on = (stress_intensity or 0) > 0.5
    stress_color = "#E84B5A" if stress_on else "#4CAF50"
    stress_label = "ON" if stress_on else "OFF"

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
            "value":            mrmi_combined_chart.get("value", []),
            "momentum":         mrmi_combined_chart.get("momentum", []),
            "stress_intensity": mrmi_combined_chart.get("stress_intensity", []),
            "macro_buffer":     mrmi_combined_chart.get("macro_buffer", []),
        },
        "spx": chart.get("spx", []),
        "iwm": chart.get("iwm", []),
        "btc": chart.get("btc", []),
        "drivers": drivers_meta,
        "macro": {
            "real_economy_score": re_score_series,
            "inflation_dir_pp":   inf_dir_series,
            "core_cpi_yoy_pct":   core_cpi_series,
            "components":         re_components_series,
        },
        "macro_drivers": macro_drivers_meta,
        "library": library_payload,
    }, separators=(",", ":"))

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
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px;
    color: #555; margin-bottom: 12px; font-weight: 600;
    display: flex; align-items: center;
  }}
  .step-tag {{
    display: inline-block; background: #1a1a1a; color: #777;
    font-size: 10px; padding: 2px 8px; border-radius: 4px;
    margin-right: 10px; letter-spacing: 1px;
  }}
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
    max-width: 660px; margin: 22px 0 0; color: #999;
    font-size: 14px; line-height: 1.55;
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
  .scale-zone-long {{
    background: linear-gradient(to right, #4CAF5011, #4CAF5022);
    height: 100%;
  }}
  .scale-zero {{
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

<!-- 1 · HERO (single source of truth for the headline value) -->
<header class="hero">
  <div class="hero-eyebrow">Milk Road Macro Index · {snap["date"]}</div>
  <div class="hero-row">
    <div class="hero-value mono" style="color:{state_color};">{mrmi_value_str}</div>
    <div class="hero-action">
      <div class="hero-action-label" style="color:{state_color};">{state_label}</div>
      <div class="hero-action-sub">{state_subtitle}</div>
    </div>
  </div>

  <!-- Visual scale bar -->
  {_make_scale_bar(mrmi_value, state_color)}

  <p class="hero-story">{banner_story}</p>
</header>

<!-- 2 · MRMI HISTORY CHART (right after hero — context for the headline number) -->
<div class="section-title"><span class="step-tag">STEP 1</span>How the index has evolved</div>
<div class="mrmi-chart">
  <div class="mrmi-chart-header">
    <h3>Milk Road Macro Index (MRMI)
      <span class="info-icon" data-tip="MRMI is built from two inputs: MMI (market momentum from credit / breadth / volatility) plus a macro buffer that erodes when the economy enters stagflation territory. The buffer keeps us invested by default; only when both the market signal turns red AND macro stress builds does MRMI cross below zero and trigger a CASH signal. White line = MRMI. Green/red shading = the regime. Toggle assets in the legend to overlay how SPX / Russell / BTC moved during each regime.">{info_svg}</span>
    </h3>
    <div class="range-tabs">
      <button data-range="1y" class="active">1Y</button>
      <button data-range="2y">2Y</button>
      <button data-range="5y">5Y</button>
      <button data-range="all">ALL</button>
    </div>
  </div>
  <div class="legend">
    <span class="legend-item" data-series="mrmi"><span class="legend-dot" style="background:#fff"></span>MRMI (headline)</span>
    <span class="legend-item inactive" data-series="mmi"><span class="legend-dot" style="background:#888"></span>MMI (momentum only)</span>
    <span class="legend-item" data-series="spx"><span class="legend-dot" style="background:#f5c842"></span>S&amp;P 500</span>
    <span class="legend-item inactive" data-series="iwm"><span class="legend-dot" style="background:#E84B9A"></span>Russell</span>
    <span class="legend-item inactive" data-series="btc"><span class="legend-dot" style="background:#A78BFA"></span>Bitcoin</span>
  </div>
  <div class="chart-container"><canvas id="chart-mrmi"></canvas></div>

  <div class="chart-description">
    <p><strong>What you're looking at:</strong> the white line is the MRMI value over time. Above zero → stay long. Below zero → cash. The shaded green/red regions make the regimes easy to spot. Notice the cash episodes around 2018 (vol spike), 2020 (COVID), and 2022 (bear market) — these are when both pillars confirmed danger.</p>
    <p><strong>Next:</strong> open the <em>MMI Drivers</em> section below to see what's behind the market signal, then the <em>Macro Backdrop</em> to see what's behind the economy signal.</p>
    <details class="backtest-toggle">
      <summary>How well does this work historically? <span class="muted small">(click)</span></summary>
      <div class="backtest-toggle-body">
        <p class="muted small" style="margin-bottom: 8px;">10-year backtest (2016–2026), no leverage, vs buy-and-hold:</p>
        <ul class="backtest-list">
          <li><span class="bt-asset-inline">SPX</span> +2.8% annual alpha · drawdown cut from −33.9% to −12.3%</li>
          <li><span class="bt-asset-inline">Russell 2000</span> +6.0% annual alpha · drawdown cut from −41.1% to −25.2%</li>
          <li><span class="bt-asset-inline">Bitcoin</span> +7.0% annual alpha · drawdown cut from −83.4% to −70.2%</li>
        </ul>
        <p class="muted small" style="margin-top: 8px;">Active ~22% of the time (cash during stress). OOS (2023–2026, no major stress events): SPX flat, Russell +2.5%, BTC −26% — the cost of de-risking during a bull market without stress events. The framework's value is conditional on stress periods occurring; in calm bull markets it behaves like buy-and-hold.</p>
      </div>
    </details>
  </div>
</div>

<!-- 3 · COMPOSITION (the two pillars feeding MRMI) -->
<div class="section-title"><span class="step-tag">STEP 2</span>What's inside this number</div>
<section class="comp">
  <div class="comp-header">
    <span class="comp-formula">Market + Economy → MRMI</span>
  </div>
  <div class="comp-rows">
    <div class="comp-row">
      <div class="comp-row-label">Market signal · MMI</div>
      <div class="comp-row-value mono" style="color:{mmi_color};">{mmi_value_str}</div>
      <div class="comp-row-state" style="color:{mmi_color};">{mmi_label.lower()}</div>
      <div class="comp-row-meta">Credit spreads, sector breadth, volatility — what the market itself is signaling.</div>
    </div>
    <div class="comp-row">
      <div class="comp-row-label">Economy signal · Macro Stress</div>
      <div class="comp-row-value mono" style="color:{stress_color};">{('on' if stress_on else 'off')}</div>
      <div class="comp-row-state" style="color:{stress_color};">{('stress active' if stress_on else 'no stagflation')}</div>
      <div class="comp-row-meta">Real economy + inflation direction — fires only when both turn negative simultaneously.</div>
    </div>
  </div>
  <p class="comp-rule">Both pillars must turn against the market to trigger CASH. Either alone is not enough.</p>
</section>

<!-- 4 · MMI DRIVERS (collapsible scorecard) -->
<div class="section-title"><span class="step-tag">STEP 3 · Market pillar</span>What's behind the market signal</div>
<p class="section-intro">MMI is built from three market-derived measures, equally weighted. It tells us how the market itself is behaving — independent of the underlying economy. When all three are aligned positive, momentum is healthy. When they diverge, the signal weakens.</p>
<details class="drivers">
  <summary>
    <span><span class="state-dot" style="background:{mmi_color}"></span>MMI · MOMENTUM SCORE: <span class="mono" style="color:{mmi_color};">{mmi_value_str}</span> ({mmi_label}) <span class="muted small">· GII · Breadth · FinCon — click to expand</span></span>
  </summary>
  <div class="drivers-body">
    <p class="drivers-desc">
      <strong>GII</strong> — global growth momentum (credit spreads, sector rotation, copper, vol, yield curve, shipping)<br>
      <strong>Breadth</strong> — how broadly cyclical sectors are participating<br>
      <strong>FinCon</strong> — financial conditions (equity vol + bond vol + credit spreads)<br>
      <span class="muted">Click any row to expand the chart. MMI alone does not trigger action — MRMI requires both MMI red AND macro stress to flip to CASH.</span></p>
    <div id="scorecard-mrmi"></div>
  </div>
</details>

<!-- 5 · MACRO BACKDROP -->
<div class="section-title"><span class="step-tag">STEP 4 · Economy pillar</span>What's behind the economy signal</div>
<p class="section-intro">Macro Stress fires only when two conditions hit at once: the <strong>Real Economy Score</strong> is negative (consumer spending, jobs, income, GDP nowcast deteriorating) AND <strong>Inflation Direction</strong> is positive (Core CPI rising over the last 6 months). Either alone is not enough. This is the slow, fundamental side of the framework — markets can flash false alarms, but real-economy stress takes time to build.</p>
<div class="seasons">
  <div class="chart-container" style="height: 200px; margin-bottom: 20px;"><canvas id="chart-macro"></canvas></div>
  <div class="legend" style="margin-top: -8px; margin-bottom: 18px;">
    <span class="legend-item"><span class="legend-dot" style="background:#4CAF50"></span>Real Economy Score (z, left axis)</span>
    <span class="legend-item"><span class="legend-dot" style="background:#FF8C00"></span>Inflation Direction Δ6m (pp, right axis)</span>
  </div>
  <div class="backdrop-grid">
    <div class="backdrop-cell" style="border-left-color: #4CAF50;">
      <div class="backdrop-eyebrow">REAL ECONOMY SCORE</div>
      <div class="backdrop-value mono" id="re-value-display">{fmt_signed(re_score) if re_score is not None else '—'}</div>
      <div class="backdrop-meta" id="re-meta">{('rising · ' if (re_score or 0) > 0 else 'weakening · ') + 'composite z (3y)'}</div>
    </div>
    <div class="backdrop-cell" style="border-left-color: #FF8C00;">
      <div class="backdrop-eyebrow">INFLATION DIRECTION</div>
      <div class="backdrop-value mono" id="inf-value-display">{fmt_signed(inf_dir) + 'pp' if inf_dir is not None else '—'}</div>
      <div class="backdrop-meta" id="inf-meta">{('rising · ' if (inf_dir or 0) >= 0 else 'falling · ') + 'Core CPI Δ6m'}{f' · level {core_cpi_yoy_pct:.2f}%' if core_cpi_yoy_pct is not None else ''}</div>
    </div>
  </div>

  <div class="backdrop-summary" style="border-left-color: {backdrop['color']};">
    <div class="backdrop-summary-tag" style="color: {backdrop['color']};">{backdrop['tag']} · {backdrop['label']}</div>
    <p>{backdrop['summary']}</p>
  </div>

  <div class="seasons-axis-spec">
    <strong>Real Economy Score:</strong> equal-weighted z-score of Real PCE YoY · Sahm Rule (inverted) · Real Personal Income YoY · Atlanta Fed GDPNow
    &nbsp;·&nbsp;
    <strong>Inflation Direction:</strong> Δ in Core CPI YoY over the last 6 months, in pp
  </div>
</div>

<!-- Macro Drivers (collapsible scorecard) -->
<details class="drivers seasons-drivers">
  <summary>
    <span><span class="state-dot" style="background:{backdrop['color']}"></span>MACRO DRIVERS <span class="muted small">· what's behind the Real Economy Score — click to expand</span></span>
  </summary>
  <div class="drivers-body">
    <p class="drivers-desc">The four real-economy components that feed the Real Economy Score:
      <strong>PCE</strong> (consumer growth · ~70% of GDP),
      <strong>Sahm</strong> (forward-looking labor stress signal),
      <strong>Real Income</strong> (household income trajectory),
      <strong>GDPNow</strong> (Atlanta Fed real-time GDP nowcast). Click any row to expand the chart.</p>
    <div id="scorecard-seasons"></div>
  </div>
</details>

<!-- 6 · LIBRARY -->
<div class="section-title"><span class="step-tag">STEP 5</span>Reference Library</div>
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
    Library entries don't drive the binary call — they're context that explains narrative shifts. Most need data wiring before they can populate.
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
      fill: {{ target: 'origin', above: 'rgba(76,175,80,0.22)', below: 'rgba(232,75,90,0.22)' }},
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
            zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }},
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
    html += `<tr class="expanded-row" id="exp-${{key}}"><td colspan="5"><div class="chart-wrap"><canvas id="canvas-${{key}}"></canvas></div><div class="chart-desc">${{entry.desc || ''}}</div></td></tr>`;
  }});

  html += '</tbody></table>';
  container.innerHTML = html;
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
    buildScorecard();
    buildMacroDriversScorecard();
    buildMacroChart();
    Object.keys(driverCharts).forEach(k => createDriverChart(k));
    Object.keys(macroDriverCharts).forEach(k => createMacroDriverChart(k));
    Object.keys(libCharts).forEach(k => createLibChart(k));
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

function buildMacroChart() {{
  const dates = sliceRecent(CHART_DATA.dates, RANGE_BARS[currentRange]);
  const re_series = sliceRecent((CHART_DATA.macro || {{}}).real_economy_score || [], RANGE_BARS[currentRange]);
  const inf_series = sliceRecent((CHART_DATA.macro || {{}}).inflation_dir_pp || [], RANGE_BARS[currentRange]);

  if (window.macroChart) window.macroChart.destroy();
  window.macroChart = new Chart(document.getElementById('chart-macro'), {{
    type: 'line',
    data: {{
      labels: dates,
      datasets: [
        {{ label: 'Real Economy Score', data: re_series, borderColor: '#4CAF50', borderWidth: 2,
           pointRadius: 0, tension: 0.1, spanGaps: true,
           fill: {{ target: 'origin', above: 'rgba(76,175,80,0.10)', below: 'rgba(232,75,90,0.08)' }},
           yAxisID: 'y' }},
        {{ label: 'Inflation Direction Δ6m', data: inf_series, borderColor: '#FF8C00', borderWidth: 2,
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
          annotations: {{
            zero: {{ type: 'line', yMin: 0, yMax: 0, borderColor: '#333', borderWidth: 1, scaleID: 'y' }},
          }},
        }},
      }},
      scales: {{
        x: {{ type: 'category', ticks: {{ color: '#555', font: {{ size: 10 }}, maxTicksLimit: 10, maxRotation: 0 }}, grid: {{ display: false }} }},
        y: {{ position: 'left', ticks: {{ color: '#4CAF50', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ color: '#1a1a1a' }} }},
        yInf: {{ position: 'right', ticks: {{ color: '#FF8C00', font: {{ size: 10, family: "'SF Mono', Menlo, monospace" }}, maxTicksLimit: 5 }}, grid: {{ display: false }} }},
      }},
    }},
  }});
}}

buildMrmiChart('1y');
buildScorecard();
buildMacroDriversScorecard();
buildMacroChart();

// Auto-expand all driver charts when a section is opened for the first time
document.querySelectorAll('details.drivers').forEach(d => {{
  d.addEventListener('toggle', e => {{
    if (!e.target.open) return;
    if (d.querySelector('#scorecard-mrmi')) expandAllDrivers();
    if (d.querySelector('#scorecard-seasons')) expandAllMacroDrivers();
  }});
}});
</script>

</body>
</html>
"""


if __name__ == "__main__":
    snap = latest_snapshot()
    chart = extract_chart_data()
    raw = load_raw_data()
    OUTPUT.write_text(render(snap, chart, raw))
    print(f"Dashboard v2 written to {OUTPUT}")
